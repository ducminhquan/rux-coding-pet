import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import scenario

class ScenarioTest(unittest.TestCase):
    def test_user_choices(self):
        config=scenario.load()
        self.assertEqual(config['voice'],'thuy-duyen')
        self.assertEqual([config['states'][s]['motion'] for s in scenario.STATES],[7,32,59,20,27])
        self.assertEqual([scenario.interval(s) for s in scenario.STATES],[30,30,0,0,20])
    def test_state_payload_is_compact_and_keeps_context(self):
        with patch('rux.command') as send:
            scenario.dispatch('attention','Tên chat',True,True,context='turn1')
        self.assertEqual(send.call_args.args,('set-state','attention'))
        self.assertEqual(send.call_args.kwargs['context'],'turn1')
        self.assertTrue(send.call_args.kwargs['quiet'])
        self.assertFalse(send.call_args.kwargs['no_motion'])
    def test_suppressed_movement_still_updates_state(self):
        with patch('rux.command') as send:scenario.dispatch('working',move=False)
        self.assertTrue(send.call_args.kwargs['no_motion'])
    def test_explicit_sync_transfers_validated_configuration(self):
        with patch('rux.command') as send:scenario.sync()
        self.assertEqual(send.call_args.args[0],'configure')
        self.assertEqual(json.loads(base64.b64decode(send.call_args.args[1])),scenario.load())
    def test_heartbeat_has_no_motion_or_state_payload(self):
        with patch('rux.command') as send:scenario.heartbeat('turn1')
        self.assertEqual(send.call_args.args,('heartbeat',))
        self.assertEqual(send.call_args.kwargs,{'context':'turn1'})
    def test_rejects_tight_repeat_and_out_of_bounds_motion(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'scenario.json'
            for field,value in [('repeat',1),('motion',81),('motion2',81),('motion2',True),('angle',90)]:
                config=scenario.load();config['states']['working'][field]=value
                path.write_text(json.dumps(config))
                with self.assertRaises(ValueError):scenario.load(path)

    def test_legacy_config_defaults_to_no_second_action(self):
        config=scenario.load()
        for spec in config['states'].values():spec.pop('motion2',None)
        checked=scenario.validate(config)
        self.assertTrue(all(s['motion2']==0 for s in checked['states'].values()))
    def test_second_action_survives_sync(self):
        config=scenario.load();config['states']['working']['motion2']=20
        with patch('rux.command') as send:scenario.sync(config)
        self.assertEqual(json.loads(base64.b64decode(send.call_args.args[1]))['states']['working']['motion2'],20)
