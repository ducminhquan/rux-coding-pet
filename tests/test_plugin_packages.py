import contextlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('rux_plugin_test',ROOT/'plugins/common/scripts/rux_plugin.py')
plugin=importlib.util.module_from_spec(spec);spec.loader.exec_module(plugin)

class PluginTest(unittest.TestCase):
    def test_adapter_discards_content_and_isolates_every_chat(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ):
            root=Path(temp);project=root/'project';project.mkdir()
            config=dict(enabled=True,projects=[str(project)],serial='TEST_ONLY',adb='adb',data_dir=str(root/'codex-data'))
            folders=[]
            for session in ['a','b']:
                event=plugin.normalize('codex',dict(cwd=str(project),session_id=session,turn_id='t',hook_event_name='UserPromptSubmit',prompt='PRIVATE',tool_input={'secret':'PRIVATE'},last_assistant_message='PRIVATE'))
                folders.append(plugin.accept(config,event,spawn=False))
            self.assertNotEqual(folders[0],folders[1])
            for folder in folders:
                c=sqlite3.connect(folder/'queue.sqlite3');rows=c.execute('SELECT session,turn,event FROM events').fetchall();c.close()
                self.assertEqual(len(rows),1);self.assertNotIn('PRIVATE',repr(rows))
    def test_claude_generates_new_turns_without_reading_transcript(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ):
            project=Path(temp)
            c=dict(enabled=True,projects=[temp],serial='TEST',adb='adb',data_dir=str(project/'state'))
            turns=[]
            for event_name in ['UserPromptSubmit','PermissionRequest','PreToolUse','Stop','UserPromptSubmit']:
                event=plugin.normalize('claude',dict(cwd=temp,session_id='s',hook_event_name=event_name,transcript_path='/do/not/read'))
                directory=plugin.accept(c,event,spawn=False)
                with contextlib.closing(sqlite3.connect(directory/'queue.sqlite3')) as db:turns.append(db.execute("SELECT value FROM meta WHERE key='plugin_turn'").fetchone()[0])
            self.assertEqual(len(set(turns[:4])),1);self.assertNotEqual(turns[0],turns[4])
    def test_kiro_aliases_and_unsupported_notification(self):
        self.assertEqual(plugin.normalize('kiro',{'hook_event_name':'agentStop','session_id':'s'})['event'],'Stop')
        self.assertEqual(plugin.normalize('kiro',{'hook_event_name':'userPromptSubmit','session_id':'s'})['event'],'UserPromptSubmit')
        self.assertIsNone(plugin.normalize('claude',{'hook_event_name':'Notification','notification_type':'auth_success'}))
        self.assertIsNone(plugin.normalize('claude',{'hook_event_name':'Stop','agent_id':'child'}))
    def test_codex_permission_preflight_is_not_human_attention(self):
        base=dict(session_id='s',hook_event_name='PermissionRequest')
        self.assertEqual(plugin.normalize('codex',base)['event'],'PermissionCheck')
        self.assertEqual(plugin.normalize('claude',base)['event'],'PermissionRequest')
        self.assertEqual(plugin.normalize('codex',dict(base,hook_event_name='PreToolUse',tool_name='functions.request_user_input'))['event'],'NeedsInput')
        self.assertEqual(plugin.normalize('codex',dict(base,hook_event_name='PreToolUse',tool_name='functions.request_user_input_async'))['event'],'PreToolUse')
    def test_scope_and_disabled_are_noops(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ):
            c=dict(enabled=True,projects=[temp],serial='TEST',adb='adb',data_dir=str(Path(temp)/'state'))
            e=plugin.normalize('kiro',{'cwd':'/different','session_id':'s','hook_event_name':'UserPromptSubmit'})
            self.assertIsNone(plugin.accept(c,e,spawn=False));self.assertFalse(Path(c['data_dir']).exists())
    def test_plugin_cache_path_with_spaces_and_missing_config_fail_open(self):
        with tempfile.TemporaryDirectory(prefix='Rux plugin ') as temp:
            root=Path(temp);(root/'scripts').mkdir();(root/'provider.json').write_text('{"provider":"claude"}')
            import shutil
            shutil.copy2(ROOT/'plugins/common/scripts/rux_plugin.py',root/'scripts/rux_plugin.py')
            env=dict(os.environ,RUX_PLUGIN_CONFIG=str(root/'missing.json'))
            p=subprocess.run([sys.executable,str(root/'scripts/rux_plugin.py'),'hook'],input='{"hook_event_name":"Stop","last_assistant_message":"PRIVATE"}',text=True,capture_output=True,env=env)
            self.assertEqual(p.returncode,0);self.assertEqual(json.loads(p.stdout),{});self.assertNotIn('PRIVATE',p.stderr)
    def test_wire_sequence_is_per_session_and_has_no_shared_queue(self):
        spec=importlib.util.spec_from_file_location('wire_test',ROOT/'plugins/common/scripts/session_protocol.py')
        wire=importlib.util.module_from_spec(spec);spec.loader.exec_module(wire)
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,RUX_SOURCE='claude',RUX_SESSION='s',RUX_STATE_DIR=temp):
            first=wire.envelope(json.dumps(['claude:s','turn1','working']))
            second=wire.envelope(json.dumps(['claude:s','turn1','working']))
            self.assertEqual((first['sequence'],second['sequence']),(1,2));self.assertEqual(first['turn_id'],'turn1')
