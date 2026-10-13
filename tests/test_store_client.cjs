// Run with node --test tests/test_store_client.cjs (no npm dependencies).
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('src/artoo/libraries/kit/assets/store.js', 'utf8');
function harness(shared = new Map(), browser = new Map()) {
  let fail = false, loseAck = false, counter = 0;
  const window = {
    location: {href:'https://reader.test/a/repo/artifact/nested/view.html',origin:'https://reader.test',protocol:'https:'},
    document: {currentScript:{src:'https://reader.test/a/repo/artifact/lib/artoo-kit/store.js'},querySelector:()=>null},
    localStorage: {getItem:k=>browser.get(k)??null,setItem:(k,v)=>browser.set(k,v),removeItem:k=>browser.delete(k),key:i=>[...browser.keys()][i],get length(){return browser.size;}},
    fetch: async (url, options) => {
      if(fail) throw Error('offline');
      assert.match(url,/^https:\/\/reader.test\/a\/repo\/artifact\/_artoo\/state\/feedback/);
      const name = url.split('/').at(-1);
      const reply = (status,data)=>({ok:status<400,status,json:async()=>data});
      if(name==='feedback') return reply(200,{protocol:2,durable:true,entries:[]});
      const current=shared.get(name);
      if(options.method==='GET') return current?reply(200,current):reply(404,{});
      const body=JSON.parse(options.body);
      if(body.expected_revision !== (current?.revision??null)) return reply(409,{current_revision:current?.revision});
      const result={document:body.document,revision:`r${++counter}-${Date.now()}`,git_committed:false};
      if(options.method==='DELETE') shared.delete(name); else shared.set(name,result);
      if(loseAck){loseAck=false;throw Error('connection lost after disk write');}
      return reply(options.method==='DELETE'?204:200,result);
    }
  };
  vm.runInNewContext(source,{window,URL});
  return {store:window.ArtooStore.open('feedback'),window,browser,shared,offline:v=>fail=v,loseAck:()=>loseAck=true};
}
test('load required; shared save readable in independent browser; no Git claim',async()=>{
 const a=harness(); await assert.rejects(a.store.save('review',{n:1}),/Load/);
 assert.equal(await a.store.load('review'),null);
 const saved=await a.store.save('review',{n:1}); assert.equal(saved.git_committed,false);
 const b=harness(a.shared); assert.equal((await b.store.load('review')).n,1);
 assert.equal(a.store.inspectPending('review'),null);
});
test('stale browser conflicts without overwriting; explicit recovery keeps original revision',async()=>{
 const a=harness(),b=harness(a.shared); await a.store.load('review'); await b.store.load('review');
 await a.store.save('review',{n:1}); await assert.rejects(b.store.save('review',{n:2}),e=>e.status===409);
 assert.equal(b.store.inspectPending('review').body.document.n,2);
 await b.store.load('review'); await assert.rejects(b.store.recoverPending('review'),e=>e.status===409);
 assert.equal(a.shared.get('review').document.n,1);
});
test('offline save retained across reload and recoverable; service failures never silently fall back',async()=>{
 const a=harness();await a.store.load('review');a.offline(true);
 await assert.rejects(a.store.save('review',{n:2}),/offline/);assert.equal(a.store.status,'unsaved');
 assert.equal(a.store.inspectLocal('review'),null);
 const b=harness(a.shared,a.browser);await b.store.load('review');await b.store.recoverPending('review');
 assert.equal(b.shared.get('review').document.n,2);
 const c=harness();c.offline(true);await assert.rejects(c.store.load('review'),/offline/);
});
test('lost acknowledgement cannot duplicate or overwrite a committed save',async()=>{
 const a=harness();await a.store.load('review');a.loseAck();
 await assert.rejects(a.store.save('review',{n:4}));
 const b=harness(a.shared,a.browser);assert.equal((await b.store.load('review')).n,4);
 await assert.rejects(b.store.recoverPending('review'),e=>e.status===409);
 assert.equal(b.store.inspectPending('review').body.document.n,4);
});
test('import requires reviewed document and preserves legacy browser copy',async()=>{
 const a=harness();a.browser.set('artoo:state:feedback:review',JSON.stringify({legacy:true}));
 await a.store.load('review');await assert.rejects(a.store.importLocal('review'),/Compare/);
 await a.store.importLocal('review',{confirm:true,document:{legacy:true,merged:true}});
 assert.equal(a.store.inspectLocal('review').document.legacy,true);
 assert.equal(a.shared.get('review').document.merged,true);
});
test('explicit local mode and cross-origin refusal',async()=>{
 const a=harness();assert.throws(()=>a.window.ArtooStore.open('feedback',{base:'https://evil.test/state'}),/same-origin/);
 const local=a.window.ArtooStore.open('feedback',{localOnly:true});await local.load('review');
 assert.equal((await local.save('review',{n:1})).durable,false);
});

test('pending merge replaces journal atomically and uses freshly loaded revision',async()=>{
 const a=harness(),b=harness(a.shared);await a.store.load('review');await b.store.load('review');
 await a.store.save('review',{n:1});await assert.rejects(b.store.save('review',{n:2}));
 await b.store.load('review');await b.store.resolvePending('review',{confirm:true,document:{n:3}});
 assert.equal(b.shared.get('review').document.n,3);assert.equal(b.store.inspectPending('review'),null);
});

test('successful ack cannot remove a different tab pending journal',async()=>{
 const a=harness(),b=harness(a.shared,a.browser);await a.store.load('review');await b.store.load('review');
 let release,started;
 const start=new Promise(r=>started=r),gate=new Promise(r=>release=r);
 const original=a.window.fetch;
 a.window.fetch=async(u,o)=>{const response=await original(u,o);if(o.method==='PUT'){started();await gate;}return response;};
 const saving=a.store.save('review',{n:1});await start;
 // Emulate the other tab's interleaved, already-started operation after its initial check.
 const pending={method:'PUT',created:new Date().toISOString(),body:{document:{n:2},expected_revision:null}};
 await assert.rejects(b.store._write('review',pending,true),e=>e.status===409);
 release();await saving;
 assert.equal(b.store.listPending('review').length,1);
 assert.equal(b.store.inspectPending('review').body.document.n,2);
});
