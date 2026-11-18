"""Run unchanged eduPIC in recoverable blocks, stop on the recorded exploratory rule."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import fcntl
import json
import os
import re
import shutil
import signal
import subprocess
import time
from adaptive_common import ROOT, KEY, SOURCE_SHA, save_json, sha, checkpoint, complete_blocks, validate_block, assess

PREVIOUS = ROOT.parent/'2026-11-18_Ar_10Pa_250V_13.56MHz_25mm_cycle1701-1705'
REPO = Path('/workspace/eduPIC_PAL_RF-sheath')

def now():
    return datetime.now(ZoneInfo('Asia/Seoul')).isoformat()

def backup():
    for attempt in range(3):
        result = subprocess.run(['python',str(ROOT/'publish_checkpoint.py')],cwd=ROOT)
        if result.returncode == 0:
            return
        if attempt < 2:
            time.sleep(5)
    raise RuntimeError('GitHub backup failed; pausing at a saved checkpoint before further calculation')

def initialize():
    if (ROOT/'provenance.json').exists():
        return
    meta = json.loads((PREVIOUS/'run-metadata.json').read_text())
    source = REPO/'C/eduPIC.cc'
    assert sha(source) == SOURCE_SHA
    initial = checkpoint(PREVIOUS/'picdata.bin')
    assert initial['cycle'] == 1705
    assert initial['sha256'] == '09c15e9568d92e87b20580927a21a44a8637cad0635f7407da248840e8aa3763'
    shutil.copyfile(source,ROOT/'source-eduPIC.cc')
    shutil.copyfile(REPO/'LICENSE',ROOT/'LICENSE')
    shutil.copyfile(PREVIOUS/'picdata.bin',ROOT/'input-cycle1705.bin')
    shutil.copyfile(PREVIOUS/'conv.dat',ROOT/'history_through1705.dat')
    shutil.copyfile(PREVIOUS/'convergence-before-measurement.json',ROOT/'initial_stationarity.json')
    (ROOT/'blocks').mkdir(exist_ok=True)
    build = ['g++','-std=c++11','-O3','-march=native','source-eduPIC.cc','-o','edupic']
    subprocess.run(build,cwd=ROOT,check=True)
    save_json(ROOT/'provenance.json',dict(source_repository=meta['source_repository'], source_commit=meta['source_commit'],
              source_sha256=SOURCE_SHA, source_unchanged=True, parameters=meta['parameters'], input_checkpoint=initial,
              started_at_Asia_Seoul=now(), compile_command=build, binary_sha256=sha(ROOT/'edupic'),
              criteria_sha256=sha(ROOT/'criteria.json'), rng='Original random_device seed on each invocation; RNG state is not saved.',
              measurement_definition='New independent 20-cycle accumulator blocks after checkpoint 1705; previous five-cycle measurement is not included in stopping statistics.'))

def request_stop(signum, frame):
    (ROOT/'STOP_AFTER_BLOCK').touch()
    print(f'Signal {signum}: finish and preserve the current block, then stop',flush=True)

def main():
    lock = (ROOT/'controller.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
    lock.write(str(os.getpid())+'\n'); lock.flush()
    initialize()
    config = json.loads((ROOT/'criteria.json').read_text())
    meta = json.loads((ROOT/'provenance.json').read_text())
    assert sha(ROOT/'source-eduPIC.cc') == SOURCE_SHA
    assert sha(ROOT/'criteria.json') == meta['criteria_sha256'], 'Criteria changed after launch'
    old = json.loads((ROOT/'status.json').read_text()) if (ROOT/'status.json').exists() else {}
    if old.get('status') in ['criteria_met', 'measurement_limit_reached']:
        print('Already stopped at a final decision; use a new directory to extend this result',flush=True)
        return
    signal.signal(signal.SIGTERM,request_stop)
    signal.signal(signal.SIGINT,request_stop)
    blocks = complete_blocks()
    previous = ROOT/'input-cycle1705.bin'
    elapsed = 0.
    for index, p in enumerate(blocks):
        b = json.loads((p/'block.json').read_text())
        assert b['cycles_inclusive'] == [1706+20*index,1725+20*index]
        assert b['input_checkpoint']['sha256'] == sha(previous)
        assert b['output_checkpoint']['sha256'] == sha(p/'picdata.bin')
        elapsed += b['wall_seconds']
        previous = p/'picdata.bin'
    current = checkpoint(previous)
    state = dict(status='running',controller_pid=os.getpid(), checkpoint_cycle=current['cycle'],
                 completed_measurement_cycles=len(blocks)*20, elapsed_solver_seconds=elapsed,
                 block_cycles=config['block_cycles'], consecutive_passes=old.get('consecutive_passes',0),
                 updated_at_Asia_Seoul=now())
    save_json(ROOT/'status.json',state)
    backup()
    while len(blocks)*20 < config['maximum_measurement_cycles']:
        if (ROOT/'STOP_AFTER_BLOCK').exists():
            state.update(status='paused_at_checkpoint',updated_at_Asia_Seoul=now())
            save_json(ROOT/'status.json',state); backup(); return
        start = current['cycle']+1
        end = start+config['block_cycles']-1
        work = ROOT/'blocks'/f'cycle{start}-{end}'
        if work.exists():
            interrupted = work.with_name(work.name+'.interrupted-'+datetime.now().strftime('%Y%m%dT%H%M%S'))
            work.rename(interrupted)
        work.mkdir()
        shutil.copyfile(previous,work/'picdata.bin')
        state.update(status='running', active_block=[start,end],updated_at_Asia_Seoul=now())
        save_json(ROOT/'status.json',state)
        begin = time.monotonic()
        started = now()
        print(f'BLOCK_START {start}-{end}',flush=True)
        with (work/'run.log').open('w') as log:
            process = subprocess.Popen(['stdbuf','-oL',str(ROOT/'edupic'),str(config['block_cycles']),'m'],
                       cwd=work, stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,start_new_session=True)
            state['solver_pid'] = process.pid
            for line in process.stdout:
                log.write(line); log.flush()
                match = re.search(r'c =\s*(\d+)\s+t =\s*(\d+)\s+#e =\s*(\d+)\s+#i =\s*(\d+)',line)
                if match:
                    cycle, step, ne, ni = map(int,match.groups())
                    state.update(active_cycle=cycle, active_step=step, electrons=ne, ions=ni,
                                 elapsed_solver_seconds=elapsed+time.monotonic()-begin,updated_at_Asia_Seoul=now())
                    save_json(ROOT/'status.json',state)
                    if step==0 and (cycle-start)%5==0:
                        print(f'PROGRESS RF={cycle} new_cycles={cycle-1706} e={ne} i={ni}',flush=True)
            code = process.wait()
        if code:
            raise RuntimeError(f'Solver exited {code} at block {start}-{end}; original checkpoints are preserved')
        wall = time.monotonic()-begin
        validation, output = validate_block(work,start,config['block_cycles'])
        save_json(work/'validation.json',validation)
        save_json(work/'block.json',dict(cycles_inclusive=[start,end],measurement_cycles=config['block_cycles'],
                  input_checkpoint=current,output_checkpoint=output,wall_seconds=wall,
                  started_at_Asia_Seoul=started,completed_at_Asia_Seoul=now(),source_sha256=SOURCE_SHA,
                  validation='validation.json',command=[str(ROOT/'edupic'),str(config['block_cycles']),'m']))
        current, previous = output, work/'picdata.bin'
        blocks.append(work)
        elapsed += wall
        assessment = assess()
        save_json(ROOT/'assessment.json',assessment)
        with (ROOT/'assessments.jsonl').open('a') as f:
            f.write(json.dumps(assessment,allow_nan=False)+'\n')
        consecutive = state['consecutive_passes']+1 if assessment['passed'] else 0
        done = consecutive >= config['required_consecutive_passes']
        limit = len(blocks)*20 >= config['maximum_measurement_cycles']
        state.update(status='criteria_met' if done else ('measurement_limit_reached' if limit else 'running'),
                     checkpoint_cycle=current['cycle'],completed_measurement_cycles=len(blocks)*20,
                     elapsed_solver_seconds=elapsed,consecutive_passes=consecutive,updated_at_Asia_Seoul=now())
        state.pop('solver_pid',None)
        save_json(ROOT/'status.json',state)
        print(f'BLOCK_DONE checkpoint={end} seconds={wall:.1f} passed={assessment["passed"]} consecutive={consecutive}',flush=True)
        if 'indicators' in assessment:
            print('INDICATORS '+json.dumps({k:{'uncertainty_pct':round(v['relative_uncertainty_indicator']*100,3),
                  'change_pct':round(v['first_last_half_relative_change']*100,3),'passed':v['passed']}
                  for k,v in assessment['indicators'].items()}),flush=True)
        backup()
        if done or limit:
            print('FINAL '+json.dumps(state),flush=True); return

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        save_json(ROOT/'error.json',dict(error=str(exc),at_Asia_Seoul=now()))
        if (ROOT/'status.json').exists():
            state=json.loads((ROOT/'status.json').read_text())
            state.update(status='paused_error',error=str(exc),updated_at_Asia_Seoul=now())
            save_json(ROOT/'status.json',state)
        raise
