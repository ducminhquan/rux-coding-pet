import contextlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from chat_hook import ROOT, aggregate, enqueue, transition, worker, database, cached_title

class HooksTest(unittest.TestCase):
    def test_first_tool_after_manual_mode_recovers_current_turn(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);sent=[]
            with contextlib.closing(database(directory)) as db:
                db.execute('INSERT INTO sessions VALUES(?,?,?,?)',('s','old','completed',0))
                db.execute("INSERT INTO meta VALUES('resume_epoch','manual-resume')");db.commit()
            for event in ['PreToolUse','Stop']:
                enqueue(dict(cwd=str(ROOT),session_id='s',turn_id='current',hook_event_name=event),directory)
                worker(directory,sent.append)
            self.assertEqual(sent,['working','completed'])
            with contextlib.closing(database(directory)) as db:
                self.assertEqual(db.execute('SELECT turn,state FROM sessions').fetchone(),('current','completed'))
                episode=json.loads(db.execute("SELECT value FROM meta WHERE key='thinking_episode'").fetchone()[0])
                self.assertEqual(episode,['s','current','completed','manual-resume'])
    def test_late_stop_does_not_end_new_turn(self):
        self.assertEqual(transition('working', 'new', 'old', 'Stop'), 'working')
    def test_permission_then_resume(self):
        state = transition('working', 'a', 'a', 'PermissionRequest')
        self.assertEqual(state, 'attention')
        self.assertEqual(transition(state, 'a', 'a', 'PreToolUse'), 'working')
    def test_running_tool_recovers_waiting_without_a_new_prompt(self):
        for state in ('idle','attention','completed'):
            self.assertEqual(transition(state,'t','t','PreToolUse'),'working')
        self.assertEqual(transition('attention','t','t','PostToolUse'),'working')
        self.assertEqual(transition('completed','t','t','PostToolUse'),'completed')
        self.assertEqual(transition('working','new','old','PreToolUse'),'working')
    def test_automatic_permission_check_never_requests_human_help(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);sent=[]
            base=dict(cwd=str(ROOT),session_id='s',turn_id='t')
            for event in ('UserPromptSubmit','PreToolUse','PermissionRequest','PostToolUse','Stop'):
                enqueue(dict(base,hook_event_name=event),directory);worker(directory,sent.append)
            self.assertEqual(sent,['working','completed'])
            with contextlib.closing(database(directory)) as db:
                self.assertIn(('PermissionCheck',),db.execute('SELECT event FROM events').fetchall())
    def test_blocking_question_waits_until_tool_returns(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);sent=[]
            base=dict(cwd=str(ROOT),session_id='s',turn_id='t',tool_name='functions.request_user_input')
            for event in ('UserPromptSubmit','PreToolUse','PostToolUse'):
                enqueue(dict(base,hook_event_name=event),directory);worker(directory,sent.append)
            self.assertEqual(sent,['working','attention','working'])
    def test_other_busy_chat_takes_priority(self):
        self.assertEqual(aggregate(['working', 'completed']), 'working')
        self.assertEqual(aggregate(['attention', 'working']), 'attention')
    def test_queue_deduplicates_across_workers_and_drops_content(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            sent = []
            base = dict(cwd=str(ROOT), session_id='test', turn_id='t', prompt='SECRET', tool_input='SECRET')
            for event in ['UserPromptSubmit', 'PreToolUse', 'PermissionRequest', 'PreToolUse', 'Stop']:
                self.assertTrue(enqueue(dict(base, hook_event_name=event), directory))
                worker(directory, sent.append)
            self.assertEqual(sent, ['working', 'completed'])
            with contextlib.closing(database(directory)) as db:
                rows = db.execute('SELECT * FROM events').fetchall()
            self.assertNotIn('SECRET', repr(rows))
            self.assertTrue(all(row[5] == 'delivered' for row in rows))
    def test_delivery_failure_is_recorded(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            enqueue(dict(cwd=str(ROOT), session_id='test', hook_event_name='UserPromptSubmit'), directory)
            def fail(state): raise RuntimeError('USB disconnected')
            worker(directory, fail)
            with contextlib.closing(database(directory)) as db:
                self.assertEqual(db.execute('SELECT status FROM events').fetchone()[0], 'failed')
    def test_wrong_project_ignored(self):
        self.assertFalse(enqueue(dict(cwd='/tmp/elsewhere', session_id='x', hook_event_name='Stop')))

    def test_cached_title_failure_keeps_previous_name(self):
        with tempfile.TemporaryDirectory() as temp:
            with contextlib.closing(database(Path(temp))) as db:
                db.execute('INSERT INTO titles VALUES(?,?,?)', ('s', 'Tên chat', 0))
                def unavailable(session): raise RuntimeError('metadata unavailable')
                self.assertEqual(cached_title(db, 's', unavailable), 'Tên chat')

    def test_session_switch_updates_display_even_if_same_state(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            sent = []
            for session in ['first', 'second']:
                enqueue(dict(cwd=str(ROOT), session_id=session, turn_id='t', hook_event_name='UserPromptSubmit'), directory)
                worker(directory, sent.append, lambda ident: 'Tên ' + ident)
            self.assertEqual(sent, ['working', 'working'])
            with contextlib.closing(database(directory)) as db:
                display = json.loads(db.execute("SELECT value FROM meta WHERE key='last_display'").fetchone()[0])
            self.assertEqual(display, ['working', 'second', 'Tên second'])

    def test_completed_chat_cannot_replace_busy_chat_title(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            sent = []
            for session, event in [('busy', 'UserPromptSubmit'), ('other', 'UserPromptSubmit'), ('other', 'Stop')]:
                enqueue(dict(cwd=str(ROOT), session_id=session, turn_id='t', hook_event_name=event), directory)
                worker(directory, sent.append, lambda ident: 'Tên ' + ident)
            with contextlib.closing(database(directory)) as db:
                display = json.loads(db.execute("SELECT value FROM meta WHERE key='last_display'").fetchone()[0])
            self.assertEqual(display, ['working', 'busy', 'Tên busy'])

if __name__ == '__main__': unittest.main()
