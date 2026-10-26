"""Wire adapter: no host-side selection, one durable sequence counter per chat."""
import base64
import fcntl
import json
import os
from pathlib import Path

def envelope(context):
    source=os.environ['RUX_SOURCE'];session=os.environ['RUX_SESSION']
    data=Path(os.environ['RUX_STATE_DIR']);data.mkdir(parents=True,exist_ok=True)
    with (data/'wire-sequence.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        path=data/'wire-sequence.txt'
        sequence=int(path.read_text())+1 if path.exists() else 1
        temp=data/'wire-sequence.tmp'
        with temp.open('w') as stream:
            stream.write(str(sequence));stream.flush();os.fsync(stream.fileno())
        temp.replace(path)
    parts=json.loads(context)
    return dict(source=source,session_id=session,turn_id=parts[1],sequence=sequence)

def encode(value):return base64.b64encode(json.dumps(value,ensure_ascii=False).encode()).decode()

def dispatch(state,title='',move=True,quiet=False,context='',activity=''):
    from rux import command
    value=envelope(context);value.update(state=state,title=title,quiet=bool(quiet),no_motion=not move,activity=activity[:80])
    return command('session-state',encode(value))

def heartbeat(context):
    from rux import command
    return command('session-heartbeat',encode(envelope(context)))
