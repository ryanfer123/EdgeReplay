import math
from pathlib import Path
import struct
import unittest

from edge_replay.telemetry import decode_can,label_audit,parse_trace


class TraceTests(unittest.TestCase):
    def test_signal_summary(self):
        trace=parse_trace('drive','time_ms,speed_kph\n0,10\n500,30\n')
        self.assertEqual(trace['duration_ms'],500)
        self.assertEqual(trace['channels'][0]['mean'],20)
        self.assertEqual(trace['interval_ms'],{'min':500,'max':500})
        self.assertIsNone(trace['audit']['accuracy'])

    def test_all_driver_frame_positions(self):
        cases=[('0x300',(17,12),{'throttle_variation':17,'brake_usage_pct':12}),
               ('301',(145,.25),{'energy_wh_km':145,'regen_efficiency':.25}),
               ('0x302',(.5,0),{'jerk_m_s3':.5})]
        for identifier,values,expected in cases:
            with self.subTest(identifier=identifier):
                self.assertEqual(decode_can(identifier,struct.pack('<ff',*values).hex()),expected)

    def test_payload_errors(self):
        for identifier,payload in [('0x999','0000000000000000'),('0x300','00'),('not-id','0000000000000000'),('0x300','z'*16),('0x300',struct.pack('<ff',math.nan,0).hex())]:
            with self.subTest(payload=payload),self.assertRaises(ValueError):
                decode_can(identifier,payload)

    def test_can_carries_forward_values_and_exposes_age(self):
        first=struct.pack('<ff',15,10).hex();second=struct.pack('<ff',140,.25).hex()
        trace=parse_trace('bus',f'time_ms,can_id,data_hex\n0,0x300,{first}\n5,0x301,{second}\n')
        self.assertEqual(trace['rows'][1]['values']['throttle_variation'],15)
        self.assertEqual(trace['rows'][1]['frame']['age_ms']['throttle_variation'],5)
        self.assertNotIn('energy_wh_km',trace['rows'][0]['values'])

    def test_labels_are_compared_only_when_both_exist(self):
        trace=parse_trace('predictions','time_ms,temp,expected_label,predicted_label\n0,20,normal,normal\n1,22,normal,warning\n2,24,,warning\n')
        self.assertEqual(trace['audit']['compared'],2)
        self.assertEqual(trace['audit']['accuracy'],.5)
        self.assertEqual(trace['audit']['mismatches'][0]['time_ms'],1)

    def test_declared_ranges_warn_without_dropping_values(self):
        trace=parse_trace('units','time_ms,regen_efficiency\n0,25\n')
        self.assertEqual(len(trace['warnings']),1)
        self.assertEqual(trace['rows'][0]['values']['regen_efficiency'],25)

    def test_invalid_recordings_are_rejected(self):
        cases=['time_ms,speed\n0,nan\n','time_ms,speed\n0,inf\n','time_ms,speed\n-1,10\n',
               'time_ms,speed\n0,1\n0,2\n','time_ms,speed\n2,1\n1,2\n','time_ms,speed\n0,1,2\n',
               'time_ms,speed\n0\n','time_ms,speed,speed\n0,1,2\n','time_ms,speed\n','speed\n1\n']
        for content in cases:
            with self.subTest(content=content),self.assertRaises(ValueError):
                parse_trace('bad',content)

    def test_bom_and_quoted_csv(self):
        self.assertEqual(parse_trace('ok','\ufefftime_ms,value\n0,"1.5"\n')['rows'][0]['values']['value'],1.5)

    def test_source_hash_is_reproducible(self):
        content='time_ms,value\n0,1\n'
        self.assertEqual(parse_trace('one',content)['sha256'],parse_trace('two',content)['sha256'])

    def test_bundled_fixtures_validate(self):
        for path in (Path(__file__).parents[1]/'edge_replay/web').glob('*.csv'):
            with self.subTest(path=path):
                self.assertTrue(parse_trace(path.stem,path.read_text())['rows'])

    def test_can_frames_with_equal_timestamps_keep_source_order(self):
        a=struct.pack('<ff',15,10).hex();b=struct.pack('<ff',140,.25).hex()
        trace=parse_trace('burst',f'time_ms,can_id,data_hex\n0,0x300,{a}\n0,0x301,{b}\n')
        self.assertEqual(len(trace['rows']),2)
        self.assertEqual(trace['rows'][0]['frame']['can_id'],'0x300')
        self.assertEqual(trace['rows'][1]['frame']['can_id'],'0x301')
        self.assertEqual(trace['rows'][1]['frame']['age_ms']['throttle_variation'],0)
