import { app } from '../../scripts/app.js';
import { GridEditor } from './editor.js';

const css=document.createElement('link');css.rel='stylesheet';css.href=new URL('./editor.css',import.meta.url).href;document.head.append(css);

app.registerExtension({
  name:'Magik.ImageGrid.Editor',
  async beforeRegisterNodeDef(nodeType,nodeData){
    if(nodeData.name!=='MagikImageGrid')return;
    const created=nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated=function(){
      const ret=created?.apply(this,arguments);
      const widget=this.widgets?.find(w=>w.name==='layout');
      if(!widget){console.error('Magik Image Grid: layout widget not available');return ret;}
      // Keep the original widget and serializer at its original position in widgets_values.
      // Hide only its visual representation; the editor is a nonserialized DOM widget.
      widget.type='converted-widget';widget.hidden=true;widget.computeSize=()=>[0,-4];widget.computeLayoutSize=()=>({minHeight:0,maxHeight:0,minWidth:0});widget.draw=()=>{};
      if(widget.element)widget.element.hidden=true;
      if(widget.inputEl)widget.inputEl.hidden=true;
      let dom,height=800;
      const editor=new GridEditor({read:()=>widget.value||'',write:value=>{widget.value=value;},dirty:()=>this.setDirtyCanvas(true,true),resize:next=>{
        if(next<100)return;height=next+20;
        if(dom){const size=this.computeSize();if(this.size[1]<size[1]||Math.abs(this.size[1]-size[1])>10)this.setSize([this.size[0],size[1]]);}
      }});
      const wrapper=document.createElement('div');wrapper.style.overflow='hidden';wrapper.append(editor.root);
      dom=this.addDOMWidget('magik_grid_editor','magik_grid_editor',wrapper,{serialize:false,hideOnZoom:false,getValue:()=>'',setValue:()=>{},getMinHeight:()=>height,getMaxHeight:()=>height,getHeight:()=>height});
      dom.computeSize=width=>[width,height];this._magikGridEditor=editor;
      this.setSize([Math.max(this.size[0],760),Math.max(this.size[1],height+130)]);
      queueMicrotask(()=>editor.render());return ret;
    };
    const configured=nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure=function(){const ret=configured?.apply(this,arguments);this._magikGridEditor?.load();return ret;};
    const executed=nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted=function(message){const ret=executed?.apply(this,arguments);const payload=message?.magik_image_grid?.[0];if(payload)this._magikGridEditor?.receive(payload);return ret;};
    const removed=nodeType.prototype.onRemoved;
    nodeType.prototype.onRemoved=function(){this._magikGridEditor?.destroy();return removed?.apply(this,arguments);};
  }
});
