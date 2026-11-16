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

test('start hands Pinokio a complete workspace URL without reopening the project',async()=>{
  const start=require('../../start.js');
  const launch=start.run[0].params.on.find(rule=>rule.done);
  const origin='http://127.0.0.1:49226';
  const workspace='http://localhost:49226/mumblebox-foundry/?version=0.1.0-preview.33';
  const readyPattern=new RegExp(launch.event.slice(1,-1));
  assert.equal(readyPattern.exec(`Foundry ready: ${origin} ${workspace.slice(0,-1)}`),null);
  const ready=readyPattern.exec(`Foundry ready: ${origin} ${workspace} [ready]`);
  assert.deepEqual(ready?.slice(1),[origin,workspace]);
  assert.deepEqual(start.run[1],{
    method:'local.set',
    params:{url:'{{input.event[1]}}',workspace:'{{input.event[2]}}'},
  });
  assert.equal(start.run.some(step=>step.method==='web.open'),false);
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

test('updater reports current without restarting and restarts a newly installed release',()=>{
  const update=require('../../update.js');
  const [maintenance,storeResult,...actions]=update.run;
  assert.match(maintenance.params.message,/maintenance.py update/);
  const resultPattern=new RegExp(maintenance.params.on.find(rule=>rule.done).event.slice(1,-1));
  assert.equal(storeResult.params.updateResult,'{{input.event[1]}}');
  for(const [result,expected] of [['current',['notify']],['installed',['script.restart']]]){
    const event=resultPattern.exec(`Foundry update result: ${result} [done]`);
    assert.equal(event?.[1],result);
    const local={updateResult:result};
    const enabled=actions.filter(step=>!step.when||new Function('local',`return ${step.when.slice(2,-2)}`)(local));
    assert.deepEqual(enabled.map(step=>step.method),expected);
    if(result==='current')assert.match(enabled[0].params.html,/already up to date/);
    else assert.equal(enabled[0].params.uri,require('path').resolve(__dirname,'../../start.js'));
  }
});
test('installer reuses an existing launcher environment',()=>{
  const install=require('../../install.js');
  assert.match(install.run[0].when,/!exists.*launcher-env\/Scripts\/python.exe/);
  assert.doesNotMatch(JSON.stringify(install),/--clear|UV_VENV_CLEAR/);
});
