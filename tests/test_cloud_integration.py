"""Exercise real CSV reconstruction and ordinary server revalidation of cloud copies."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import test_api

from edge_replay.telemetry import parse_trace

ROOT = Path(__file__).resolve().parents[1]


class LocalCloudRoutesTests(unittest.TestCase):
    setUp = test_api.APITests.setUp
    tearDown = test_api.APITests.tearDown
    request = test_api.APITests.request

    def test_home_workspace_and_cloud_assets(self):
        for path in (
            "/",
            "/workspace",
            "/workspace/",
            "/home.css",
            "/home.js",
            "/product-preview.jpg",
            "/cloud.css",
            "/cloud.js",
            "/cloud-adapter.js",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 200)
        self.assertIn(b"Find the moment.", self.request("/")[1])
        workspace = self.request("/workspace")[1]
        self.assertIn(b'id="open-cloud"', workspace)
        self.assertIn(b"/cloud-adapter.js", workspace)
        self.assertNotIn(b"CloudWorkspace.init", self.request("/")[1])

    def test_cloud_config_is_public_local_and_not_cached(self):
        values = {
            "configured": True,
            "url": "https://example.supabase.co",
            "publishableKey": "sb_publishable_test",
            "table": "edge_replay_cloud_workspaces",
            "maxPayloadBytes": 8 * 1024 * 1024,
        }
        with patch("edge_replay.server.cloud_config", return_value=values):
            status, body, headers = self.request("/api/cloud/config")
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["hosted"])
        self.assertEqual(json.loads(body)["publishableKey"], "sb_publishable_test")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn(
            "connect-src 'self' https://example.supabase.co;",
            headers["Content-Security-Policy"],
        )
        self.assertNotIn("https://*", headers["Content-Security-Policy"])

    def test_unconfigured_cloud_keeps_default_csp(self):
        with patch(
            "edge_replay.server.cloud_config", return_value={"configured": False}
        ):
            status, body, headers = self.request("/api/cloud/config")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"configured": False, "hosted": False})
        self.assertIn("connect-src 'self';", headers["Content-Security-Policy"])
        self.assertNotIn("publishableKey", json.loads(body))

    def test_remote_csv_is_revalidated_before_recording_is_saved(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for the real cloud adapter test")
        script = """
const fs=require('node:fs'),vm=require('node:vm');
vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));
const payload=JSON.parse(process.argv[2]);
process.stdout.write(JSON.stringify(EdgeReplayCloudAdapter.restoreInput(payload)));
"""
        payload = {
            "kind": "edge-replay-recording",
            "version": 1,
            "name": "remote",
            "csv": "time_ms,value\n0,nan\n",
        }
        result = subprocess.run(
            [
                node,
                "-e",
                script,
                str(ROOT / "edge_replay/web/cloud-adapter.js"),
                json.dumps(payload),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        status, _, _ = self.request("/api/recordings", json.loads(result.stdout))
        self.assertEqual(status, 400)
        self.assertEqual(
            json.loads(self.request("/api/recordings")[1])["recordings"], []
        )


class RecordingAdapterTests(unittest.TestCase):
    def setUp(self):
        self.node = shutil.which("node")
        if self.node is None:
            self.skipTest("Node.js is required for the real browser adapter test")

    def snapshot(self, recording):
        script = """
const fs=require('node:fs'),vm=require('node:vm');
vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));
process.stdout.write(JSON.stringify(EdgeReplayCloudAdapter.snapshot(JSON.parse(process.argv[2]))));
"""
        result = subprocess.run(
            [
                self.node,
                "-e",
                script,
                str(ROOT / "edge_replay/web/cloud-adapter.js"),
                json.dumps(recording),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)

    def test_signal_snapshot_roundtrip_preserves_labels_and_numeric_values(self):
        original = parse_trace(
            "signals",
            'time_ms,speed_kph,expected_label,predicted_label\n0,12.5,"normal, coasting","normal, coasting"\n500,16.25,"warning ""quoted""",normal\n',
        )
        payload = self.snapshot(original)
        restored = parse_trace(payload["name"], payload["csv"])
        self.assertEqual(restored["rows"], original["rows"])
        self.assertEqual(restored["audit"], original["audit"])
        self.assertEqual(payload["originalSourceSha256"], original["sha256"])
        self.assertNotIn("id", payload)
        self.assertNotIn("rows", payload)

    def test_can_snapshot_roundtrip_retains_raw_frame_order_and_payloads(self):
        original = parse_trace(
            "CAN burst",
            "time_ms,can_id,data_hex\n0,0x300,0000704100002041\n0,0x301,00000c430000803e\n1,0x302,0000003f00000000\n",
        )
        payload = self.snapshot(original)
        restored = parse_trace(payload["name"], payload["csv"])
        self.assertEqual(restored["mode"], "can")
        self.assertEqual(restored["rows"], original["rows"])
        self.assertEqual(restored["channels"], original["channels"])

    def test_unsupported_and_oversized_cloud_copies_are_rejected(self):
        script = """
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));
const a=EdgeReplayCloudAdapter;
assert.throws(()=>a.snapshot(null),/Load a recording/);
for(const bad of [[],null,{}, {kind:'other',version:1}, {kind:'edge-replay-recording',version:2},
 {kind:'edge-replay-recording',version:1,name:'x',csv:''},
 {kind:'edge-replay-recording',version:1,name:'x',csv:'x'.repeat(3*1024*1024+1)}])
 assert.throws(()=>a.restoreInput(bad));
"""
        result = subprocess.run(
            [self.node, "-e", script, str(ROOT / "edge_replay/web/cloud-adapter.js")],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
