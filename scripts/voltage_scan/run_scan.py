"""Independent, recoverable PIC/MCC cases with the previously agreed stopping rule."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor
import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import time
import traceback
import numpy as np
from stopping import save_json, sha, checkpoint, validate_block, stationarity, assess_blocks


def now():
    return datetime.now(ZoneInfo('Asia/Seoul')).isoformat()


def atomic_copy(src, dst):
    dst = Path(dst)
    tmp = dst.with_suffix(dst.suffix + '.tmp')
    shutil.copyfile(src, tmp)
    tmp.replace(dst)


def completed(case):
    paths = list((case / 'warmup').glob('*/block.json'))
    paths += list((case / 'measurements').glob('*/*/block.json'))
    return sorted(paths, key=lambda p: json.loads(p.read_text())['cycles_inclusive'][0])


def recover(case):
    """Only complete blocks count; partial work is preserved but never merged."""
    previous = case / 'input_cycle0.bin'
    history, records = [], []
    for path in completed(case):
        record = json.loads(path.read_text())
        cp = checkpoint(previous)
        assert record['input_checkpoint']['sha256'] == cp['sha256']
        assert record['cycles_inclusive'][0] == cp['cycle'] + 1
        current = path.parent / 'picdata.bin'
        assert record['output_checkpoint']['sha256'] == sha(current)
        hist = np.loadtxt(path.parent / 'conv.dat', ndmin=2)
        assert np.array_equal(hist[:, 0], np.arange(*[record['cycles_inclusive'][0], record['cycles_inclusive'][1] + 1]))
        history.extend(hist.tolist())
        records.append((path.parent, record))
        previous = current
    return previous, history, records


def run_case(root, voltage):
    case = root / f'2026-11-19_Ar_20mTorr_{voltage}V_13.56MHz_25mm_topRF'
    lock = (case / 'controller.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    lock.write(str(os.getpid())); lock.flush()
    criteria = json.loads((root / 'criteria.json').read_text())
    config = json.loads((root / 'config.json').read_text())
    assert sha(root / 'source-eduPIC.cc') == config['source_sha256']
    old = json.loads((case / 'status.json').read_text()) if (case / 'status.json').exists() else {}
    if old.get('status') in ['criteria_met', 'extinguished', 'measurement_limit_reached', 'total_cycle_limit_reached']:
        return old
    previous, history, records = recover(case)
    current = checkpoint(previous)
    phase = old.get('phase', 'warmup')
    epoch = old.get('measurement_epoch', 0)
    elapsed = sum(r['wall_seconds'] for _, r in records)
    active_blocks = [p for p, r in records if r['phase'] == 'measurement' and r['measurement_epoch'] == epoch]
    passes = old.get('consecutive_passes', 0)
    state = dict(status='running', phase=phase, voltage_peak_V=voltage, pressure_mTorr=20,
                 checkpoint_cycle=current['cycle'], measurement_epoch=epoch,
                 completed_measurement_cycles=len(active_blocks) * 20,
                 elapsed_solver_seconds=elapsed, consecutive_passes=passes,
                 controller_pid=os.getpid(), started_at_Asia_Seoul=old.get('started_at_Asia_Seoul', now()))

    def update(**kwargs):
        state.update(kwargs, updated_at_Asia_Seoul=now())
        save_json(case / 'status.json', state)

    try:
        update()
        while True:
            if (root / 'STOP_AFTER_BLOCK').exists() or (case / 'STOP_AFTER_BLOCK').exists():
                update(status='paused_at_checkpoint'); break
            if current['cycle'] >= criteria['maximum_total_cycles']:
                update(status='total_cycle_limit_reached'); break
            if current['electrons'] == 0 and current['ions'] == 0:
                update(status='extinguished', reason='Both simulated particle populations are zero; no sustained discharge in this realization.'); break
            stable = stationarity(history, criteria)
            if phase == 'warmup' and stable['passed']:
                phase = 'measurement'; epoch += 1; active_blocks = []; passes = 0
                update(phase=phase, measurement_epoch=epoch, measurement_start_cycle=current['cycle'] + 1,
                       completed_measurement_cycles=0, consecutive_passes=0)
                print(f'{voltage}V MEASUREMENT_START at cycle {current["cycle"] + 1}', flush=True)
            count = criteria['block_cycles'] if phase == 'measurement' else criteria['warmup_block_cycles']
            start = current['cycle'] + 1; end = start + count - 1
            base = case / ('warmup' if phase == 'warmup' else f'measurements/epoch{epoch:03d}')
            base.mkdir(parents=True, exist_ok=True)
            work = base / f'cycle{start:06d}-{end:06d}'
            if work.exists():
                work.rename(work.with_name(work.name + '.interrupted-' + datetime.now().strftime('%Y%m%dT%H%M%S')))
            work.mkdir()
            shutil.copyfile(previous, work / 'picdata.bin')
            command = [str(case / 'edupic'), str(count)] + (['m'] if phase == 'measurement' else [])
            update(active_block=[start, end], phase=phase, particle_count_stationarity=stable)
            begin = time.monotonic(); started = now()
            print(f'{voltage}V {phase} BLOCK {start}-{end}', flush=True)
            with (work / 'run.log').open('w') as log:
                proc = subprocess.Popen(['stdbuf', '-oL', *command], cwd=work, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True)
                update(solver_pid=proc.pid)
                for line in proc.stdout:
                    log.write(line); log.flush()
                    m = re.search(r'c =\s*(\d+)\s+t =\s*(\d+)\s+#e =\s*(\d+)\s+#i =\s*(\d+)', line)
                    if m:
                        cycle, step, ne, ni = map(int, m.groups())
                        update(active_cycle=cycle, active_step=step, electrons=ne, ions=ni,
                               elapsed_solver_seconds=elapsed + time.monotonic() - begin)
                code = proc.wait()
            if code:
                raise RuntimeError(f'Solver exited {code}; last complete checkpoint is preserved')
            wall = time.monotonic() - begin
            output = checkpoint(work / 'picdata.bin')
            assert output['cycle'] == end
            conv = np.loadtxt(work / 'conv.dat', ndmin=2)
            assert conv.shape == (count, 3)
            assert np.array_equal(conv[:, 0], np.arange(start, end + 1))
            assert np.array_equal(conv[-1, 1:], [output['electrons'], output['ions']])
            if phase == 'measurement':
                validation, _ = validate_block(work, start, count)
                potential = np.loadtxt(work / 'pot_xt.dat')
                expected = voltage * np.cos(2 * np.pi * (np.arange(4000) + 1) / 4000).reshape(200, 20).mean(axis=1)
                assert np.max(np.abs(potential[0])) < 1e-8
                assert np.allclose(potential[-1], expected, atol=.001, rtol=2e-6)
                validation['electrode_orientation'] = 'bottom x=0 grounded; top x=L powered'
                save_json(work / 'validation.json', validation)
            record = dict(cycles_inclusive=[start, end], phase=phase, measurement_epoch=epoch,
                          input_checkpoint=current, output_checkpoint=output, wall_seconds=wall,
                          source_sha256=config['source_sha256'], command=command,
                          started_at_Asia_Seoul=started, completed_at_Asia_Seoul=now())
            save_json(work / 'block.json', record)
            previous = work / 'picdata.bin'; current = output; elapsed += wall
            history.extend(conv.tolist()); records.append((work, record))
            tmp = case / 'history.dat.tmp'; np.savetxt(tmp, history, fmt='%d'); tmp.replace(case / 'history.dat')
            atomic_copy(previous, case / 'latest_checkpoint.bin')
            state.pop('solver_pid', None)
            update(checkpoint_cycle=end, elapsed_solver_seconds=elapsed, latest_block=str(work.relative_to(case)),
                   electrons=current['electrons'], ions=current['ions'])
            if phase == 'measurement':
                active_blocks.append(work)
                assessment = assess_blocks(active_blocks, history, criteria)
                save_json(case / 'assessment.json', assessment)
                with (case / 'assessments.jsonl').open('a') as f:
                    f.write(json.dumps({'epoch': epoch, 'checkpoint_cycle': end, **assessment}, allow_nan=False) + '\n')
                passes = passes + 1 if assessment['passed'] else 0
                update(completed_measurement_cycles=len(active_blocks) * 20, consecutive_passes=passes,
                       particle_count_stationarity=assessment['particle_count_stationarity'])
                print(f'{voltage}V CHECK cycle={end} samples={len(active_blocks)*20} pass={assessment["passed"]} consecutive={passes}', flush=True)
                if passes >= criteria['required_consecutive_passes']:
                    update(status='criteria_met'); break
                # Do not average across a newly detected secular density transient.
                drift = any(v['first_last_half_relative_change'] > .03 for k, v in assessment.get('indicators', {}).items()
                            if 'density' in k)
                if len(active_blocks) >= 5 and drift and not assessment['particle_count_stationarity']['passed']:
                    print(f'{voltage}V DISCARD_EPOCH {epoch}: renewed density drift', flush=True)
                    phase = 'warmup'; passes = 0
                    update(phase=phase, consecutive_passes=0, epoch_discard_reason='renewed density drift; raw blocks retained')
                elif len(active_blocks) * 20 >= criteria['maximum_measurement_cycles']:
                    update(status='measurement_limit_reached'); break
            print(f'{voltage}V SAVED cycle={end} e={current["electrons"]} i={current["ions"]} seconds={wall:.1f}', flush=True)
        print(f'{voltage}V FINISHED {state["status"]} cycle={state["checkpoint_cycle"]}', flush=True)
        return state
    except Exception as exc:
        state.pop('solver_pid', None)
        update(status='paused_error', error=str(exc))
        (case / 'error.log').write_text(traceback.format_exc())
        print(f'{voltage}V ERROR {exc}', flush=True)
        return state


def main():
    p = argparse.ArgumentParser()
    p.add_argument('root', type=Path)
    p.add_argument('--voltage', type=int, nargs='+', default=[100, 250, 300])
    args = p.parse_args()
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda v: run_case(args.root.resolve(), v), args.voltage))
    save_json(args.root / 'scan_status.json', {'updated_at_Asia_Seoul': now(), 'cases': results})


if __name__ == '__main__':
    main()
