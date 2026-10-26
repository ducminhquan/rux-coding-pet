import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import chat_hook
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from chat_hook import database, heartbeat_tick

class ThinkingTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.directory=Path(self.temp.name)
        self.db=database(self.directory)
        self.db.execute('INSERT INTO sessions VALUES(?,?,?,?)',('s','t','working',1000))
        for key,value in {'last_display':json.dumps(['working','s','Tên task']),
                          'thinking_episode':json.dumps(['s','t','working']),
                          'thinking_started_at':'1000'}.items():
            self.db.execute('INSERT INTO meta VALUES(?,?)',(key,value))
        self.db.commit()
        self.sent=[]
    def tearDown(self):
        self.db.close();self.temp.cleanup()
    def tick(self,now=1000,deliver=None):
        return heartbeat_tick(self.directory,deliver or (lambda *args:self.sent.append(args)),now)
    def test_only_renews_lease_every_fifteen_seconds(self):
        self.assertEqual(self.tick(),'heartbeat')
        self.assertEqual(self.tick(1014),'waiting')
        self.assertEqual(self.tick(1015),'heartbeat')
        self.assertEqual(self.sent,[(json.dumps(['s','t','working']),)]*2)
    def test_attention_heartbeats_do_not_follow_motion_cadence(self):
        self.db.execute("UPDATE sessions SET state='attention'")
        changes={'last_display':json.dumps(['attention','s','Tên task']),
                 'thinking_episode':json.dumps(['s','t','attention']),
                 'last_heartbeat_at':'1000'}
        for key,value in changes.items():self.db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(key,value))
        self.db.commit()
        self.assertEqual(self.tick(1014),'waiting')
        self.assertEqual(self.tick(1015),'heartbeat')
    def test_stops_when_session_stops(self):
        self.db.execute("UPDATE sessions SET state='completed'");self.db.commit()
        self.assertEqual(self.tick(),'stop')
        self.assertFalse(self.sent)
    def test_pending_chat_event_has_priority(self):
        self.db.execute("INSERT INTO events(at,session,turn,event) VALUES(1000,'s','t','Stop')");self.db.commit()
        self.assertEqual(self.tick(),'waiting')
    def test_manual_resume_context_is_renewed_without_replaying_motion(self):
        episode=json.dumps(['s','t','working','manual-resume'])
        self.db.execute("UPDATE meta SET value=? WHERE key='thinking_episode'",(episode,));self.db.commit()
        self.assertEqual(self.tick(),'heartbeat')
        self.assertEqual(self.sent,[(episode,)])
    def test_long_thinking_heartbeat_has_no_duration_limit(self):
        self.assertEqual(self.tick(1300),'heartbeat')
        self.assertEqual(self.tick(1000+7200),'heartbeat')
    def test_motion_off_switch(self):
        (self.directory/'motion-disabled').touch()
        self.assertEqual(self.tick(),'stop')
    def test_failed_tick_stops_same_episode(self):
        def fail(*args):raise RuntimeError('USB disconnected')
        self.assertEqual(self.tick(deliver=fail),'failed')
        self.assertEqual(self.tick(1025),'stop')
        self.assertFalse(self.sent)
    def test_turn_change_invalidates_old_episode(self):
        self.db.execute("UPDATE sessions SET turn='next'");self.db.commit()
        self.assertEqual(self.tick(),'stop')

if __name__=='__main__':unittest.main()
