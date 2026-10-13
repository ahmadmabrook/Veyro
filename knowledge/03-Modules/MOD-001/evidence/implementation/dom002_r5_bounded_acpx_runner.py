from pathlib import Path
import subprocess,json,datetime
base=Path(__file__).parent
raw=base/'DOM002-R5-BOUNDED-ACPX-RAW-2026-10-04.txt'
exitfile=base/'DOM002-R5-BOUNDED-ACPX-EXIT-2026-10-04.json'
prompt=(base/'DOM002-R5-BOUNDED-RECOVERY-PROMPT-2026-10-04.txt').read_text()
cmd=['/Users/ahmadmabrouk/.openclaw/extensions/acpx/node_modules/.bin/acpx','--cwd','/Users/ahmadmabrouk/Desktop/Veyro','--approve-all','--non-interactive-permissions','fail','--timeout','1200','claude','-s','veyro-mod001-dom002-r5-bounded-20261004',prompt]
start=datetime.datetime.now(datetime.timezone.utc).isoformat()
with raw.open('w') as f:
    try:
        p=subprocess.run(cmd,cwd='/Users/ahmadmabrouk/Desktop/Veyro',stdout=f,stderr=subprocess.STDOUT,timeout=1250)
        result={'exitCode':p.returncode,'startedAt':start,'completedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'commandFlags':['--approve-all','--non-interactive-permissions fail','--timeout 1200'],'session':'veyro-mod001-dom002-r5-bounded-20261004'}
    except subprocess.TimeoutExpired:
        result={'exitCode':None,'error':'wrapper timeout after 1250 seconds','startedAt':start,'completedAt':datetime.datetime.now(datetime.timezone.utc).isoformat()}
exitfile.write_text(json.dumps(result,indent=2)+'\n')
