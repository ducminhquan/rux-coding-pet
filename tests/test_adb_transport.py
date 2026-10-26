import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import rux

class TransportTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'transport.json'
    def tearDown(self):self.temp.cleanup()
    def base(self,env=None):
        with patch.object(rux,'TRANSPORT_FILE',self.path),patch.dict(os.environ,env or {},clear=True):
            return rux.adb_base()
    def test_install_explicitly_disables_incremental(self):
        # Old robot firmware can panic after restoring a failed IncFS session.
        with patch.object(sys, 'argv', ['rux.py', 'install']), patch.object(rux, 'adb') as invoke:
            rux.main()
        invoke.assert_called_once_with('install', '--no-incremental', '-r', str(rux.ROOT / 'build/rux-assistant.apk'))
    def test_saved_wireless_device_is_selected(self):
        self.path.write_text(json.dumps({'serial':'192.0.2.48:5555'}))
        self.assertEqual(self.base(),['adb','-s','192.0.2.48:5555'])
    def test_explicit_env_takes_priority(self):
        self.path.write_text(json.dumps({'serial':'192.0.2.48:5555'}))
        self.assertEqual(self.base({'RUX_SERIAL':'USB123'}),['adb','-s','USB123'])
    def test_bad_config_does_not_fall_back_to_other_devices(self):
        self.path.write_text('broken')
        with self.assertRaises(RuntimeError):self.base()
    def test_missing_config_preserves_default(self):
        self.assertEqual(self.base(),['adb'])
    def test_rejects_invalid_selector(self):
        self.path.write_text(json.dumps({'serial':'invalid serial'}))
        with self.assertRaises(RuntimeError):self.base()

if __name__=='__main__':unittest.main()
