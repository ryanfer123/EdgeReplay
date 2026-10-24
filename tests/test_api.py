import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from edge_replay.server import make_server


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Path(self.temp.name)/'test.sqlite3'
        self.server=make_server(0,self.db)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def request(self,path,data=None,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        c.request('POST' if data is not None else 'GET',path,json.dumps(data) if data is not None else None,
                  headers or {'Content-Type':'application/json'})
        r=c.getresponse();body=r.read();result=(r.status,body,dict(r.getheaders()));c.close();return result

    def test_import_inspect_list_export(self):
        status,body,_=self.request('/api/recordings',{'name':'test','csv':'time_ms,value\n0,1\n10,2\n'})
        self.assertEqual(status,201);recording=json.loads(body)
        self.assertEqual(len(json.loads(self.request('/api/recordings')[1])['recordings']),1)
        self.assertEqual(json.loads(self.request('/api/recordings/'+recording['id'])[1]),recording)
        status,body,headers=self.request('/api/recordings/'+recording['id']+'?download=1')
        self.assertIn('attachment;',headers['Content-Disposition']);self.assertEqual(json.loads(body),recording)
        status,body,headers=self.request('/api/recordings/'+recording['id']+'?format=csv')
        self.assertIn(b'time_ms,value',body);self.assertTrue(headers['Content-Type'].startswith('text/csv'))

    def test_invalid_import_is_not_persisted(self):
        self.assertEqual(self.request('/api/recordings',{'name':'x','csv':'bad'})[0],400)
        self.assertEqual(json.loads(self.request('/api/recordings')[1])['recordings'],[])

    def test_missing_recording(self):
        self.assertEqual(self.request('/api/recordings/no-such-recording')[0],404)

    def test_origin_host_and_content_type(self):
        self.assertEqual(self.request('/api/recordings',{}, {'Content-Type':'application/json','Origin':'https://example.com'})[0],403)
        self.assertEqual(self.request('/api/recordings',headers={'Host':'example.com'})[0],403)
        self.assertEqual(self.request('/api/recordings',{}, {'Content-Type':'text/plain'})[0],400)

    def test_private_files_are_not_served(self):
        for path in ('/server.py','/../server.py','/edge-replay.sqlite3','/vendor/../../server.py'):
            self.assertEqual(self.request(path)[0],404)

    def test_static_assets(self):
        for path in ('/demo.csv','/example-can.csv','/vendor/gsap.min.js'):
            self.assertEqual(self.request(path)[0],200)
