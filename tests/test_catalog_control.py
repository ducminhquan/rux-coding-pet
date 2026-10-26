import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import catalog_server as server

class CatalogControlTest(unittest.TestCase):
    def test_valid_ear_and_foot_preview(self):
        spec=server.validate_preview({'face':'working','motion':24,'ears':1,'angle':20})
        self.assertEqual(spec['steps'],1)
    def test_pair_preview_preserves_order(self):
        spec=server.validate_preview({'motion':24,'motion2':20})
        self.assertEqual((spec['motion'],spec['motion2']),(24,20))
        self.assertEqual(server.validate_preview({})['motion2'],0)
    def test_rejects_unknown_commands_and_fields(self):
        for body in [{'motion2':81},{'motion2':True},{'motion2':-1},{'motion':81},{'ears':4},{'angle':0},{'angle':46},{'steps':3},{'duration_ms':9000},{'face':'$(anything)'},{'shell':'adb shell'}]:
            with self.assertRaises(ValueError):server.validate_preview(body)
    def test_voice_selection_only_accepts_catalog_ids(self):
        self.assertEqual(server.validate_voice({'voice':'diem-my'})['asset'],'voice-diem-my.wav')
        for body in [{'voice':'../secret'}, {'voice':'diem-my','asset':'anything.wav'}, {'voice':True}]:
            with self.assertRaises(ValueError):server.validate_voice(body)
    def test_voice_worker_uses_audio_command(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(server,'DATA',Path(temp)):
            server.CANCEL.clear()
            with patch.object(server,'web_control_active',return_value=True),patch.object(server,'command') as send:
                server.execute(server.validate_voice({'voice':'phuong-ly'}))
                self.assertEqual(send.call_args.args,('audio','voice-phuong-ly.wav'))
                self.assertEqual(server.STATE['result'],'done')
    def test_radar_cmd_three_and_light_colors(self):
        self.assertEqual(server.validate_preview({'ears':3})['ears'],3)
        for color in range(9):self.assertEqual(server.validate_preview({'light':color})['light'],color)
        self.assertEqual(server.validate_preview({})['light'],-1)
        for color in [-2,9,True,'red']:
            with self.assertRaises(ValueError):server.validate_preview({'light':color})
    def test_boolean_is_not_a_motor_number(self):
        with self.assertRaises(ValueError):server.validate_preview({'motion':True})
    def test_rejected_sync_keeps_local_applied_configuration(self):
        import scenario
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'config.json';path.write_text('previous')
            with patch.object(scenario,'CONFIG',path),patch.object(server,'DATA',Path(temp)),patch.object(scenario,'sync',side_effect=RuntimeError('device rejected')):
                with self.assertRaises(RuntimeError):server.apply_scenario(scenario.load())
            self.assertEqual(path.read_text(),'previous')
    def test_worker_transfers_only_canonical_base64_spec(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(server,'DATA',Path(temp)):
            server.lease();server.CANCEL.clear()
            with patch.object(server,'web_control_active',return_value=True),patch.object(server,'command') as send:
                spec=server.validate_preview({'motion':24})
                server.execute(spec)
                args=send.call_args.args
                self.assertEqual(args[0],'preview')
                self.assertEqual(json.loads(base64.b64decode(args[1])),spec)
                self.assertEqual(server.STATE['result'],'done')
    def test_cancelled_job_never_sends_movement(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(server,'DATA',Path(temp)):
            server.lease();server.CANCEL.set()
            with patch.object(server,'command') as send:
                server.execute(server.validate_preview({'motion':24}))
                send.assert_not_called()
                self.assertEqual(server.STATE['result'],'stopped')
            server.CANCEL.clear()

if __name__=='__main__':unittest.main()
