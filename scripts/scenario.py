"""Validate and sync stored choreography; normal hooks send only a state/context."""
import base64
import json
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'scripts/active_scenario.json'
STATES=('working','attention','completed','idle','failed')
FACES=set(STATES)|{'cute_'+s for s in ('happy','shy','curious','sleepy','love','wink','sad')}

def validate(data):
    if not isinstance(data,dict) or set(data)-{'version','voice','states'} or type(data.get('version',1)) is not int or data.get('version',1)!=1:raise ValueError('Invalid config version/fields')
    if not isinstance(data.get('voice'),str) or data['voice'] not in {v['id'] for v in json.loads((ROOT/'scripts/voices.json').read_text())}:raise ValueError('Invalid voice')
    if not isinstance(data.get('states'),dict) or set(data['states'])!=set(STATES):raise ValueError('Invalid states')
    normalized={}
    for state in STATES:
        spec=data['states'][state]
        if not isinstance(spec,dict) or set(spec)-{'face','motion','motion2','ears','angle','repeat'} or not {'face','motion','ears','angle','repeat'}<=set(spec):raise ValueError('Invalid preset fields')
        spec=dict(spec,motion2=spec.get('motion2',0));normalized[state]=spec
        if not isinstance(spec['face'],str) or (spec['face'] not in FACES and not re.fullmatch(r'h[0-9]{4}',spec['face'])):raise ValueError('Invalid face')
        for key,lo,hi in [('motion',0,80),('motion2',0,80),('ears',0,2),('angle',1,45),('repeat',0,300)]:
            if type(spec[key]) is not int or not lo<=spec[key]<=hi:raise ValueError('Invalid '+key)
        if 0<spec['repeat']<20:raise ValueError('Repeat must be at least 20 seconds')
    for state in ('attention','completed'):
        if not (ROOT/'android/assets'/f"voice-{data['voice']}-{state}.wav").exists():
            raise ValueError('Chưa có câu trạng thái cho giọng này trong APK: '+data['voice'])
    return dict(version=1,voice=data['voice'],states=normalized)

def load(path=CONFIG):
    return validate(json.loads(path.read_text())) if path.exists() else None

def interval(state):
    config=load()
    return config['states'][state]['repeat'] if config else 0

def encode(data):return base64.b64encode(json.dumps(data,ensure_ascii=False).encode()).decode()

def sync(config=None):
    from rux import command
    return command('configure',encode(validate(config if config is not None else load())))

def dispatch(state,title='',move=True,quiet=False,context='',activity=''):
    from rux import command
    if state not in STATES:raise ValueError('Unknown state')
    return command('set-state',state,title=title,quiet=quiet,context=context,no_motion=not move,activity=activity)

def heartbeat(context):
    from rux import command
    return command('heartbeat',context=context)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=['bundle','sync']);args=p.parse_args()
    if args.action=='bundle':
        (ROOT/'android/assets/scenarios.json').write_text(json.dumps(load(),ensure_ascii=False))
        (ROOT/'android/assets/voices.json').write_text((ROOT/'scripts/voices.json').read_text())
    else:print(sync())
