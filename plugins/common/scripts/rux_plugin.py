#!/usr/bin/env python3
"""Independent agent plugin. One metadata queue/worker/lease per chat session."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
PROVIDERS=('codex','claude','kiro')
ALIASES={'userpromptsubmit':'UserPromptSubmit','promptsubmit':'UserPromptSubmit','pretooluse':'PreToolUse','posttooluse':'PostToolUse','posttoolusefailure':'PostToolUse',
         'permissionrequest':'PermissionRequest','stop':'Stop','agentstop':'Stop','sessionend':'SessionEnd',
         'interrupt':'Interrupt','stopfailure':'Failure','sessionstart':'SessionStart','agentspawn':'SessionStart'}

def provider():
    value=json.loads((ROOT/'provider.json').read_text())['provider']
    if value not in PROVIDERS:raise ValueError('Invalid provider')
    return value

def config_path(who):
    return Path(os.environ.get('RUX_PLUGIN_CONFIG',str(Path.home()/'.config/rux-assistant'/f'{who}.json'))).expanduser().resolve()

def atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temp.open('w',encoding='utf-8') as stream:
            os.chmod(temp,0o600);json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        temp.replace(path)
    finally:temp.unlink(missing_ok=True)

def read_config(who):
    path=config_path(who)
    if not path.exists():return None
    c=json.loads(path.read_text())
    if c.get('version')!=1 or c.get('provider')!=who or type(c.get('enabled')) is not bool:raise ValueError('Invalid plugin config')
    if not isinstance(c.get('serial'),str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,200}',c['serial']):raise ValueError('Invalid device serial')
    if not isinstance(c.get('projects'),list) or not c['projects']:raise ValueError('Missing projects')
    if not isinstance(c.get('adb'),str) or not c['adb']:raise ValueError('Missing adb')
    if not isinstance(c.get('data_dir'),str) or not Path(c['data_dir']).is_absolute():raise ValueError('Invalid data dir')
    return c

def allowed(c,cwd):
    return '*' in c['projects'] or any(cwd==Path(p).expanduser().resolve() or Path(p).expanduser().resolve() in cwd.parents for p in c['projects'])

def normalize(who,payload,event_override=None,cwd=None):
    if not isinstance(payload,dict):return None
    if who=='claude' and payload.get('agent_id'):return None # Subagents must not finish the parent chat.
    raw=event_override or payload.get('hook_event_name') or payload.get('hookEventName') or payload.get('event') or ''
    if raw=='Notification':
        event='PermissionRequest' if payload.get('notification_type') in ('permission_prompt','idle_prompt') else None
    else:event=ALIASES.get(str(raw).lower())
    if event is None:return None
    directory=Path(payload.get('cwd') or cwd or os.getcwd()).resolve()
    session=payload.get('session_id') or payload.get('sessionId') or payload.get('conversation_id') or payload.get('conversationId')
    if not session:
        # Some IDE hook versions omit session ids: isolated workspace stream, documented fallback.
        session='workspace-'+hashlib.sha256(str(directory).encode()).hexdigest()[:24]
    if not isinstance(session,str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,200}',session):return None
    turn=payload.get('turn_id') or payload.get('turnId') or ''
    if not isinstance(turn,str) or len(turn)>200:return None
    title=payload.get('session_title')
    title=' '.join(title.split())[:160] if isinstance(title,str) else ''
    from activity_summary import activity_fields, is_input_request
    if who=='codex' and event=='PermissionRequest':event='PermissionCheck'
    elif event=='PreToolUse' and is_input_request(payload):event='NeedsInput'
    activity,activity_id=activity_fields(payload) if event in ('PreToolUse','PostToolUse') else ('','')
    return dict(provider=who,event=event,cwd=str(directory),session=session,turn=turn,title=title,activity=activity,activity_id=activity_id)

def accept(c,event,spawn=True):
    if not c['enabled'] or not allowed(c,Path(event['cwd'])):return None
    ident=hashlib.sha256((event['provider']+':'+event['session']).encode()).hexdigest()
    directory=Path(c['data_dir'])/'sessions'/ident
    directory.mkdir(parents=True,exist_ok=True)
    # No cross-session locks or aggregation. Robot arbitrates these separate streams.
    os.environ.update(RUX_STATE_DIR=str(directory),RUX_PROJECT_ROOT=event['cwd'],RUX_SERIAL=c['serial'],
                      ADB=c['adb'],RUX_SOURCE=event['provider'],RUX_SESSION=event['session'])
    sys.path.insert(0,str(ROOT/'runtime/scripts'))
    import chat_hook
    with contextlib.closing(chat_hook.database(directory)) as db:
        db.execute('BEGIN IMMEDIATE')
        prior=db.execute("SELECT value FROM meta WHERE key='plugin_turn'").fetchone()
        turn=event['turn'] or (uuid.uuid4().hex if event['event']=='UserPromptSubmit' or not prior else prior[0])
        db.execute("INSERT OR REPLACE INTO meta VALUES('plugin_turn',?)",(turn,))
        name=event['title'] or c.get('title') or f"{event['provider'].title()} · {Path(event['cwd']).name}"
        session=event['provider']+':'+event['session']
        old=db.execute('SELECT name FROM titles WHERE session=?',(session,)).fetchone()
        if old and not event['title'] and not c.get('title'):name=old[0]
        db.execute('INSERT OR REPLACE INTO titles VALUES(?,?,?)',(session,name,time.time()))
        if event['event']!='SessionStart' and not (directory/'disabled').exists():
            db.execute('INSERT INTO events(at,session,turn,event,activity,activity_id) VALUES(?,?,?,?,?,?)',(time.time(),session,turn,event['event'],event.get('activity',''),event.get('activity_id','')))
        db.commit()
    if spawn and event['event']!='SessionStart':
        with (directory/'worker.log').open('a') as log:
            subprocess.Popen([sys.executable,str(ROOT/'runtime/scripts/chat_hook.py'),'--worker'],
                stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,close_fds=True)
    return directory

def configure(args,who):
    path=config_path(who);old=read_config(who) or {}
    projects=['*'] if args.all_projects else list(dict.fromkeys(old.get('projects',[])+[str(Path(p).expanduser().resolve()) for p in args.project]))
    if not projects:raise ValueError('Choose --project PATH or --all-projects')
    adb=args.adb or old.get('adb') or shutil.which('adb') or str(Path.home()/'Library/Android/sdk/platform-tools/adb')
    serial=args.serial or old.get('serial')
    if not isinstance(serial,str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,200}',serial):raise ValueError('Set --serial (USB serial or IP:5555)')
    data=Path(args.data_dir or old.get('data_dir') or Path.home()/'.local/share/rux-assistant'/who).expanduser().resolve()
    c=dict(version=1,provider=who,enabled=True,serial=serial,adb=adb,projects=projects,data_dir=str(data))
    if args.title or old.get('title'):c['title']=args.title or old['title']
    atomic_json(path,c);print('Configured:',path)

def kiro_install(args):
    project=Path(args.project).expanduser().resolve()
    if not project.is_dir():raise ValueError('Project does not exist')
    cmd=shlex.join([sys.executable,str(Path(__file__).resolve()),'hook'])
    events=[('UserPromptSubmit','promptSubmit'),('PreToolUse','preToolUse'),('PostToolUse','postToolUse'),('Stop','agentStop'),('SessionStart','sessionStart')]
    if args.flavor=='cli-v2':
        path=project/'.kiro/agents/rux-assistant.json'
        hooks={key:[{'command':cmd+' --event '+event,'timeout_ms':2000}] for event,key in [('SessionStart','agentSpawn'),('UserPromptSubmit','userPromptSubmit'),('PreToolUse','preToolUse'),('PostToolUse','postToolUse'),('Stop','stop')]}
        data=dict(name='rux-assistant',description='Kiro with an independent Rux chat companion',hooks=hooks)
    elif args.flavor=='ide-v1':
        path=project/'.kiro/hooks/rux-assistant.json'
        data={'version':'v1','hooks':[dict(name='rux-'+event.lower(),when={'type':legacy},then={'type':'command','command':cmd+' --event '+event},timeout=2,enabled=True) for event,legacy in events]}
    else:
        path=project/'.kiro/hooks/rux-assistant.json'
        data={'version':'v1','hooks':[dict(name='rux-'+event.lower(),trigger=event,action={'type':'command','command':cmd+' --event '+event},timeout=2,enabled=True) for event,_ in events]}
    if path.exists():
        if json.loads(path.read_text())==data:print('Already installed:',path);return
        raise ValueError('Existing Rux definition differs; refusing to overwrite '+str(path))
    atomic_json(path,data);print('Installed:',path)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    hook=sub.add_parser('hook');hook.add_argument('--event')
    config=sub.add_parser('configure');config.add_argument('--serial');config.add_argument('--adb');config.add_argument('--project',action='append',default=[]);config.add_argument('--all-projects',action='store_true');config.add_argument('--data-dir');config.add_argument('--title')
    sub.add_parser('doctor');sub.add_parser('disable')
    installer=sub.add_parser('install-kiro');installer.add_argument('--project',required=True);installer.add_argument('--flavor',choices=['cli-v2','cli-v3','ide-v1'],required=True)
    args=parser.parse_args()
    if args.action=='hook':
        try:
            raw=sys.stdin.read(256*1024+1)
            if len(raw)<=256*1024:
                who=provider();c=read_config(who)
                if c:
                    event=normalize(who,json.loads(raw) if raw.strip() else {},args.event)
                    if event:accept(c,event)
        except Exception as e:
            # Never block/approve a prompt/tool, leak content, or make the agent continue.
            print('Rux hook unavailable: '+type(e).__name__,file=sys.stderr)
        print('{}');return 0
    try:
        who=provider()
        if args.action=='configure':configure(args,who)
        elif args.action=='install-kiro':
            if who!='kiro':raise ValueError('This is not the Kiro package')
            kiro_install(args)
        elif args.action=='disable':
            c=read_config(who)
            if c:c['enabled']=False;atomic_json(config_path(who),c)
            print('Disabled; existing robot lease expires within 45 seconds. Use robot Stop for immediate stop.')
        else:
            c=read_config(who)
            print(json.dumps({'provider':who,'configured':bool(c),'enabled':c['enabled'] if c else False,'config':str(config_path(who)),
                'runtime_present':(ROOT/'runtime/scripts/chat_hook.py').is_file(),'adb_found':bool(c and (Path(c['adb']).is_file() or shutil.which(c['adb']))),
                'queue_scope':'one directory and worker per chat','robot_protocol':'rux-session-queues-v1'},indent=2))
        return 0
    except Exception as e:print(str(e),file=sys.stderr);return 1

if __name__=='__main__':sys.exit(main())
