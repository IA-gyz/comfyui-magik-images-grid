import {test} from 'node:test';
import assert from 'node:assert/strict';
import {defaults,parse,geometry,freeze,mergePayload,newItem,fnv1a32,round} from '../js/layout.js';

const source={id:'in1:0',w:200,h:100,hash:'a'};
function sample(){const d=defaults();d.sources=[source];d.items=[newItem(source,d)];return d;}

test('hash vectors and UTF-8 match Python',()=>{assert.equal(fnv1a32(''),'811c9dc5');assert.equal(fnv1a32('foobar'),'bf9cf968');assert.equal(fnv1a32('é'),'1e9de8c1');});
test('ties-to-even rounding',()=>{assert.equal(round(2.5),2);assert.equal(round(3.5),4);assert.equal(round(-2.5),-2);assert.equal(round(-3.5),-4);});
test('uniform geometry and freeze preserve every frame',()=>{const d=sample();d.canvas={...d.canvas,w:400,h:300};const before=geometry(d);freeze(d);assert.equal(d.mode,'custom');assert.deepEqual(geometry(d),before);});
test('packed rows preserve source aspect and auto height',()=>{const d=sample();d.mode='packed';d.canvas.w=400;d.canvas.heightMode='auto';d.grid={...d.grid,padding:10,gap:5,rowHeight:50};const r=geometry(d);assert.equal(r.frames[0].w,100);assert.equal(r.frames[0].h,50);assert.equal(r.canvas.h,70);});
test('removed items stay removed during an execution merge',()=>{const d=sample(),submitted=structuredClone(d);d.items=[];const added={id:'in2:0',w:50,h:80};submitted.sources.push(added);submitted.items.push(newItem(added,submitted));const merged=mergePayload(d,{layout:submitted,inventory:submitted.sources});assert.equal(merged.items.length,1);assert.equal(merged.items[0].source,'in2:0');});
test('concurrent edits retain position and canvas settings',()=>{const d=sample(),submitted=structuredClone(d);d.mode='custom';d.items[0].x=123;d.canvas.w=999;const merged=mergePayload(d,{layout:submitted,inventory:submitted.sources});assert.equal(merged.items[0].x,123);assert.equal(merged.canvas.w,999);});
test('hidden and dropped items are omitted',()=>{const d=sample();d.items[0].visible=false;assert.equal(geometry(d).frames.length,0);d.items[0].visible=true;d.sources=[];d.orphans='drop';assert.equal(geometry(d).frames.length,0);});
test('invalid imports are rejected',()=>{for(const text of ['null','[]','{"v":2}','{"canvas":{"w":0}}','{"grid":{"columns":0}}','{"render":{"resample":"bad"}}'])assert.throws(()=>parse(text));});
test('pixel guard matches backend',()=>{const d=sample();d.canvas.w=32768;d.canvas.h=32768;assert.throws(()=>geometry(d));});
test('layout serialize/parse preserves positions and layer order',()=>{const d=sample();d.mode='custom';d.items.push({...newItem(source,d),x:-50,z:3,opacity:.25,fit:'cover'});assert.deepEqual(geometry(parse(JSON.stringify(d))),geometry(d));});

test('60 Python/JavaScript geometry parity fixtures',async()=>{
  const {readFile}=await import('node:fs/promises');
  const fixtures=JSON.parse(await readFile(new URL('./geometry_fixtures.json',import.meta.url),'utf8'));
  for(const [n,f]of fixtures.entries())assert.deepEqual(geometry(f.layout),f.expected,`fixture ${n}`);
});
