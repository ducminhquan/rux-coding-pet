#!/usr/bin/env python3
"""Import local SDK/audio dependencies without device identifiers or signing keys."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import wave
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from',dest='source_root',type=Path,help='An existing working Rux Assistant checkout')
    parser.add_argument('--sdk',type=Path,help='Path to the manufacturer RobotSdk-release.aar')
    parser.add_argument('--voices-dir',type=Path,help='Directory containing the named WAV assets')
    parser.add_argument('--resource-apk',type=Path,help='Optional resource APK from your own robot')
    parser.add_argument('--catalog',action='store_true',help='Also import build/GeeUIResource.apk from --from')
    parser.add_argument('--replace',action='store_true',help='Replace differing local dependency files')
    args=parser.parse_args()
    original=args.source_root.expanduser().resolve() if args.source_root else None
    sdk=args.sdk or (original/'vendor/RobotSdk-release.aar' if original else None)
    voices=args.voices_dir or (original/'android/assets' if original else None)
    if sdk is None or voices is None:parser.error('Set --from ROOT, or both --sdk FILE and --voices-dir DIRECTORY')
    sdk=sdk.expanduser().resolve();voices=voices.expanduser().resolve()
    if not sdk.is_file():parser.error('SDK file not found: '+str(sdk))
    with zipfile.ZipFile(sdk) as archive:
        if 'classes.jar' not in archive.namelist():parser.error('SDK AAR must contain classes.jar')
    catalog=json.loads((ROOT/'scripts/voices.json').read_text())
    scenario=json.loads((ROOT/'scripts/active_scenario.json').read_text())
    names={voice['asset'] for voice in catalog}
    names.update('voice-'+scenario['voice']+'-'+state+'.wav' for state in ('attention','completed'))
    pairs=[(sdk,ROOT/'vendor/RobotSdk-release.aar')]
    for name in sorted(names):
        source=voices/name
        if not source.is_file():parser.error('Missing WAV dependency: '+name)
        with wave.open(str(source),'rb') as audio:
            if audio.getnframes()<1 or audio.getnchannels() not in (1,2):parser.error('Invalid WAV: '+name)
        pairs.append((source,ROOT/'android/assets'/name))
    resource=args.resource_apk or (original/'build/GeeUIResource.apk' if original and args.catalog else None)
    if args.catalog and resource is None:parser.error('--catalog needs --from ROOT or --resource-apk FILE')
    if resource:
        resource=resource.expanduser().resolve()
        if not resource.is_file() or not zipfile.is_zipfile(resource):parser.error('Resource APK missing or invalid')
        pairs.append((resource,ROOT/'build/GeeUIResource.apk'))
    digest=lambda path:hashlib.sha256(path.read_bytes()).digest()
    # Validate the complete import before replacing anything.
    for source,target in pairs:
        if target.exists() and digest(source)!=digest(target) and not args.replace:parser.error('Local dependency differs; use --replace explicitly: '+str(target))
    for source,target in pairs:
        target.parent.mkdir(parents=True,exist_ok=True)
        if source!=target:shutil.copy2(source,target)
    print('Imported',len(pairs),'local dependency files. No robot connection/configuration or signing keys were copied.')

if __name__=='__main__':main()
