"""Measure five RF cycles from the preserved original-code cycle-1700 state."""
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import hashlib
import json
import re
import shutil
import struct
import subprocess
import time

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent/'default-20261117'
SOURCE = Path('/workspace/eduPIC_PAL_RF-sheath/C/eduPIC.cc')

def checkpoint(path):
    b = path.read_bytes()
    t, cycle, ne = struct.unpack_from('<ddd', b)
    ni = struct.unpack_from('<d', b, 24+32*int(ne))[0]
    assert len(b) == 32+32*(ne+ni)
    assert abs(t-cycle/13.56e6) < 1e-10
    return {'cycle':int(cycle), 'time_seconds':t, 'electrons':int(ne), 'ions':int(ni),
            'sha256':hashlib.sha256(b).hexdigest()}

def save(name, data):
    p = ROOT/name
    temp = p.with_suffix(p.suffix+'.tmp')
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n')
    temp.replace(p)

def main():
    assert not (ROOT/'run-status.json').exists(), 'Existing run; do not overwrite or repeat'
    original = json.loads((BASE/'provenance.json').read_text())
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == original['source_sha256']
    initial = checkpoint(BASE/'picdata.bin')
    assert initial['cycle'] == 1700
    shutil.copyfile(SOURCE, ROOT/'source-eduPIC.cc')
    shutil.copyfile(BASE/'picdata.bin', ROOT/'input-cycle1700.bin')
    shutil.copyfile(BASE/'picdata.bin', ROOT/'picdata.bin')
    shutil.copyfile(BASE/'convergence-before-measurement.json', ROOT/'convergence-before-measurement.json')
    lines = (BASE/'conv.dat').read_text().splitlines()
    first = lines[:1700]
    assert [int(line.split()[0]) for line in first] == list(range(1,1701))
    (ROOT/'conv.dat').write_text('\n'.join(first)+'\n')
    build = ['g++','-std=c++11','-O3','-march=native','source-eduPIC.cc','-o','edupic']
    subprocess.run(build, cwd=ROOT, check=True)
    metadata = {
        'status':'measurement_running',
        'started_at_Asia_Seoul':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        'source_repository':original['repository'], 'source_commit':original['commit'],
        'source_sha256':original['source_sha256'], 'source_unchanged':True,
        'parameters':original['parameters'], 'compile_command':build,
        'binary_sha256':hashlib.sha256((ROOT/'edupic').read_bytes()).hexdigest(),
        'command':['./edupic','5','m'], 'input_checkpoint':initial,
        'measurement_cycles':5, 'measured_cycles_inclusive':[1701,1705],
        'data_scope':'New five-cycle measurement after particle-number stationarity; not recovered cycles near 2475; not a 1000-cycle result.',
        'randomness':'Original random_device seeding; RNG state is not serialized in the checkpoint.'}
    save('run-metadata.json',metadata)
    state = {'status':'running','checkpoint_cycle':1700,'target_cycle':1705}
    save('run-status.json',state)
    started = time.monotonic()
    with (ROOT/'run.log').open('w') as log:
        p = subprocess.Popen(['stdbuf','-oL',str(ROOT/'edupic'),'5','m'],cwd=ROOT,
                             stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
        for line in p.stdout:
            log.write(line)
            log.flush()
            match = re.search(r'c =\s*(\d+)\s+t =\s*(\d+)\s+#e =\s*(\d+)\s+#i =\s*(\d+)',line)
            if match:
                c, step, ne, ni = map(int,match.groups())
                state.update(active_cycle=c, step=step, electrons=ne, ions=ni,
                             elapsed_seconds=time.monotonic()-started,
                             updated_utc=datetime.now(timezone.utc).isoformat())
                save('run-status.json',state)
                if step == 0: print(f'Measurement cycle {c-1700}/5 (RF cycle {c}); electrons {ne}, ions {ni}',flush=True)
        code = p.wait()
    if code != 0: raise RuntimeError(f'Solver exit code {code}; see run.log')
    final = checkpoint(ROOT/'picdata.bin')
    assert final['cycle'] == 1705
    report = (ROOT/'info.txt').read_text()
    assert 'VIOLATED' not in report, report
    assert re.search(r'cycles in this run\s*=\s*5\b',report)
    metadata.update(status='measurement_complete',exit_code=code,
                    completed_at_Asia_Seoul=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
                    wall_seconds=time.monotonic()-started,output_checkpoint=final)
    save('run-metadata.json',metadata)
    state.update(status='measurement_complete',checkpoint_cycle=1705)
    save('run-status.json',state)
    print('Five-cycle measurement complete; original-code stability checks passed.',flush=True)
    print(f'Elapsed {metadata["wall_seconds"]:.1f} seconds',flush=True)

if __name__ == '__main__':
    try: main()
    except Exception as error:
        save('run-error.json',{'error':str(error)})
        raise
