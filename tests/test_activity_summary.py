import contextlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from activity_summary import summary
from chat_hook import ROOT,database,enqueue,worker

class ActivityTest(unittest.TestCase):
    def test_read_and_edit_only_emit_basename(self):
        self.assertEqual(summary({'tool_name':'Read','tool_input':{'file_path':'/private/work/app.js','content':'SECRET'}}),'Đang đọc app.js…')
        self.assertEqual(summary({'tool_name':'Edit','tool_input':{'file_path':'C:\\project\\main.py','old_string':'SECRET'}}),'Đang sửa main.py…')
    def test_shell_is_allowlisted_and_never_exposes_arguments(self):
        self.assertEqual(summary({'tool_name':'exec_command','tool_input':{'cmd':"sed -n '1,20p' src/app.js"}}),'Đang đọc app.js…')
        self.assertEqual(summary({'tool_name':'Bash','tool_input':{'command':'curl --header "Authorization: SECRET" https://private'}}),'Đang chạy lệnh…')
        self.assertEqual(summary({'tool_name':'Bash','tool_input':{'command':'cat app.js; echo SECRET'}}),'Đang chạy lệnh…')
        self.assertEqual(summary({'tool_name':'Bash','tool_input':{'command':'npm test -- SECRET'}}),'Đang chạy kiểm tra…')
    def test_opaque_or_malformed_tools_do_not_copy_descriptions(self):
        self.assertEqual(summary({'tool_name':'functions.exec','tool_input':{'code':'SECRET','description':'SECRET'}}),'Đang dùng công cụ…')
        self.assertEqual(summary({'tool_name':'Read','tool_input':None}),'Đang đọc tệp…')
        self.assertEqual(summary({}),'')
    def test_correlated_post_event_does_not_clear_newer_activity(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);sent=[]
            base=dict(cwd=str(ROOT),session_id='s',turn_id='t')
            for name,tool_id,path in [('UserPromptSubmit','',''),('PreToolUse','old','old.js'),('PreToolUse','new','new.js'),('PostToolUse','old','old.js')]:
                enqueue(dict(base,hook_event_name=name,tool_name='Read',tool_use_id=tool_id,tool_input={'file_path':'/private/'+path,'content':'SECRET'}),directory)
                worker(directory,sent.append)
            with contextlib.closing(database(directory)) as db:
                self.assertEqual(db.execute('SELECT text FROM activities').fetchone()[0],'Đang đọc new.js…')
                data=repr(db.execute('SELECT * FROM events').fetchall())
                self.assertNotIn('SECRET',data);self.assertNotIn('/private/',data)
            enqueue(dict(base,hook_event_name='PostToolUse',tool_name='Read',tool_use_id='new',tool_input={'file_path':'new.js'}),directory);worker(directory,sent.append)
            with contextlib.closing(database(directory)) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM activities').fetchone()[0],0)
    def test_stop_clears_activity_and_old_turn_cannot_restore_it(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);sent=[];base=dict(cwd=str(ROOT),session_id='s',turn_id='current')
            for event in ['UserPromptSubmit','PreToolUse','Stop']:
                enqueue(dict(base,hook_event_name=event,tool_name='Read',tool_input={'file_path':'app.js'}),directory);worker(directory,sent.append)
            enqueue(dict(base,turn_id='old',hook_event_name='PreToolUse',tool_name='Read',tool_input={'file_path':'wrong.js'}),directory);worker(directory,sent.append)
            with contextlib.closing(database(directory)) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM activities').fetchone()[0],0)
