#!/usr/bin/env python3
"""Build independent, relocatable Rux plugins without user config or device ids."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
VERSION='0.1.3'
OUT=ROOT/'build/releases'
STAGE=OUT/'rux-assistant-plugins'
COMMON=ROOT/'plugins/common'

def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

def build(destination=STAGE):
    if destination.exists():shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for who in ('codex','claude','kiro'):
        folder=destination/who
        shutil.copytree(COMMON,folder,ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
        write(folder/'provider.json',dict(provider=who,version=VERSION,protocol='rux-session-queues-v1'))
        runtime=folder/'runtime/scripts';runtime.mkdir(parents=True)
        for name in ('chat_hook.py','rux.py','codex_metadata.py','activity_summary.py'):shutil.copy2(ROOT/'scripts'/name,runtime/name)
        shutil.copy2(COMMON/'scripts/session_protocol.py',runtime/'scenario.py')
        shutil.copy2(ROOT/'scripts/activity_summary.py',folder/'scripts/activity_summary.py')
        # No APK/vendor SDK, recordings, transcripts, databases, serials, source paths or keystores.
        if who in ('codex','claude'):
            variable='PLUGIN_ROOT' if who=='codex' else 'CLAUDE_PLUGIN_ROOT'
            events=['SessionStart','UserPromptSubmit','PreToolUse','PostToolUse','PermissionRequest','Stop','SessionEnd']
            events+=['Interrupt'] if who=='codex' else ['Notification','StopFailure','PostToolUseFailure']
            hooks={}
            for event in events:
                item={'type':'command','command':f'python3 "${{{variable}}}/scripts/rux_plugin.py" hook --event {event}','timeout':2}
                # Exec form avoids shell tokenization on current Claude Code.
                if who=='claude':item.update(command='python3',args=['${CLAUDE_PLUGIN_ROOT}/scripts/rux_plugin.py','hook','--event',event],onFailure='continue')
                hooks[event]=[{'hooks':[item]}]
            write(folder/'hooks/hooks.json',{'hooks':hooks})
            manifest=dict(name='rux-assistant',version=VERSION,description='Independent Rux companion with per-chat queues and robot-side selection.',author={'name':'Rux Assistant'})
            if who=='codex':
                manifest.update(skills='./skills/',hooks='./hooks/hooks.json',requires_local_executor=True,
                    interface={'displayName':'Rux Assistant','shortDescription':'Rux companion · one independent queue per chat'})
            write(folder/('.codex-plugin' if who=='codex' else '.claude-plugin')/'plugin.json',manifest)
        shutil.copy2(ROOT/'plugins/README.md',folder/'README.md')
        shutil.copy2(ROOT/'plugins/PROTOCOL.md',folder/'PROTOCOL.md')
    write(destination/'.agents/plugins/marketplace.json',{
        'name':'rux-local','interface':{'displayName':'Rux Local Plugins'},'plugins':[{
            'name':'rux-assistant','source':{'source':'local','path':'./codex'},
            'policy':{'installation':'AVAILABLE','authentication':'ON_INSTALL'},'category':'Productivity'}]})
    write(destination/'.claude-plugin/marketplace.json',{
        'name':'rux-local','owner':{'name':'Rux Assistant'},'plugins':[{'name':'rux-assistant','source':'./claude','version':VERSION,'description':'Independent Rux chat companion'}]})
    shutil.copy2(ROOT/'plugins/README.md',destination/'README.md')
    shutil.copy2(ROOT/'plugins/PROTOCOL.md',destination/'PROTOCOL.md')
    return destination

def archive(path,name):
    target=OUT/name
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(path.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:z.write(p,Path(path.name)/p.relative_to(path))
    return target

if __name__=='__main__':
    build();archives=[archive(STAGE,f'rux-assistant-plugins-{VERSION}.zip')]
    archives += [archive(STAGE/who,f'rux-{who}-{VERSION}.zip') for who in ('codex','claude','kiro')]
    companion=OUT/'rux-assistant-session-queues.apk'
    if (ROOT/'build/rux-assistant.apk').exists():
        shutil.copy2(ROOT/'build/rux-assistant.apk',companion)
        archives.append(companion)
    checksum=[]
    for path in archives:
        checksum.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name)
        print(path)
    (OUT/'SHA256SUMS').write_text('\n'.join(checksum)+'\n')
