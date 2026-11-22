from pathlib import Path
import json,subprocess,struct,time
r=Path(__file__).resolve().parent
elapsed=0
while True:
 b=(r/'picdata.bin').read_bytes();t,cycle,ne=struct.unpack_from('<ddd',b);ni=struct.unpack_from('<d',b,24+32*int(ne))[0]
 status='electron_extinction_confirmed' if ne==0 else ('limit_reached' if cycle>=650 else 'running')
 state={'status':status,'cycle':int(cycle),'electrons':int(ne),'ions':int(ni),'particle_weight':7000,'elapsed_solver_seconds':elapsed}
 (r/'status.json').write_text(json.dumps(state,indent=2)+'\n')
 print(state,flush=True)
 if status!='running':break
 start=time.monotonic()
 with (r/'run.log').open('a') as f:subprocess.run([str(r/'edupic'),'20'],cwd=r,stdout=f,stderr=subprocess.STDOUT,check=True)
 elapsed+=time.monotonic()-start
