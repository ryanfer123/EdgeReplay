"""Exercise the actual serverless handler over HTTP; no database and no live remote calls."""
import importlib.util
import json
from pathlib import Path
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hosted_api', ROOT / 'api/index.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class HostedAPITests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), api.handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def request(self, path, value=None, **headers):
        req = Request(self.url + path, data=None if value is None else json.dumps(value).encode(),
                      headers={'Content-Type':'application/json', **headers})
        try:
            with urlopen(req) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            with error:
                return error.code, json.load(error)

    def test_health_configuration_and_rewrite_route(self):
        self.assertEqual(self.request('/api/health')[0], 200)
        status, config = self.request('/api/index.py?route=cloud/config')
        self.assertEqual(status, 200); self.assertTrue(config['hosted'])
        self.assertEqual(self.request('/api/unknown')[0], 404)

    def test_rejects_invalid_envelopes_and_cross_origin(self):
        self.assertEqual(self.request('/api/unknown', [1])[0], 400)
        self.assertEqual(self.request('/api/unknown', {}, Origin='https://foreign.example')[0], 403)

    def test_stateless_real_csv_validation(self):
        csv = (ROOT / 'edge_replay/web/demo.csv').read_text()
        status, record = self.request('/api/recordings', {'name':'demo.csv','csv':csv})
        self.assertEqual(status, 201); self.assertGreater(len(record['rows']), 1)
        self.assertEqual(self.request('/api/recordings')[1]['recordings'], [])
        self.assertEqual(self.request('/api/recordings', {'name':'broken','csv':'bad'})[0], 400)


class HostedBrowserTests(unittest.TestCase):
    def test_real_browser_adapter_session_and_compute_protocol(self):
        import shutil
        import subprocess
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node.js is required for browser adapter checks')
        script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const kind=process.argv[2], code=fs.readFileSync(process.argv[1],'utf8');
const store=new Map(),calls=[],responses=[];
function boot(){
 const context={URL,Request,Response,location:{origin:'https://example.test'},sessionStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)},document:{addEventListener(){} ,getElementById(){return null}},fetch:async(input,opts)=>{calls.push({input,opts});assert.ok(responses.length,'unexpected network');return new Response(JSON.stringify(responses.shift()),{status:200})},setTimeout};
 vm.createContext(context);vm.runInContext(code,context);return context;
}
(async()=>{
 let context=boot();const id='record-id';
 if(kind==='RetrievalLab'){
  let value=await(await context.fetch('/api/state')).json();assert.equal(value.datasets.length,0);
  const dataset={id,name:'Corpus',documents:[],queries:[]};responses.push(dataset);
  await context.fetch('/api/datasets',{method:'POST',body:JSON.stringify({name:'Corpus'})});
  responses.push({id:'run-id',dataset,created:'2026-01-01',results:{k:3,methods:{}}});
  await context.fetch('/api/runs',{method:'POST',body:JSON.stringify({dataset_id:id,k:3})});
  assert.equal(JSON.parse(calls.at(-1).opts.body).dataset.id,id);
  value=await(await context.fetch('/api/runs/run-id')).json();assert.equal(value.results.k,3);
  context=boot();value=await(await context.fetch('/api/state')).json();assert.equal(value.runs.length,1);
 }else if(kind==='EdgeReplay'){
  const record={id,name:'Trace',mode:'signals',channels:[],rows:[]};responses.push(record);
  await context.fetch('/api/recordings',{method:'POST',body:JSON.stringify({name:'Trace',csv:'original,csv\n1,2\n'})});
  const csv=await(await context.fetch('/api/recordings/'+id+'?format=csv')).text();assert.equal(csv,'original,csv\n1,2\n');
  context=boot();assert.equal((await(await context.fetch('/api/recordings')).json()).recordings.length,1);
 }else{
  responses.push({catalog:{layers:[],verified:'2026-01-01'},investigations:[]});
  await context.fetch('/api/state');
  const record={id,spec:{name:'Study',bounds:[0,0,1,1],notes:'observed',before:'2001',after:'2023'},sources:{before:{url:'https://gibs.earthdata.nasa.gov/a'},after:{url:'https://gibs.earthdata.nasa.gov/b'}}};
  responses.push(record);await context.fetch('/api/investigations',{method:'POST',body:'{}'});
  assert.match(await(await context.fetch('/api/export/'+id+'?format=md')).text(),/observed/);
  assert.equal(context.HostedWorkspace.imageSource(record.sources.before),record.sources.before.url);
 }
 // Cloud authentication stays a direct external request, never a local cache operation.
 responses.push({ok:true});await context.fetch('https://project.supabase.co/auth/v1/token',{method:'POST',body:'{}'});
 assert.equal(calls.at(-1).input,'https://project.supabase.co/auth/v1/token');
 store.set('hosted:'+kind+':v1','{"datasets":7}');context=boot();
 if(kind==='GeoTrace')responses.push({catalog:{layers:[]},investigations:[]});
 const state=await(await context.fetch(kind==='EdgeReplay'?'/api/recordings':'/api/state')).json();
 assert.equal((state.datasets||state.recordings||state.investigations).length,0);
 assert.equal(responses.length,0);
})().catch(error=>{console.error(error);process.exitCode=1});
'''
        result = subprocess.run([node, '-e', script, str(ROOT / 'edge_replay/web/hosted.js'), 'EdgeReplay'], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

if __name__ == '__main__':
    unittest.main()
