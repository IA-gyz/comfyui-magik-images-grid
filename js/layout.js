/** Pure layout geometry shared by the editor and browser regression tests. */
export const defaults = () => ({v:1, mode:'uniform', canvas:{w:1500,h:1000,heightMode:'fixed',background:'#20242c'}, grid:{columns:3,gap:16,padding:24,rowHeight:240}, orphans:'placeholder',render:{resample:'lanczos',maxPixels:64000000}, sources:[],items:[]});
export const clone = value => JSON.parse(JSON.stringify(value));
// Python round() uses ties-to-even; keep generated frames identical on both sides.
export function round(v) { const f=Math.floor(v), d=v-f; return d===.5 ? (f%2===0?f:f+1) : Math.round(v); }
export function fnv1a32(text) { let h=0x811c9dc5; for(const b of new TextEncoder().encode(text)){h^=b;h=Math.imul(h,0x01000193)>>>0;} return h.toString(16).padStart(8,'0'); }
export function parse(text) {
  const data=text ? JSON.parse(text) : {};
  if(!data || typeof data!=='object' || Array.isArray(data) || (data.v!==undefined && data.v!==1)) throw Error('Unsupported layout JSON. Import a schema v1 layout.');
  const d=defaults();
  for(const key of ['mode','orphans']) if(data[key]!==undefined)d[key]=data[key];
  for(const key of ['canvas','grid','render']) d[key]={...d[key],...data[key]};
  d.sources=data.sources||[]; d.items=data.items||[];
  return validate(d);
}
export function validate(d) {
  const num=(value,name,min,max,integer=false)=>{
    if(typeof value!=='number'||!Number.isFinite(value)||value<min||value>max)throw Error(`${name} must be a finite number between ${min} and ${max}.`);
    return integer?round(value):value;
  };
  const one=(v,name,allowed)=>{if(!allowed.includes(v))throw Error(`Invalid ${name}.`);return v;};
  one(d.mode,'mode',['uniform','packed','custom']);one(d.orphans,'missing source policy',['placeholder','drop','error']);
  for(const k of ['w','h'])d.canvas[k]=num(d.canvas[k],`Canvas ${k}`,1,32768,true);
  one(d.canvas.heightMode,'height mode',['fixed','auto']);
  if(!/^#[0-9a-f]{6}$/i.test(d.canvas.background))throw Error('Background must be a #RRGGBB color.');
  for(const k of ['gap','padding'])d.grid[k]=num(d.grid[k],k,0,32768,true);
  d.grid.columns=num(d.grid.columns,'Columns',1,100,true);d.grid.rowHeight=num(d.grid.rowHeight,'Row height',1,32768,true);
  one(d.render.resample,'resampling',['nearest','bilinear','bicubic','lanczos']);d.render.maxPixels=num(d.render.maxPixels,'Pixel limit',1,64000000,true);
  if(!Array.isArray(d.sources)||d.sources.length>8192||!Array.isArray(d.items)||d.items.length>8192)throw Error('Invalid source or item list.');
  const sourceIds=new Set();
  for(const s of d.sources){if(!s||typeof s.id!=='string'||sourceIds.has(s.id))throw Error('Source ids must be unique strings.');sourceIds.add(s.id);num(s.w,'Source width',1,Number.MAX_SAFE_INTEGER);num(s.h,'Source height',1,Number.MAX_SAFE_INTEGER);}
  const ids=new Set();
  d.items=d.items.map((item,index)=>{
    if(!item||typeof item.source!=='string')throw Error('Items require source ids.');
    const i={x:24,y:24,w:240,h:240,z:index,fit:'contain',opacity:1,visible:true,anchorX:.5,anchorY:.5,...item};
    i.uid=i.uid||globalThis.crypto?.randomUUID?.()||`item-${Date.now()}-${Math.random()}`;
    if(typeof i.uid!=='string'||ids.has(i.uid))throw Error('Item uids must be unique strings.');ids.add(i.uid);
    for(const k of ['x','y'])i[k]=num(i[k],k,-32768,32768,true);
    for(const k of ['w','h'])i[k]=num(i[k],k,1,32768,true);
    i.z=num(i.z,'Layer',-8192,8192,true);i.opacity=num(i.opacity,'Opacity',0,1);
    for(const k of ['anchorX','anchorY'])i[k]=num(i[k],k,0,1);
    one(i.fit,'fit',['contain','cover','stretch']);i.visible=Boolean(i.visible);return i;
  });
  return d;
}
export function geometry(layout) {
  const c=layout.canvas,g=layout.grid,sources=new Map(layout.sources.map(s=>[s.id,s]));
  const items=layout.items.filter(i=>i.visible!==false && (layout.orphans!=='drop'||sources.has(i.source))).map(clone);
  const pad=g.padding,gap=g.gap,w=c.w,avail=w-2*pad;
  if(layout.mode!=='custom' && items.length){
    if(avail<1)throw Error('Canvas width must exceed twice the padding.');
    if(layout.mode==='uniform'){
      const cols=Math.min(g.columns,items.length),rows=Math.ceil(items.length/cols),cw=(avail-(cols-1)*gap)/cols;
      const ch=c.heightMode==='auto'?cw:(c.h-2*pad-(rows-1)*gap)/rows;
      if(Math.min(cw,ch)<1)throw Error('Grid cells are smaller than one pixel. Reduce padding/gap or increase the canvas.');
      items.forEach((i,n)=>{const x=pad+(n%cols)*(cw+gap),y=pad+Math.floor(n/cols)*(ch+gap);Object.assign(i,{x:round(x),y:round(y),w:Math.max(1,round(x+cw)-round(x)),h:Math.max(1,round(y+ch)-round(y))});});
    } else if(layout.mode==='packed'){
      let x=pad,y=pad,rh=0;
      for(const i of items){const s=sources.get(i.source)||i;let ih=g.rowHeight,iw=Math.max(1,round(ih*s.w/s.h));if(iw>avail){ih=Math.max(1,round(ih*avail/iw));iw=avail;}if(x>pad && x+iw>w-pad){x=pad;y+=rh+gap;rh=0;}Object.assign(i,{x:round(x),y:round(y),w:round(iw),h:round(ih)});x+=iw+gap;rh=Math.max(rh,ih);}
    }
  }
  const h=c.heightMode==='auto'?Math.max(1,(items.length?Math.max(...items.map(i=>i.y+i.h)):c.h-pad)+pad):c.h;
  if(!Number.isFinite(w*h)||h>32768||w*h>layout.render.maxPixels)throw Error('Canvas exceeds the configured pixel limit.');
  return {canvas:{w,h,background:c.background},frames:items.sort((a,b)=>a.z-b.z)};
}
export function freeze(layout) {
  const resolved=geometry(layout), frames=new Map(resolved.frames.map(f=>[f.uid,f]));
  for(const item of layout.items){const f=frames.get(item.uid);if(f)Object.assign(item,{x:f.x,y:f.y,w:f.w,h:f.h});}
  layout.mode='custom'; return layout;
}
export function mergePayload(layout,payload){
  const d=clone(layout),known=new Set(d.sources.map(s=>s.id)),uids=new Set(d.items.map(i=>i.uid));
  // Only add genuinely new sources; an item deleted during execution stays deleted.
  for(const i of payload.layout.items)if(!known.has(i.source)&&!uids.has(i.uid)) {d.items.push(clone(i));uids.add(i.uid);}
  d.sources=clone(payload.inventory);
  if(d.orphans==='drop'){const ids=new Set(d.sources.map(s=>s.id));d.items=d.items.filter(i=>ids.has(i.source));}
  return d;
}
export function newItem(source,layout){
  const w=Math.min(320,source.w),h=Math.min(32768,Math.max(1,round(w*source.h/source.w)));
  return {uid:globalThis.crypto?.randomUUID?.()||`item-${Date.now()}-${Math.random().toString(16).slice(2)}`,source:source.id,x:layout.grid.padding,y:layout.grid.padding,w,h,z:layout.items.length,fit:'contain',opacity:1,visible:true,anchorX:.5,anchorY:.5};
}
