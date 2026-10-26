"""A state opens Android UI without killing the independent runtime."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import shlex
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import rux

class RpcRoutingTest(unittest.TestCase):
    def invoke(self,name,logs='OK request=test active=true'):
        with patch.object(rux.uuid,'uuid4',return_value=SimpleNamespace(hex='test')),patch.object(rux,'adb') as launch,patch.object(rux,'adb_base',return_value=['adb']),patch.object(rux.subprocess,'run',return_value=SimpleNamespace(stdout=logs)):
            ack=rux.command(name,'working',context='current')
            return shlex.split(launch.call_args.args[1]),ack
    def test_state_opens_activity_without_force_stopping_service(self):
        args,_=self.invoke('set-state')
        self.assertEqual(args[:2],['am','start'])
        self.assertIn('com.rux.assistant/.MainActivity',args)
        self.assertNotIn('-S',args)
    def test_heartbeat_only_addresses_service(self):
        args,_=self.invoke('heartbeat')
        self.assertEqual(args[:2],['am','start-foreground-service'])
        self.assertIn('com.rux.assistant/.ScenarioService',args)
        self.assertNotIn('com.rux.assistant/.MainActivity',args)
    def test_failure_wins_over_success_in_retained_logs(self):
        with self.assertRaises(RuntimeError):self.invoke('status','OK request=test\nFAILED request=test')
