import {msg, sourceText, sourceMessage, setText} from "../web/foundry/i18n.js";
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('../web/foundry/hair/graph.js',import.meta.url),'utf8');
const merge=new Function("msg","sourceText",source.replace(/^import .*;\r?\n/gm,'').replaceAll('export ','')+';return mergeHairBranch;')(msg,sourceText);
const full=JSON.parse(await readFile(new URL('../workflows/Mumblebox 3D Asset Foundry.json',import.meta.url),'utf8'));
const ids=new Set([70000,70001,70002,70003,70004,70005]);
const template={nodes:full.nodes.filter(n=>ids.has(+n.id)),links:full.links.filter(l=>ids.has(+l[1])&&ids.has(+l[3])),groups:full.groups.filter(g=>g.title.startsWith('HAIR /'))};

test('opening HairDeck upgrades a graph with no hair branch without altering other workflows',()=>{
 const old=structuredClone(full);old.nodes=old.nodes.filter(n=>!ids.has(+n.id));old.links=old.links.filter(l=>!ids.has(+l[1])&&!ids.has(+l[3]));old.groups=old.groups.filter(g=>!g.title.startsWith('HAIR /'));
 const before=structuredClone(old),result=merge(old,template);
 assert.equal(result.changed,true);assert.deepEqual(old,before);
 assert.deepEqual(result.graph.nodes.filter(n=>!ids.has(+n.id)),before.nodes);
 assert.deepEqual(result.graph.links.slice(0,before.links.length),before.links);
 assert.deepEqual(result.graph.groups.slice(0,before.groups.length),before.groups);
 assert.equal(result.graph.nodes.filter(n=>ids.has(+n.id)).length,6);
 assert.equal(merge(result.graph,template).changed,false);
});

test('old HairDeck generation node upgrades while preserving its meaningful settings',()=>{
 const old=structuredClone(full),n=old.nodes.find(n=>n.id===70002);
 n.type='HairDeckGenerate';n.widgets_values_named={image:'saved.png',seed:73,steps:10,cfg:1.75,generate_bones:false};
 const result=merge(old,template),updated=result.graph.nodes.find(n=>n.id===70002);
 assert.equal(updated.type,'FoundryHairGenerate');assert.deepEqual(updated.widgets_values,['saved.png',73,10,1.75,false,true]);
 assert.deepEqual(result.graph.nodes.filter(n=>n.id!==70002),old.nodes.filter(n=>n.id!==70002));
});

test('a conflicting reserved ID is rejected without modifying the graph',()=>{
 const old=structuredClone(full),before=JSON.stringify(old);old.nodes.find(n=>n.id===70002).type='UserCustomNode';
 const changed=JSON.stringify(old);assert.throws(()=>merge(old,template),/preserved/);assert.equal(JSON.stringify(old),changed);assert.notEqual(changed,before);
});

test('missing chain helper gets only its own link inside the existing hair group',()=>{
 const old=structuredClone(full);old.nodes=old.nodes.filter(n=>n.id!==70005);old.links=old.links.filter(l=>l[3]!==70005);
 old.nodes.find(n=>n.id===70001).outputs[0].links=old.links.filter(l=>l[1]===70001).map(l=>l[0]);
 const result=merge(old,template);assert.equal(result.graph.nodes.length,old.nodes.length+1);assert.deepEqual(result.graph.groups,old.groups);
 assert.equal(result.graph.links.filter(l=>l[3]===70005).length,1);
});
