import {defaults,parse,clone,geometry,freeze,fnv1a32,mergePayload,newItem,round,validate} from './layout.js';

const MAX_ITEMS=8192;
const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};

export class GridEditor {
  constructor({read,write,dirty=()=>{},resize=()=>{}}){
    this.read=read;this.write=write;this.dirty=dirty;this.resize=resize;
    this.selected=null;this.thumbs={};this.undo=[];this.redo=[];this.zoom=1;this.snap=0;this.lockAspect=true;this.warnings=[];this.drag=null;this.error='';
    this.root=el('div','magik-grid');this.root.tabIndex=0;
    this.root.addEventListener('pointerdown',e=>e.stopPropagation());
    this.root.addEventListener('wheel',e=>e.stopPropagation(),{passive:true});
    this.root.addEventListener('keydown',e=>this.key(e));
    this.build();this.load();
    this.observer=new ResizeObserver(()=>{this.draw();this.resize(this.root.scrollHeight);});this.observer.observe(this.root);
  }
  load(){
    try{this.layout=parse(this.read()||'');this.error='';}catch(e){this.layout=defaults();this.error=e.message;}
    this.selected=this.layout.items.some(i=>i.uid===this.selected)?this.selected:null;
    this.render();
  }
  destroy(){this.observer.disconnect();this.root.remove();}
  button(text,fn,parent,cls=''){const b=el('button',cls,text);b.type='button';b.addEventListener('click',fn);parent.append(b);return b;}
  field(parent,title,type,options,onchange){
    const l=el('label','',title), input=el(type==='select'?'select':'input');
    if(type==='select'){for(const [value,text] of options){const o=el('option','',text);o.value=value;input.append(o);}}
    else {input.type=type;Object.assign(input,options||{});}
    if(type==='checkbox')l.className='mg-check';
    input.addEventListener('change',()=>onchange(type==='checkbox'?input.checked:type==='number'?Number(input.value):input.value));l.append(input);parent.append(l);return input;
  }
  build(){
    const head=el('div','mg-header');head.append(el('strong','','MAGIK IMAGE GRID'),el('span','mg-tag','GRID / COLLAGE'));this.root.append(head);
    const settings=el('div','mg-row');this.root.append(settings);this.controls={};
    this.controls.mode=this.field(settings,'Layout','select',[['uniform','Uniform grid'],['packed','Packed rows'],['custom','Custom collage']],v=>this.change(d=>{if(v==='custom')freeze(d);else d.mode=v;}));
    this.controls.mode.parentElement.style.minWidth='150px';this.controls.mode.parentElement.style.flex='2';
    for(const [key,title] of [['w','Width'],['h','Height']])this.controls[key]=this.field(settings,title,'number',{min:1,max:32768,step:1},v=>this.change(d=>d.canvas[key]=this.integer(v,1,32768)));
    this.controls.background=this.field(settings,'Background','color',{},v=>this.change(d=>d.canvas.background=v));
    this.controls.heightMode=this.field(settings,'Auto height','checkbox',{},v=>this.change(d=>d.canvas.heightMode=v?'auto':'fixed'));
    const grid=el('div','mg-row');this.root.append(grid);
    for(const [key,title,min,max] of [['columns','Columns',1,100],['gap','Gap',0,32768],['padding','Padding',0,32768],['rowHeight','Row height',1,32768]])this.controls[key]=this.field(grid,title,'number',{min,max,step:1},v=>this.change(d=>d.grid[key]=this.integer(v,min,max)));
    const toolbar=el('div','mg-toolbar');this.root.append(toolbar);
    this.undoButton=this.button('Undo',()=>this.history(false),toolbar);this.redoButton=this.button('Redo',()=>this.history(true),toolbar);
    this.button('Freeze layout',()=>this.change(d=>freeze(d)),toolbar,'mg-primary');
    this.button('Duplicate',()=>this.duplicate(),toolbar);this.button('Remove',()=>this.remove(),toolbar);
    toolbar.append(el('span','mg-spacer'));
    this.snapInput=this.field(toolbar,'Snap','select',[['0','Off'],['5','5 px'],['10','10 px'],['25','25 px']],v=>this.snap=Number(v));
    this.zoomInput=this.field(toolbar,'View','select',[['.5','50%'],['1','Fit'],['1.5','150%'],['2','200%'],['4','400%']],v=>{this.zoom=Number(v);this.draw();});this.zoomInput.value='1';
    this.viewport=el('div','mg-viewport');this.board=el('div','mg-board');this.board.tabIndex=0;this.viewport.append(this.board);this.root.append(this.viewport);
    this.board.addEventListener('pointerdown',e=>this.start(e));this.board.addEventListener('pointermove',e=>this.move(e));this.board.addEventListener('pointerup',e=>this.finish(e));this.board.addEventListener('pointercancel',e=>this.finish(e,true));
    this.root.append(el('div','mg-note','Drag to move · bottom-right handle to resize · arrows nudge · Shift = 10 px · Ctrl+Z undo. Dragging freezes automatic layouts.'));
    const body=el('div','mg-body');this.root.append(body);
    this.inspector=el('div','mg-section');body.append(this.inspector);
    const layerSection=el('div','mg-section');layerSection.append(el('h4','','Layers · topmost first'));this.layers=el('div','mg-layers');layerSection.append(this.layers);body.append(layerSection);
    const addRow=el('div','mg-row');layerSection.append(addRow);this.sourceSelect=this.field(addRow,'Add source','select',[],()=>{});this.button('Add',()=>this.addSource(),addRow);
    const advanced=el('details');advanced.append(el('summary','','Rendering & layout files'));this.root.append(advanced);const row=el('div','mg-row');advanced.append(row);
    this.controls.orphans=this.field(row,'Missing images','select',[['placeholder','Keep empty frame'],['drop','Drop item'],['error','Stop with error']],v=>this.change(d=>d.orphans=v));
    this.controls.resample=this.field(row,'Resampling','select',[['lanczos','Lanczos'],['bicubic','Bicubic'],['bilinear','Bilinear'],['nearest','Nearest']],v=>this.change(d=>d.render.resample=v));
    this.controls.maxPixels=this.field(row,'Max megapixels','number',{min:.001,max:64,step:1},v=>this.change(d=>d.render.maxPixels=Math.max(1,round(Math.min(64,Math.max(.001,v))*1000000))));
    const files=el('div','mg-toolbar');advanced.append(files);this.button('Export JSON',()=>this.export(),files);this.button('Import JSON',()=>this.fileInput.click(),files);this.button('Reset layout',()=>{if(window.confirm('Reset the layout and arrange all current source images again?'))this.change(d=>{const sources=d.sources;Object.assign(d,defaults());d.sources=sources;d.items=sources.map(s=>newItem(s,d));d.items.forEach((i,n)=>i.z=n);});},files);
    this.fileInput=el('input');this.fileInput.type='file';this.fileInput.accept='.json,application/json';this.fileInput.hidden=true;this.fileInput.addEventListener('change',async()=>{const file=this.fileInput.files[0];try{if(file){if(file.size>8000000)throw Error('Layout file exceeds 8 MB.');const data=parse(await file.text());data.sources=this.layout.sources;this.change(d=>Object.assign(d,data));}}catch(e){this.status(e.message,true);}this.fileInput.value='';});advanced.append(this.fileInput);
    this.warningArea=el('div','mg-warnings');this.statusArea=el('div','mg-status');this.root.append(this.warningArea,this.statusArea);
  }
  integer(v,min,max){if(!Number.isFinite(v))throw Error('Enter a finite number.');return Math.min(max,Math.max(min,round(v)));}
  change(fn){
    const before=clone(this.layout);
    try{fn(this.layout);validate(this.layout);geometry(this.layout);if(this.layout.items.length>MAX_ITEMS)throw Error('Layout item limit reached.');this.record(JSON.stringify(before));this.error='';this.commit();}
    catch(e){this.layout=before;this.error=e.message;}
    this.render();
  }
  record(text){if(this.undo.at(-1)!==text)this.undo.push(text);if(this.undo.length>60)this.undo.shift();this.redo=[];}
  commit(){this.write(JSON.stringify(this.layout));this.dirty();}
  history(redo){const from=redo?this.redo:this.undo,to=redo?this.undo:this.redo;if(!from.length)return;to.push(JSON.stringify(this.layout));const sources=this.layout.sources;this.layout=JSON.parse(from.pop());this.layout.sources=sources;this.selected=this.layout.items.some(i=>i.uid===this.selected)?this.selected:null;this.error='';this.commit();this.render();}
  status(text,error=false){this.statusArea.textContent=text;this.statusArea.classList.toggle('mg-error',error);}
  render(){
    const d=this.layout,c=this.controls;
    c.mode.value=d.mode;c.w.value=d.canvas.w;c.h.value=d.canvas.h;c.h.disabled=d.canvas.heightMode==='auto';c.heightMode.checked=d.canvas.heightMode==='auto';c.background.value=d.canvas.background;
    for(const k of ['columns','gap','padding','rowHeight'])c[k].value=d.grid[k];
    c.columns.disabled=d.mode!=='uniform';c.rowHeight.disabled=d.mode!=='packed';c.gap.disabled=d.mode==='custom';c.padding.disabled=d.mode==='custom'&&d.canvas.heightMode!=='auto';
    c.orphans.value=d.orphans;c.resample.value=d.render.resample;c.maxPixels.value=d.render.maxPixels/1000000;
    this.undoButton.disabled=!this.undo.length;this.redoButton.disabled=!this.redo.length;
    this.draw();this.renderInspector();this.renderLayers();
    this.warningArea.textContent=this.warnings.join(' · ');
  }
  draw(){
    if(!this.layout)return;
    let resolved;try{resolved=geometry(this.layout);}catch(e){this.status(e.message,true);return;}
    this.resolved=resolved;const {w,h,background}=resolved.canvas;
    this.scale=this.drag?.scale ?? Math.max(.002,Math.min((this.viewport.clientWidth-26||550)/w,(this.viewport.clientHeight-26||350)/h))*this.zoom;
    Object.assign(this.board.style,{width:`${w*this.scale}px`,height:`${h*this.scale}px`,background});
    this.board.replaceChildren();const sources=new Map(this.layout.sources.map(s=>[s.id,s]));
    for(const f of resolved.frames){
      const s=sources.get(f.source),frame=el('div','mg-frame');frame.dataset.uid=f.uid;
      if(f.uid===this.selected)frame.classList.add('mg-selected');if(!s)frame.classList.add('mg-missing');
      Object.assign(frame.style,{left:`${f.x*this.scale}px`,top:`${f.y*this.scale}px`,width:`${f.w*this.scale}px`,height:`${f.h*this.scale}px`});
      const art=el('div','mg-art');art.style.opacity=f.opacity;frame.append(art);
      if(this.thumbs[f.source]&&s){
        const img=el('img');img.src=this.thumbs[f.source];img.draggable=false;
        let dw=f.w,dh=f.h;if(f.fit!=='stretch'){const k=(f.fit==='cover'?Math.max:Math.min)(f.w/s.w,f.h/s.h);dw=Math.max(1,round(s.w*k));dh=Math.max(1,round(s.h*k));}
        Object.assign(img.style,{width:`${dw*this.scale}px`,height:`${dh*this.scale}px`,left:`${round((f.w-dw)*f.anchorX)*this.scale}px`,top:`${round((f.h-dh)*f.anchorY)*this.scale}px`});art.append(img);
      } else if(s)art.style.background=`hsl(${this.layout.sources.indexOf(s)*53%360} 25% 32% / .75)`;
      frame.append(el('span','mg-caption',s?`${f.source} · ${s.w}×${s.h}`:`Missing ${f.source}`));
      if(f.uid===this.selected){const handle=el('div','mg-handle');handle.dataset.resize='1';frame.append(handle);}
      this.board.append(frame);
    }
    if(!resolved.frames.length)this.board.append(el('div','mg-empty',this.layout.sources.length?'No visible items. Add a source below.':'Connect images and run once\nto load every image in the editor.'));
    const count=this.layout.sources.length,n=resolved.frames.length;
    this.status(this.error||`${count} source images · ${n} visible items · ${w} × ${h} px · output ${(w*h*12/1048576).toFixed(1)} MiB RGB. Preview uses thumbnails; run to render full quality.`,!!this.error);
  }
  renderLayers(){
    this.layers.replaceChildren();const sources=new Map(this.layout.sources.map(s=>[s.id,s]));
    for(const i of [...this.layout.items].sort((a,b)=>b.z-a.z)){
      const b=this.button('',()=>{this.selected=i.uid;this.render();},this.layers,'mg-layer'+(i.uid===this.selected?' mg-active':''));
      b.append(el('span','',`${i.visible===false?'○':'●'} ${i.source}`),el('small','',sources.has(i.source)?`${sources.get(i.source).w}×${sources.get(i.source).h}`:'missing'));
    }
    const old=this.sourceSelect.value;this.sourceSelect.replaceChildren();for(const s of this.layout.sources){const o=el('option','',`${s.id} · ${s.w}×${s.h}`);o.value=s.id;this.sourceSelect.append(o);}if(this.layout.sources.some(s=>s.id===old))this.sourceSelect.value=old;
  }
  renderInspector(){
    this.inspector.replaceChildren();this.inspector.append(el('h4','','Selected image'));
    const item=this.layout.items.find(i=>i.uid===this.selected);
    if(!item){this.inspector.append(el('div','mg-note','Select an image on the canvas or in the layer list.'));return;}
    const source=this.layout.sources.find(s=>s.id===item.source);this.inspector.append(el('div','mg-inspector-title',`${item.source}${source?` · original ${source.w}×${source.h}`:' · source missing'}`));
    const frame=this.resolved?.frames.find(f=>f.uid===item.uid)||item;
    const row=el('div','mg-row');this.inspector.append(row);
    for(const k of ['x','y','w','h']){
      const input=this.field(row,k.toUpperCase(),'number',{min:['w','h'].includes(k)?1:-32768,max:32768,step:1},v=>this.change(d=>{freeze(d);d.items.find(i=>i.uid===item.uid)[k]=this.integer(v,['w','h'].includes(k)?1:-32768,32768);}));input.value=frame[k];
    }
    const row2=el('div','mg-row');this.inspector.append(row2);
    const fit=this.field(row2,'Image fit','select',[['contain','Contain'],['cover','Cover / crop'],['stretch','Stretch']],v=>this.change(d=>d.items.find(i=>i.uid===item.uid).fit=v));fit.value=item.fit;
    const opacity=this.field(row2,'Opacity','number',{min:0,max:1,step:.05},v=>this.change(d=>d.items.find(i=>i.uid===item.uid).opacity=Math.max(0,Math.min(1,v))));opacity.value=item.opacity;
    const row3=el('div','mg-row');this.inspector.append(row3);
    for(const [k,label] of [['anchorX','Anchor X'],['anchorY','Anchor Y']]){const input=this.field(row3,label,'number',{min:0,max:1,step:.1},v=>this.change(d=>d.items.find(i=>i.uid===item.uid)[k]=Math.max(0,Math.min(1,v))));input.value=item[k];}
    const opts=el('div','mg-row');this.inspector.append(opts);
    const visible=this.field(opts,'Visible','checkbox',{},v=>this.change(d=>d.items.find(i=>i.uid===item.uid).visible=v));visible.checked=item.visible!==false;
    const aspect=this.field(opts,'Lock aspect on resize','checkbox',{},v=>this.lockAspect=v);aspect.checked=this.lockAspect;
    const actions=el('div','mg-toolbar');this.inspector.append(actions);this.button('To front',()=>this.layer(true),actions);this.button('To back',()=>this.layer(false),actions);
  }
  start(e){
    if(e.button!==0)return;e.preventDefault();this.root.focus({preventScroll:true});
    const target=e.target.closest('.mg-frame');if(!target){this.selected=null;this.render();return;}
    this.selected=target.dataset.uid;
    const before=JSON.stringify(this.layout);
    const item=this.resolved.frames.find(i=>i.uid===this.selected);
    this.drag={before,item:clone(item),scale:this.scale,x:e.clientX,y:e.clientY,resize:!!e.target.dataset.resize,moved:false};
    this.board.setPointerCapture(e.pointerId);this.render();
  }
  move(e){
    if(!this.drag)return;e.preventDefault();const d=this.drag,i=this.layout.items.find(i=>i.uid===d.item.uid);
    if(!d.moved && Math.hypot(e.clientX-d.x,e.clientY-d.y)<2)return;
    if(!d.moved){freeze(this.layout);d.moved=true;}
    const dx=(e.clientX-d.x)/d.scale,dy=(e.clientY-d.y)/d.scale;
    const snap=v=>this.snap?round(v/this.snap)*this.snap:round(v);
    if(d.resize){
      let w=Math.max(1,d.item.w+dx),h=Math.max(1,d.item.h+dy);
      if(this.lockAspect&&!e.shiftKey){const ratio=d.item.w/d.item.h;if(Math.abs(dx/d.item.w)>Math.abs(dy/d.item.h))h=w/ratio;else w=h*ratio;}
      i.w=Math.min(32768,Math.max(1,snap(w)));i.h=Math.min(32768,Math.max(1,snap(h)));
    }else{i.x=Math.min(32768,Math.max(-32768,snap(d.item.x+dx)));i.y=Math.min(32768,Math.max(-32768,snap(d.item.y+dy)));}
    this.draw();this.dirty();
  }
  finish(e,cancel=false){
    if(!this.drag)return;const before=this.drag.before,moved=this.drag.moved;this.drag=null;
    if(this.board.hasPointerCapture(e.pointerId))this.board.releasePointerCapture(e.pointerId);
    try{if(cancel){this.layout=JSON.parse(before);}else if(moved){geometry(this.layout);this.record(before);this.commit();this.error='';}}
    catch(err){this.layout=JSON.parse(before);this.error=err.message;}
    this.render();
  }
  addSource(){const s=this.layout.sources.find(s=>s.id===this.sourceSelect.value);if(!s)return;this.change(d=>{const i=newItem(s,d);d.items.push(i);this.selected=i.uid;});}
  duplicate(){if(!this.selected)return;this.change(d=>{freeze(d);const i=d.items.find(i=>i.uid===this.selected);if(!i)return;const n={...clone(i),uid:newItem({id:i.source,w:i.w,h:i.h},d).uid,x:Math.min(32768,i.x+20),y:Math.min(32768,i.y+20),z:d.items.length};d.items.push(n);this.selected=n.uid;this.reorder(d);});}
  remove(){if(!this.selected)return;this.change(d=>{d.items=d.items.filter(i=>i.uid!==this.selected);this.selected=null;this.reorder(d);});}
  reorder(d){[...d.items].sort((a,b)=>a.z-b.z).forEach((i,n)=>i.z=n);}
  layer(front){this.change(d=>{const ordered=[...d.items].sort((a,b)=>a.z-b.z),i=ordered.find(i=>i.uid===this.selected);if(!i)return;const remaining=ordered.filter(v=>v!==i);if(front)remaining.push(i);else remaining.unshift(i);remaining.forEach((i,n)=>i.z=n);});}
  key(e){
    e.stopPropagation();if(['INPUT','SELECT','TEXTAREA','BUTTON'].includes(e.target.tagName))return;
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();this.history(e.shiftKey);return;}
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='y'){e.preventDefault();this.history(true);return;}
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='d'){e.preventDefault();this.duplicate();return;}
    if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();this.remove();return;}
    if(e.key==='Escape'){this.selected=null;this.render();return;}
    const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];
    if(delta&&this.selected){e.preventDefault();this.change(d=>{freeze(d);const i=d.items.find(i=>i.uid===this.selected),step=e.shiftKey?10:1;i.x=this.integer(i.x+delta[0]*step,-32768,32768);i.y=this.integer(i.y+delta[1]*step,-32768,32768);});}
  }
  receive(payload){
    if(!payload||payload.v!==1)return;
    // Commit in-progress pointer edits before comparing the submitted layout hash.
    if(this.drag){if(this.drag.moved){try{geometry(this.layout);this.record(this.drag.before);this.commit();}catch{this.layout=JSON.parse(this.drag.before);}}this.drag=null;}
    const current=this.read()||'';this.layout=payload.received===fnv1a32(current)?clone(payload.layout):mergePayload(this.layout,payload);
    this.thumbs=payload.thumbnails||{};this.warnings=[...(payload.warnings||[])];
    if(payload.upscaled?.length)this.warnings.push(`${payload.upscaled.length} frames upscale their source images.`);
    this.error='';this.selected=this.layout.items.some(i=>i.uid===this.selected)?this.selected:null;this.commit();this.render();
  }
  export(){const blob=new Blob([JSON.stringify(this.layout,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download='magik-grid-layout.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
}
