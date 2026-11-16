const assert=require('node:assert/strict');
const test=require('node:test');
const launcher=require('../../pinokio.js');
test('running menu embeds Foundry on the same site as Pinokio Desktop',async()=>{
  const menu=await launcher.menu({}, {
    exists:()=>true, running:script=>script==='start.js',
    local:()=>({url:'http://127.0.0.1:49226'})
  });
  assert.equal(menu[0].href,'http://localhost:49226/mumblebox-foundry/');
  assert.equal(menu[0].default,true);
  assert.equal(menu[0].target,undefined);
  assert.equal(menu.find(item=>item.text==='Update')?.href,'update.js');
});

test('reopening Foundry during an update cannot run the updater again',async()=>{
  for(const starting of [false,true]){
    const menu=await launcher.menu({}, {
      exists:()=>true,
      running:script=>script==='update.js'||(starting&&script==='start.js'),
      local:()=>({}),
    });
    assert.ok(menu.some(item=>item.text==='Updating Foundry'));
    assert.equal(menu.some(item=>item.href==='update.js'),false);
    assert.equal(menu.some(item=>item.default),false);
  }
});

test('start hands Pinokio the ready workspace URL and opens it in the launcher',async()=>{
  const start=require('../../start.js');
  const launch=start.run[0].params.on.find(rule=>rule.done);
  const origin='http://127.0.0.1:49226';
  const workspace='http://localhost:49226/mumblebox-foundry/?version=0.1.0-preview.33';
  const ready=new RegExp(launch.event.slice(1,-1)).exec(`Foundry ready: ${origin} ${workspace}`);
  assert.deepEqual(ready?.slice(1),[origin,workspace]);
  assert.deepEqual(start.run[1],{
    method:'local.set',
    params:{url:'{{input.event[1]}}',workspace:'{{input.event[2]}}'},
  });
  assert.deepEqual(start.run[2],{
    method:'web.open',
    params:{uri:'{{cwd}}',target:'_top'},
  });
  for(const updating of [true,false]){
    const menu=await launcher.menu({}, {
      exists:()=>true,
      running:script=>script==='start.js'||(updating&&script==='update.js'),
      local:()=>({url:origin,workspace}),
    });
    assert.deepEqual(menu.filter(item=>item.default).map(item=>item.href),[workspace]);
    assert.equal(menu.some(item=>item.href==='update.js'),!updating);
  }
});

test('updater checks jobs before stopping and restarts after installing',()=>{
  const update=require('../../update.js');
  assert.match(update.run[0].params.message,/check-idle/);
  assert.match(update.run[1].params.message,/stop-owned/);
  assert.equal(update.run[2].method,'script.stop');
  assert.equal(update.run[2].params.uri,require('path').resolve(__dirname,'../../start.js'));
  assert.match(update.run[3].params.message,/maintenance.py update/);
  assert.equal(update.run[4].method,'script.start');
  assert.equal(update.run[4].params.uri,update.run[2].params.uri);
});
test('installer reuses an existing launcher environment',()=>{
  const install=require('../../install.js');
  assert.match(install.run[0].when,/!exists.*launcher-env\/Scripts\/python.exe/);
  assert.doesNotMatch(JSON.stringify(install),/--clear|UV_VENV_CLEAR/);
});
