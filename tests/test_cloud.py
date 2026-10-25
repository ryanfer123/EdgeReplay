import json
import tempfile
import unittest
from pathlib import Path
from edge_replay.cloud import cloud_config


class CloudConfigTests(unittest.TestCase):
    def test_missing_config_disables_cloud(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(cloud_config({}, Path(folder) / 'missing.json')['configured'])

    def test_valid_environment_exposes_only_public_values(self):
        config = cloud_config({'SUPABASE_URL': 'https://example.supabase.co/',
                               'SUPABASE_PUBLISHABLE_KEY': 'sb_publishable_example'}, Path('/nonexistent'))
        self.assertTrue(config['configured'])
        self.assertEqual(config['url'], 'https://example.supabase.co')
        self.assertEqual(config['table'], 'edge_replay_cloud_workspaces')
        self.assertEqual(config['maxPayloadBytes'], 8 * 1024 * 1024)

    def test_private_or_unsafe_configuration_fails_closed(self):
        for url, key in [('http://example.supabase.co', 'sb_publishable_example'),
                         ('https://user:pass@example.com', 'sb_publishable_example'),
                         ('https://example.com/path', 'sb_publishable_example'),
                         ('https://example.com?x=y', 'sb_publishable_example'),
                         ('https://example.com', 'sb_secret_private'),
                         ('https://example.com', 'legacy.jwt.token')]:
            with self.subTest(url=url, key=key):
                config = cloud_config({'SUPABASE_URL': url, 'SUPABASE_PUBLISHABLE_KEY': key}, Path('/nonexistent'))
                self.assertFalse(config['configured'])
                self.assertNotIn('publishableKey', config)
                self.assertNotIn(key, json.dumps(config))

    def test_file_configuration_and_environment_override(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'cloud.config.json'
            path.write_text(json.dumps({'SUPABASE_URL': 'https://file.supabase.co',
                                        'SUPABASE_PUBLISHABLE_KEY': 'sb_publishable_file'}))
            self.assertTrue(cloud_config({}, path)['configured'])
            config = cloud_config({'SUPABASE_URL': 'https://env.supabase.co'}, path)
            self.assertEqual(config['url'], 'https://env.supabase.co')
            path.write_text('not json')
            self.assertFalse(cloud_config({}, path)['configured'])
            path.write_text('[]')
            self.assertFalse(cloud_config({}, path)['configured'])

class CloudClientTests(unittest.TestCase):
    def test_browser_client_auth_refresh_and_private_crud(self):
        import shutil
        import subprocess
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node.js is required for browser client protocol tests')
        script = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
vm.runInThisContext(fs.readFileSync(process.argv[1], 'utf8'));
const {Client} = globalThis.CloudWorkspace;
const values = new Map();
const storage = {getItem:k=>values.get(k)||null, setItem:(k,v)=>values.set(k,v), removeItem:k=>values.delete(k)};
const config = {url:'https://example.supabase.co',publishableKey:'sb_publishable_test',table:'private_workspaces',maxPayloadBytes:100};
let calls = [], queue = [];
const request = async (url, opts) => {
  calls.push({url,...opts});
  assert.equal(opts.credentials,'omit');
  assert.equal(opts.headers.apikey, config.publishableKey);
  assert.ok(queue.length, 'unexpected network request');
  const item = queue.shift();
  if(item instanceof Error) throw item;
  return {ok:item[0]>=200&&item[0]<300,status:item[0],text:async()=>typeof item[1]==='string'?item[1]:JSON.stringify(item[1])};
};
const session = {access_token:'access',refresh_token:'refresh',expires_in:3600,user:{id:'user-a',email:'a@example.com'}};
(async()=>{
  const client = new Client(config,{fetch:request,storage});
  await assert.rejects(client.list(),/Sign in/); assert.equal(calls.length,0);
  queue.push([200,{user:{id:'pending'}}]); assert.equal(await client.signUp('new@example.com','password'),false);
  assert.equal(client.session,null);
  queue.push([200,session]); await client.signIn('a@example.com','password');
  assert.match(calls.at(-1).url,/grant_type=password/);
  assert.deepEqual(JSON.parse(calls.at(-1).body),{email:'a@example.com',password:'password'});
  assert.ok([...values.values()][0].includes('refresh')); assert.ok(![...values.values()][0].includes('password'));
  queue.push([200,[]]); assert.deepEqual(await client.list(),[]);
  assert.equal(calls.at(-1).headers.Authorization,'Bearer access');
  assert.match(calls.at(-1).url,/select=id,title,created_at/);
  queue.push([201,'']); await client.save('  saved  ',{x:1});
  assert.deepEqual(JSON.parse(calls.at(-1).body),{title:'saved',payload:{x:1},owner_id:'user-a'});
  await assert.rejects(client.save('x',[]),/No workspace/);
  await assert.rejects(client.save('',{}),/workspace name/);
  await assert.rejects(client.save('x',{text:'x'.repeat(200)}),/8 MiB/);
  const id = '12345678-1234-1234-1234-123456789abc';
  queue.push([200,[{payload:{x:1}}]]); assert.deepEqual(await client.load(id),{x:1});
  queue.push([200,[]]); await assert.rejects(client.load(id),/no longer exists/);
  await assert.rejects(client.load('bad&select=*'),/Invalid workspace/);
  queue.push([204,'']); await client.remove(id); assert.equal(calls.at(-1).method,'DELETE');
  client.session.expires_at=0;
  queue.push([200,{...session,access_token:'renewed'}]);
  const before=calls.length;
  assert.deepEqual(await Promise.all([client.token(),client.token()]),['renewed','renewed']);
  assert.equal(calls.length-before,1); assert.match(calls.at(-1).url,/grant_type=refresh_token/);
  const restored=new Client(config,{fetch:request,storage});assert.equal(restored.session.access_token,'renewed');
  client.session.expires_at=0; queue.push(new Error('offline'));
  await assert.rejects(client.token(),/offline/);assert.ok(client.session,'transient failures preserve refresh token');
  queue.push([400,{message:'invalid refresh'}]);await assert.rejects(client.token(),/invalid refresh/);
  assert.equal(client.session,null);assert.equal(values.size,0);
  client.remember(session);queue.push([401,{message:'expired'}]); await assert.rejects(client.list(),/expired/);assert.equal(client.session,null);
  client.remember(session);queue.push(new Error('offline'));await assert.rejects(client.signOut(),/offline/);assert.equal(values.size,0);assert.equal(client.session,null);
  queue.push([503,'gateway']);await assert.rejects(client.signIn('a','b'),/Cloud request failed/);
  const blocked=new Client(config,{fetch:request,storage:{getItem(){throw Error()},setItem(){throw Error()},removeItem(){throw Error()}}});
  blocked.remember(session);assert.equal(blocked.session.user.id,'user-a');blocked.remember(null);
  values.set(client.storageKey,'invalid JSON');assert.equal(new Client(config,{fetch:request,storage}).session,null);
  assert.equal(queue.length,0);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
        path = Path(__file__).resolve().parents[1] / 'edge_replay' / 'web/cloud.js'
        result = subprocess.run([node, '-e', script, str(path)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
