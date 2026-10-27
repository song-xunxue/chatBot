import{K as ye,y as _,r as F,M as ot,d as he,C as at,s as c,a5 as ct,H as nn,a9 as Ke,bh as on,bi as ln,aQ as lt,aK as rn,Z,aA as Be,bj as Ze,q as xe,k as St,A as Te,$ as an,T as Ct,D as k,U as L,E as ie,F as ue,S as it,R as Rt,av as ft,b9 as sn,a0 as dn,aZ as un,t as st,aw as Ft,v as Oe,J as dt,bk as cn,ak as Tt,_ as we,aU as $e,bl as fn,O as hn,a6 as vn,bm as gn,aR as bn,az as pn,bn as ht,au as mn,a_ as wn,bo as yn,bp as xn,bq as Sn,Y as de}from"./index-aEyr6MLK.js";import{c as Cn,b as Rn,d as Je,i as ut,f as Fn,B as Tn,V as On,a as Mn,e as rt,u as zn}from"./Follower-Cg6Qi6oB.js";import{b as In,u as vt,a as Pn}from"./Input-B-08Tmlm.js";import{N as Qe}from"./Tag-BLeuNHgP.js";import{a as kn,V as gt,c as _n}from"./create-MDFTPoYJ.js";import{N as Bn}from"./Popover-aWeLpzJW.js";import{N as $n}from"./Empty-WHehI-iN.js";import{h as Ee}from"./happens-in-CM8LO42l.js";function bt(e){return e&-e}class Ot{constructor(n,o){this.l=n,this.min=o;const l=new Array(n+1);for(let a=0;a<n+1;++a)l[a]=0;this.ft=l}add(n,o){if(o===0)return;const{l,ft:a}=this;for(n+=1;n<=l;)a[n]+=o,n+=bt(n)}get(n){return this.sum(n+1)-this.sum(n)}sum(n){if(n===void 0&&(n=this.l),n<=0)return 0;const{ft:o,min:l,l:a}=this;if(n>a)throw new Error("[FinweckTree.sum]: `i` is larger than length.");let f=n*l;for(;n>0;)f+=o[n],n-=bt(n);return f}getBound(n){let o=0,l=this.l;for(;l>o;){const a=Math.floor((o+l)/2),f=this.sum(a);if(f>n){l=a;continue}else if(f<n){if(o===a)return this.sum(o+1)<=n?o+1:a;o=a}else return a}return o}}let je;function En(){return typeof document>"u"?!1:(je===void 0&&("matchMedia"in window?je=window.matchMedia("(pointer:coarse)").matches:je=!1),je)}let et;function pt(){return typeof document>"u"?1:(et===void 0&&(et="chrome"in window?window.devicePixelRatio:1),et)}const Mt="VVirtualListXScroll";function Nn({columnsRef:e,renderColRef:n,renderItemWithColsRef:o}){const l=F(0),a=F(0),f=_(()=>{const w=e.value;if(w.length===0)return null;const T=new Ot(w.length,0);return w.forEach((S,B)=>{T.add(B,S.width)}),T}),g=ye(()=>{const w=f.value;return w!==null?Math.max(w.getBound(a.value)-1,0):0}),d=w=>{const T=f.value;return T!==null?T.sum(w):0},y=ye(()=>{const w=f.value;return w!==null?Math.min(w.getBound(a.value+l.value)+1,e.value.length-1):0});return ot(Mt,{startIndexRef:g,endIndexRef:y,columnsRef:e,renderColRef:n,renderItemWithColsRef:o,getLeft:d}),{listWidthRef:l,scrollLeftRef:a}}const mt=he({name:"VirtualListRow",props:{index:{type:Number,required:!0},item:{type:Object,required:!0}},setup(){const{startIndexRef:e,endIndexRef:n,columnsRef:o,getLeft:l,renderColRef:a,renderItemWithColsRef:f}=at(Mt);return{startIndex:e,endIndex:n,columns:o,renderCol:a,renderItemWithCols:f,getLeft:l}},render(){const{startIndex:e,endIndex:n,columns:o,renderCol:l,renderItemWithCols:a,getLeft:f,item:g}=this;if(a!=null)return a({itemIndex:this.index,startColIndex:e,endColIndex:n,allColumns:o,item:g,getLeft:f});if(l!=null){const d=[];for(let y=e;y<=n;++y){const w=o[y];d.push(l({column:w,left:f(y),item:g}))}return d}return null}}),An=Je(".v-vl",{maxHeight:"inherit",height:"100%",overflow:"auto",minWidth:"1px"},[Je("&:not(.v-vl--show-scrollbar)",{scrollbarWidth:"none"},[Je("&::-webkit-scrollbar, &::-webkit-scrollbar-track-piece, &::-webkit-scrollbar-thumb",{width:0,height:0,display:"none"})])]),Ln=he({name:"VirtualList",inheritAttrs:!1,props:{showScrollbar:{type:Boolean,default:!0},columns:{type:Array,default:()=>[]},renderCol:Function,renderItemWithCols:Function,items:{type:Array,default:()=>[]},itemSize:{type:Number,required:!0},itemResizable:Boolean,itemsStyle:[String,Object],visibleItemsTag:{type:[String,Object],default:"div"},visibleItemsProps:Object,ignoreItemResize:Boolean,onScroll:Function,onWheel:Function,onResize:Function,defaultScrollKey:[Number,String],defaultScrollIndex:Number,keyField:{type:String,default:"key"},paddingTop:{type:[Number,String],default:0},paddingBottom:{type:[Number,String],default:0}},setup(e){const n=rn();An.mount({id:"vueuc/virtual-list",head:!0,anchorMetaName:Cn,ssr:n}),Ke(()=>{const{defaultScrollIndex:s,defaultScrollKey:b}=e;s!=null?G({index:s}):b!=null&&G({key:b})});let o=!1,l=!1;on(()=>{if(o=!1,!l){l=!0;return}G({top:O.value,left:g.value})}),ln(()=>{o=!0,l||(l=!0)});const a=ye(()=>{if(e.renderCol==null&&e.renderItemWithCols==null||e.columns.length===0)return;let s=0;return e.columns.forEach(b=>{s+=b.width}),s}),f=_(()=>{const s=new Map,{keyField:b}=e;return e.items.forEach((P,$)=>{s.set(P[b],$)}),s}),{scrollLeftRef:g,listWidthRef:d}=Nn({columnsRef:Z(e,"columns"),renderColRef:Z(e,"renderCol"),renderItemWithColsRef:Z(e,"renderItemWithCols")}),y=F(null),w=F(void 0),T=new Map,S=_(()=>{const{items:s,itemSize:b,keyField:P}=e,$=new Ot(s.length,b);return s.forEach((N,K)=>{const E=N[P],j=T.get(E);j!==void 0&&$.add(K,j)}),$}),B=F(0),O=F(0),p=ye(()=>Math.max(S.value.getBound(O.value-lt(e.paddingTop))-1,0)),A=_(()=>{const{value:s}=w;if(s===void 0)return[];const{items:b,itemSize:P}=e,$=p.value,N=Math.min($+Math.ceil(s/P+1),b.length-1),K=[];for(let E=$;E<=N;++E)K.push(b[E]);return K}),G=(s,b)=>{if(typeof s=="number"){X(s,b,"auto");return}const{left:P,top:$,index:N,key:K,position:E,behavior:j,debounce:H=!0}=s;if(P!==void 0||$!==void 0)X(P,$,j);else if(N!==void 0)V(N,j,H);else if(K!==void 0){const Q=f.value.get(K);Q!==void 0&&V(Q,j,H)}else E==="bottom"?X(0,Number.MAX_SAFE_INTEGER,j):E==="top"&&X(0,0,j)};let z,I=null;function V(s,b,P){const{value:$}=S,N=$.sum(s)+lt(e.paddingTop);if(!P)y.value.scrollTo({left:0,top:N,behavior:b});else{z=s,I!==null&&window.clearTimeout(I),I=window.setTimeout(()=>{z=void 0,I=null},16);const{scrollTop:K,offsetHeight:E}=y.value;if(N>K){const j=$.get(s);N+j<=K+E||y.value.scrollTo({left:0,top:N+j-E,behavior:b})}else y.value.scrollTo({left:0,top:N,behavior:b})}}function X(s,b,P){y.value.scrollTo({left:s,top:b,behavior:P})}function W(s,b){var P,$,N;if(o||e.ignoreItemResize||ee(b.target))return;const{value:K}=S,E=f.value.get(s),j=K.get(E),H=(N=($=(P=b.borderBoxSize)===null||P===void 0?void 0:P[0])===null||$===void 0?void 0:$.blockSize)!==null&&N!==void 0?N:b.contentRect.height;if(H===j)return;H-e.itemSize===0?T.delete(s):T.set(s,H-e.itemSize);const oe=H-j;if(oe===0)return;K.add(E,oe);const i=y.value;if(i!=null){if(z===void 0){const h=K.sum(E);i.scrollTop>h&&i.scrollBy(0,oe)}else if(E<z)i.scrollBy(0,oe);else if(E===z){const h=K.sum(E);H+h>i.scrollTop+i.offsetHeight&&i.scrollBy(0,oe)}J()}B.value++}const D=!En();let te=!1;function ne(s){var b;(b=e.onScroll)===null||b===void 0||b.call(e,s),(!D||!te)&&J()}function ce(s){var b;if((b=e.onWheel)===null||b===void 0||b.call(e,s),D){const P=y.value;if(P!=null){if(s.deltaX===0&&(P.scrollTop===0&&s.deltaY<=0||P.scrollTop+P.offsetHeight>=P.scrollHeight&&s.deltaY>=0))return;s.preventDefault(),P.scrollTop+=s.deltaY/pt(),P.scrollLeft+=s.deltaX/pt(),J(),te=!0,Rn(()=>{te=!1})}}}function ve(s){if(o||ee(s.target))return;if(e.renderCol==null&&e.renderItemWithCols==null){if(s.contentRect.height===w.value)return}else if(s.contentRect.height===w.value&&s.contentRect.width===d.value)return;w.value=s.contentRect.height,d.value=s.contentRect.width;const{onResize:b}=e;b!==void 0&&b(s)}function J(){const{value:s}=y;s!=null&&(O.value=s.scrollTop,g.value=s.scrollLeft)}function ee(s){let b=s;for(;b!==null;){if(b.style.display==="none")return!0;b=b.parentElement}return!1}return{listHeight:w,listStyle:{overflow:"auto"},keyToIndex:f,itemsStyle:_(()=>{const{itemResizable:s}=e,b=Be(S.value.sum());return B.value,[e.itemsStyle,{boxSizing:"content-box",width:Be(a.value),height:s?"":b,minHeight:s?b:"",paddingTop:Be(e.paddingTop),paddingBottom:Be(e.paddingBottom)}]}),visibleItemsStyle:_(()=>(B.value,{transform:`translateY(${Be(S.value.sum(p.value))})`})),viewportItems:A,listElRef:y,itemsElRef:F(null),scrollTo:G,handleListResize:ve,handleListScroll:ne,handleListWheel:ce,handleItemResize:W}},render(){const{itemResizable:e,keyField:n,keyToIndex:o,visibleItemsTag:l}=this;return c(ct,{onResize:this.handleListResize},{default:()=>{var a,f;return c("div",nn(this.$attrs,{class:["v-vl",this.showScrollbar&&"v-vl--show-scrollbar"],onScroll:this.handleListScroll,onWheel:this.handleListWheel,ref:"listElRef"}),[this.items.length!==0?c("div",{ref:"itemsElRef",class:"v-vl-items",style:this.itemsStyle},[c(l,Object.assign({class:"v-vl-visible-items",style:this.visibleItemsStyle},this.visibleItemsProps),{default:()=>{const{renderCol:g,renderItemWithCols:d}=this;return this.viewportItems.map(y=>{const w=y[n],T=o.get(w),S=g!=null?c(mt,{index:T,item:y}):void 0,B=d!=null?c(mt,{index:T,item:y}):void 0,O=this.$slots.default({item:y,renderedCols:S,renderedItemWithCols:B,index:T})[0];return e?c(ct,{key:w,onResize:p=>this.handleItemResize(w,p)},{default:()=>O}):(O.key=w,O)})}})]):(f=(a=this.$slots).empty)===null||f===void 0?void 0:f.call(a)])}})}});function zt(e,n){n&&(Ke(()=>{const{value:o}=e;o&&Ze.registerHandler(o,n)}),xe(e,(o,l)=>{l&&Ze.unregisterHandler(l)},{deep:!1}),St(()=>{const{value:o}=e;o&&Ze.unregisterHandler(o)}))}function wt(e){switch(typeof e){case"string":return e||void 0;case"number":return String(e);default:return}}function tt(e){const n=e.filter(o=>o!==void 0);if(n.length!==0)return n.length===1?n[0]:o=>{e.forEach(l=>{l&&l(o)})}}const Dn=he({name:"Checkmark",render(){return c("svg",{xmlns:"http://www.w3.org/2000/svg",viewBox:"0 0 16 16"},c("g",{fill:"none"},c("path",{d:"M14.046 3.486a.75.75 0 0 1-.032 1.06l-7.93 7.474a.85.85 0 0 1-1.188-.022l-2.68-2.72a.75.75 0 1 1 1.068-1.053l2.234 2.267l7.468-7.038a.75.75 0 0 1 1.06.032z",fill:"currentColor"})))}}),Vn=he({props:{onFocus:Function,onBlur:Function},setup(e){return()=>c("div",{style:"width: 0; height: 0",tabindex:0,onFocus:e.onFocus,onBlur:e.onBlur})}}),yt=he({name:"NBaseSelectGroupHeader",props:{clsPrefix:{type:String,required:!0},tmNode:{type:Object,required:!0}},setup(){const{renderLabelRef:e,renderOptionRef:n,labelFieldRef:o,nodePropsRef:l}=at(ut);return{labelField:o,nodeProps:l,renderLabel:e,renderOption:n}},render(){const{clsPrefix:e,renderLabel:n,renderOption:o,nodeProps:l,tmNode:{rawNode:a}}=this,f=l==null?void 0:l(a),g=n?n(a,!1):Te(a[this.labelField],a,!1),d=c("div",Object.assign({},f,{class:[`${e}-base-select-group-header`,f==null?void 0:f.class]}),g);return a.render?a.render({node:d,option:a}):o?o({node:d,option:a,selected:!1}):d}});function Wn(e,n){return c(Ct,{name:"fade-in-scale-up-transition"},{default:()=>e?c(an,{clsPrefix:n,class:`${n}-base-select-option__check`},{default:()=>c(Dn)}):null})}const xt=he({name:"NBaseSelectOption",props:{clsPrefix:{type:String,required:!0},tmNode:{type:Object,required:!0}},setup(e){const{valueRef:n,pendingTmNodeRef:o,multipleRef:l,valueSetRef:a,renderLabelRef:f,renderOptionRef:g,labelFieldRef:d,valueFieldRef:y,showCheckmarkRef:w,nodePropsRef:T,handleOptionClick:S,handleOptionMouseEnter:B}=at(ut),O=ye(()=>{const{value:z}=o;return z?e.tmNode.key===z.key:!1});function p(z){const{tmNode:I}=e;I.disabled||S(z,I)}function A(z){const{tmNode:I}=e;I.disabled||B(z,I)}function G(z){const{tmNode:I}=e,{value:V}=O;I.disabled||V||B(z,I)}return{multiple:l,isGrouped:ye(()=>{const{tmNode:z}=e,{parent:I}=z;return I&&I.rawNode.type==="group"}),showCheckmark:w,nodeProps:T,isPending:O,isSelected:ye(()=>{const{value:z}=n,{value:I}=l;if(z===null)return!1;const V=e.tmNode.rawNode[y.value];if(I){const{value:X}=a;return X.has(V)}else return z===V}),labelField:d,renderLabel:f,renderOption:g,handleMouseMove:G,handleMouseEnter:A,handleClick:p}},render(){const{clsPrefix:e,tmNode:{rawNode:n},isSelected:o,isPending:l,isGrouped:a,showCheckmark:f,nodeProps:g,renderOption:d,renderLabel:y,handleClick:w,handleMouseEnter:T,handleMouseMove:S}=this,B=Wn(o,e),O=y?[y(n,o),f&&B]:[Te(n[this.labelField],n,o),f&&B],p=g==null?void 0:g(n),A=c("div",Object.assign({},p,{class:[`${e}-base-select-option`,n.class,p==null?void 0:p.class,{[`${e}-base-select-option--disabled`]:n.disabled,[`${e}-base-select-option--selected`]:o,[`${e}-base-select-option--grouped`]:a,[`${e}-base-select-option--pending`]:l,[`${e}-base-select-option--show-checkmark`]:f}],style:[(p==null?void 0:p.style)||"",n.style||""],onClick:tt([w,p==null?void 0:p.onClick]),onMouseenter:tt([T,p==null?void 0:p.onMouseenter]),onMousemove:tt([S,p==null?void 0:p.onMousemove])}),c("div",{class:`${e}-base-select-option__content`},O));return n.render?n.render({node:A,option:n,selected:o}):d?d({node:A,option:n,selected:o}):A}}),jn=k("base-select-menu",`
 line-height: 1.5;
 outline: none;
 z-index: 0;
 position: relative;
 border-radius: var(--n-border-radius);
 transition:
 background-color .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier);
 background-color: var(--n-color);
`,[k("scrollbar",`
 max-height: var(--n-height);
 `),k("virtual-list",`
 max-height: var(--n-height);
 `),k("base-select-option",`
 min-height: var(--n-option-height);
 font-size: var(--n-option-font-size);
 display: flex;
 align-items: center;
 `,[L("content",`
 z-index: 1;
 white-space: nowrap;
 text-overflow: ellipsis;
 overflow: hidden;
 `)]),k("base-select-group-header",`
 min-height: var(--n-option-height);
 font-size: .93em;
 display: flex;
 align-items: center;
 `),k("base-select-menu-option-wrapper",`
 position: relative;
 width: 100%;
 `),L("loading, empty",`
 display: flex;
 padding: 12px 32px;
 flex: 1;
 justify-content: center;
 `),L("loading",`
 color: var(--n-loading-color);
 font-size: var(--n-loading-size);
 `),L("header",`
 padding: 8px var(--n-option-padding-left);
 font-size: var(--n-option-font-size);
 transition: 
 color .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 border-bottom: 1px solid var(--n-action-divider-color);
 color: var(--n-action-text-color);
 `),L("action",`
 padding: 8px var(--n-option-padding-left);
 font-size: var(--n-option-font-size);
 transition: 
 color .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 border-top: 1px solid var(--n-action-divider-color);
 color: var(--n-action-text-color);
 `),k("base-select-group-header",`
 position: relative;
 cursor: default;
 padding: var(--n-option-padding);
 color: var(--n-group-header-text-color);
 `),k("base-select-option",`
 cursor: pointer;
 position: relative;
 padding: var(--n-option-padding);
 transition:
 color .3s var(--n-bezier),
 opacity .3s var(--n-bezier);
 box-sizing: border-box;
 color: var(--n-option-text-color);
 opacity: 1;
 `,[ie("show-checkmark",`
 padding-right: calc(var(--n-option-padding-right) + 20px);
 `),ue("&::before",`
 content: "";
 position: absolute;
 left: 4px;
 right: 4px;
 top: 0;
 bottom: 0;
 border-radius: var(--n-border-radius);
 transition: background-color .3s var(--n-bezier);
 `),ue("&:active",`
 color: var(--n-option-text-color-pressed);
 `),ie("grouped",`
 padding-left: calc(var(--n-option-padding-left) * 1.5);
 `),ie("pending",[ue("&::before",`
 background-color: var(--n-option-color-pending);
 `)]),ie("selected",`
 color: var(--n-option-text-color-active);
 `,[ue("&::before",`
 background-color: var(--n-option-color-active);
 `),ie("pending",[ue("&::before",`
 background-color: var(--n-option-color-active-pending);
 `)])]),ie("disabled",`
 cursor: not-allowed;
 `,[it("selected",`
 color: var(--n-option-text-color-disabled);
 `),ie("selected",`
 opacity: var(--n-option-opacity-disabled);
 `)]),L("check",`
 font-size: 16px;
 position: absolute;
 right: calc(var(--n-option-padding-right) - 4px);
 top: calc(50% - 7px);
 color: var(--n-option-check-color);
 transition: color .3s var(--n-bezier);
 `,[Rt({enterScale:"0.5"})])])]),Hn=he({name:"InternalSelectMenu",props:Object.assign(Object.assign({},Oe.props),{clsPrefix:{type:String,required:!0},scrollable:{type:Boolean,default:!0},treeMate:{type:Object,required:!0},multiple:Boolean,size:{type:String,default:"medium"},value:{type:[String,Number,Array],default:null},autoPending:Boolean,virtualScroll:{type:Boolean,default:!0},show:{type:Boolean,default:!0},labelField:{type:String,default:"label"},valueField:{type:String,default:"value"},loading:Boolean,focusable:Boolean,renderLabel:Function,renderOption:Function,nodeProps:Function,showCheckmark:{type:Boolean,default:!0},onMousedown:Function,onScroll:Function,onFocus:Function,onBlur:Function,onKeyup:Function,onKeydown:Function,onTabOut:Function,onMouseenter:Function,onMouseleave:Function,onResize:Function,resetMenuOnOptionsChange:{type:Boolean,default:!0},inlineThemeDisabled:Boolean,scrollbarProps:Object,onToggle:Function}),setup(e){const{mergedClsPrefixRef:n,mergedRtlRef:o,mergedComponentPropsRef:l}=st(e),a=Ft("InternalSelectMenu",o,n),f=Oe("InternalSelectMenu","-internal-select-menu",jn,cn,e,Z(e,"clsPrefix")),g=F(null),d=F(null),y=F(null),w=_(()=>e.treeMate.getFlattenedNodes()),T=_(()=>kn(w.value)),S=F(null);function B(){const{treeMate:i}=e;let h=null;const{value:U}=e;U===null?h=i.getFirstAvailableNode():(e.multiple?h=i.getNode((U||[])[(U||[]).length-1]):h=i.getNode(U),(!h||h.disabled)&&(h=i.getFirstAvailableNode())),$(h||null)}function O(){const{value:i}=S;i&&!e.treeMate.getNode(i.key)&&(S.value=null)}let p;xe(()=>e.show,i=>{i?p=xe(()=>e.treeMate,()=>{e.resetMenuOnOptionsChange?(e.autoPending?B():O(),Tt(N)):O()},{immediate:!0}):p==null||p()},{immediate:!0}),St(()=>{p==null||p()});const A=_(()=>lt(f.value.self[we("optionHeight",e.size)])),G=_(()=>$e(f.value.self[we("padding",e.size)])),z=_(()=>e.multiple&&Array.isArray(e.value)?new Set(e.value):new Set),I=_(()=>{const i=w.value;return i&&i.length===0}),V=_(()=>{var i,h;return(h=(i=l==null?void 0:l.value)===null||i===void 0?void 0:i.Select)===null||h===void 0?void 0:h.renderEmpty});function X(i){const{onToggle:h}=e;h&&h(i)}function W(i){const{onScroll:h}=e;h&&h(i)}function D(i){var h;(h=y.value)===null||h===void 0||h.sync(),W(i)}function te(){var i;(i=y.value)===null||i===void 0||i.sync()}function ne(){const{value:i}=S;return i||null}function ce(i,h){h.disabled||$(h,!1)}function ve(i,h){h.disabled||X(h)}function J(i){var h;Ee(i,"action")||(h=e.onKeyup)===null||h===void 0||h.call(e,i)}function ee(i){var h;Ee(i,"action")||(h=e.onKeydown)===null||h===void 0||h.call(e,i)}function s(i){var h;(h=e.onMousedown)===null||h===void 0||h.call(e,i),!e.focusable&&i.preventDefault()}function b(){const{value:i}=S;i&&$(i.getNext({loop:!0}),!0)}function P(){const{value:i}=S;i&&$(i.getPrev({loop:!0}),!0)}function $(i,h=!1){S.value=i,h&&N()}function N(){var i,h;const U=S.value;if(!U)return;const ae=T.value(U.key);ae!==null&&(e.virtualScroll?(i=d.value)===null||i===void 0||i.scrollTo({index:ae}):(h=y.value)===null||h===void 0||h.scrollTo({index:ae,elSize:A.value}))}function K(i){var h,U;!((h=g.value)===null||h===void 0)&&h.contains(i.target)&&((U=e.onFocus)===null||U===void 0||U.call(e,i))}function E(i){var h,U;!((h=g.value)===null||h===void 0)&&h.contains(i.relatedTarget)||(U=e.onBlur)===null||U===void 0||U.call(e,i)}ot(ut,{handleOptionMouseEnter:ce,handleOptionClick:ve,valueSetRef:z,pendingTmNodeRef:S,nodePropsRef:Z(e,"nodeProps"),showCheckmarkRef:Z(e,"showCheckmark"),multipleRef:Z(e,"multiple"),valueRef:Z(e,"value"),renderLabelRef:Z(e,"renderLabel"),renderOptionRef:Z(e,"renderOption"),labelFieldRef:Z(e,"labelField"),valueFieldRef:Z(e,"valueField")}),ot(Fn,g),Ke(()=>{const{value:i}=y;i&&i.sync()});const j=_(()=>{const{size:i}=e,{common:{cubicBezierEaseInOut:h},self:{height:U,borderRadius:ae,color:Se,groupHeaderTextColor:fe,actionDividerColor:le,optionTextColorPressed:Ce,optionTextColor:ge,optionTextColorDisabled:Me,optionTextColorActive:ze,optionOpacityDisabled:Ie,optionCheckColor:pe,actionTextColor:me,optionColorPending:Pe,optionColorActive:ke,loadingColor:_e,loadingSize:Re,optionColorActivePending:Fe,[we("optionFontSize",i)]:re,[we("optionHeight",i)]:r,[we("optionPadding",i)]:v}}=f.value;return{"--n-height":U,"--n-action-divider-color":le,"--n-action-text-color":me,"--n-bezier":h,"--n-border-radius":ae,"--n-color":Se,"--n-option-font-size":re,"--n-group-header-text-color":fe,"--n-option-check-color":pe,"--n-option-color-pending":Pe,"--n-option-color-active":ke,"--n-option-color-active-pending":Fe,"--n-option-height":r,"--n-option-opacity-disabled":Ie,"--n-option-text-color":ge,"--n-option-text-color-active":ze,"--n-option-text-color-disabled":Me,"--n-option-text-color-pressed":Ce,"--n-option-padding":v,"--n-option-padding-left":$e(v,"left"),"--n-option-padding-right":$e(v,"right"),"--n-loading-color":_e,"--n-loading-size":Re}}),{inlineThemeDisabled:H}=e,Q=H?dt("internal-select-menu",_(()=>e.size[0]),j,e):void 0,oe={selfRef:g,next:b,prev:P,getPendingTmNode:ne};return zt(g,e.onResize),Object.assign({mergedTheme:f,mergedClsPrefix:n,rtlEnabled:a,virtualListRef:d,scrollbarRef:y,itemSize:A,padding:G,flattenedNodes:w,empty:I,mergedRenderEmpty:V,virtualListContainer(){const{value:i}=d;return i==null?void 0:i.listElRef},virtualListContent(){const{value:i}=d;return i==null?void 0:i.itemsElRef},doScroll:W,handleFocusin:K,handleFocusout:E,handleKeyUp:J,handleKeyDown:ee,handleMouseDown:s,handleVirtualListResize:te,handleVirtualListScroll:D,cssVars:H?void 0:j,themeClass:Q==null?void 0:Q.themeClass,onRender:Q==null?void 0:Q.onRender},oe)},render(){const{$slots:e,virtualScroll:n,clsPrefix:o,mergedTheme:l,themeClass:a,onRender:f}=this;return f==null||f(),c("div",{ref:"selfRef",tabindex:this.focusable?0:-1,class:[`${o}-base-select-menu`,`${o}-base-select-menu--${this.size}-size`,this.rtlEnabled&&`${o}-base-select-menu--rtl`,a,this.multiple&&`${o}-base-select-menu--multiple`],style:this.cssVars,onFocusin:this.handleFocusin,onFocusout:this.handleFocusout,onKeyup:this.handleKeyUp,onKeydown:this.handleKeyDown,onMousedown:this.handleMouseDown,onMouseenter:this.onMouseenter,onMouseleave:this.onMouseleave},ft(e.header,g=>g&&c("div",{class:`${o}-base-select-menu__header`,"data-header":!0,key:"header"},g)),this.loading?c("div",{class:`${o}-base-select-menu__loading`},c(sn,{clsPrefix:o,strokeWidth:20})):this.empty?c("div",{class:`${o}-base-select-menu__empty`,"data-empty":!0},un(e.empty,()=>{var g;return[((g=this.mergedRenderEmpty)===null||g===void 0?void 0:g.call(this))||c($n,{theme:l.peers.Empty,themeOverrides:l.peerOverrides.Empty,size:this.size})]})):c(dn,Object.assign({ref:"scrollbarRef",theme:l.peers.Scrollbar,themeOverrides:l.peerOverrides.Scrollbar,scrollable:this.scrollable,container:n?this.virtualListContainer:void 0,content:n?this.virtualListContent:void 0,onScroll:n?void 0:this.doScroll},this.scrollbarProps),{default:()=>n?c(Ln,{ref:"virtualListRef",class:`${o}-virtual-list`,items:this.flattenedNodes,itemSize:this.itemSize,showScrollbar:!1,paddingTop:this.padding.top,paddingBottom:this.padding.bottom,onResize:this.handleVirtualListResize,onScroll:this.handleVirtualListScroll,itemResizable:!0},{default:({item:g})=>g.isGroup?c(yt,{key:g.key,clsPrefix:o,tmNode:g}):g.ignored?null:c(xt,{clsPrefix:o,key:g.key,tmNode:g})}):c("div",{class:`${o}-base-select-menu-option-wrapper`,style:{paddingTop:this.padding.top,paddingBottom:this.padding.bottom}},this.flattenedNodes.map(g=>g.isGroup?c(yt,{key:g.key,clsPrefix:o,tmNode:g}):c(xt,{clsPrefix:o,key:g.key,tmNode:g})))}),ft(e.action,g=>g&&[c("div",{class:`${o}-base-select-menu__action`,"data-action":!0,key:"action"},g),c(Vn,{onFocus:this.onTabOut,key:"focus-detector"})]))}}),Kn=ue([k("base-selection",`
 --n-padding-single: var(--n-padding-single-top) var(--n-padding-single-right) var(--n-padding-single-bottom) var(--n-padding-single-left);
 --n-padding-multiple: var(--n-padding-multiple-top) var(--n-padding-multiple-right) var(--n-padding-multiple-bottom) var(--n-padding-multiple-left);
 position: relative;
 z-index: auto;
 box-shadow: none;
 width: 100%;
 max-width: 100%;
 display: inline-block;
 vertical-align: bottom;
 border-radius: var(--n-border-radius);
 min-height: var(--n-height);
 line-height: 1.5;
 font-size: var(--n-font-size);
 `,[k("base-loading",`
 color: var(--n-loading-color);
 `),k("base-selection-tags","min-height: var(--n-height);"),L("border, state-border",`
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 pointer-events: none;
 border: var(--n-border);
 border-radius: inherit;
 transition:
 box-shadow .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 `),L("state-border",`
 z-index: 1;
 border-color: #0000;
 `),k("base-suffix",`
 cursor: pointer;
 position: absolute;
 top: 50%;
 transform: translateY(-50%);
 right: 10px;
 `,[L("arrow",`
 font-size: var(--n-arrow-size);
 color: var(--n-arrow-color);
 transition: color .3s var(--n-bezier);
 `)]),k("base-selection-overlay",`
 display: flex;
 align-items: center;
 white-space: nowrap;
 pointer-events: none;
 position: absolute;
 top: 0;
 right: 0;
 bottom: 0;
 left: 0;
 padding: var(--n-padding-single);
 transition: color .3s var(--n-bezier);
 `,[L("wrapper",`
 flex-basis: 0;
 flex-grow: 1;
 overflow: hidden;
 text-overflow: ellipsis;
 `)]),k("base-selection-placeholder",`
 color: var(--n-placeholder-color);
 `,[L("inner",`
 max-width: 100%;
 overflow: hidden;
 `)]),k("base-selection-tags",`
 cursor: pointer;
 outline: none;
 box-sizing: border-box;
 position: relative;
 z-index: auto;
 display: flex;
 padding: var(--n-padding-multiple);
 flex-wrap: wrap;
 align-items: center;
 width: 100%;
 vertical-align: bottom;
 background-color: var(--n-color);
 border-radius: inherit;
 transition:
 color .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier),
 background-color .3s var(--n-bezier);
 `),k("base-selection-label",`
 height: var(--n-height);
 display: inline-flex;
 width: 100%;
 vertical-align: bottom;
 cursor: pointer;
 outline: none;
 z-index: auto;
 box-sizing: border-box;
 position: relative;
 transition:
 color .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier),
 background-color .3s var(--n-bezier);
 border-radius: inherit;
 background-color: var(--n-color);
 align-items: center;
 `,[k("base-selection-input",`
 font-size: inherit;
 line-height: inherit;
 outline: none;
 cursor: pointer;
 box-sizing: border-box;
 border:none;
 width: 100%;
 padding: var(--n-padding-single);
 background-color: #0000;
 color: var(--n-text-color);
 transition: color .3s var(--n-bezier);
 caret-color: var(--n-caret-color);
 `,[L("content",`
 text-overflow: ellipsis;
 overflow: hidden;
 white-space: nowrap; 
 `)]),L("render-label",`
 color: var(--n-text-color);
 `)]),it("disabled",[ue("&:hover",[L("state-border",`
 box-shadow: var(--n-box-shadow-hover);
 border: var(--n-border-hover);
 `)]),ie("focus",[L("state-border",`
 box-shadow: var(--n-box-shadow-focus);
 border: var(--n-border-focus);
 `)]),ie("active",[L("state-border",`
 box-shadow: var(--n-box-shadow-active);
 border: var(--n-border-active);
 `),k("base-selection-label","background-color: var(--n-color-active);"),k("base-selection-tags","background-color: var(--n-color-active);")])]),ie("disabled","cursor: not-allowed;",[L("arrow",`
 color: var(--n-arrow-color-disabled);
 `),k("base-selection-label",`
 cursor: not-allowed;
 background-color: var(--n-color-disabled);
 `,[k("base-selection-input",`
 cursor: not-allowed;
 color: var(--n-text-color-disabled);
 `),L("render-label",`
 color: var(--n-text-color-disabled);
 `)]),k("base-selection-tags",`
 cursor: not-allowed;
 background-color: var(--n-color-disabled);
 `),k("base-selection-placeholder",`
 cursor: not-allowed;
 color: var(--n-placeholder-color-disabled);
 `)]),k("base-selection-input-tag",`
 height: calc(var(--n-height) - 6px);
 line-height: calc(var(--n-height) - 6px);
 outline: none;
 display: none;
 position: relative;
 margin-bottom: 3px;
 max-width: 100%;
 vertical-align: bottom;
 `,[L("input",`
 font-size: inherit;
 font-family: inherit;
 min-width: 1px;
 padding: 0;
 background-color: #0000;
 outline: none;
 border: none;
 max-width: 100%;
 overflow: hidden;
 width: 1em;
 line-height: inherit;
 cursor: pointer;
 color: var(--n-text-color);
 caret-color: var(--n-caret-color);
 `),L("mirror",`
 position: absolute;
 left: 0;
 top: 0;
 white-space: pre;
 visibility: hidden;
 user-select: none;
 -webkit-user-select: none;
 opacity: 0;
 `)]),["warning","error"].map(e=>ie(`${e}-status`,[L("state-border",`border: var(--n-border-${e});`),it("disabled",[ue("&:hover",[L("state-border",`
 box-shadow: var(--n-box-shadow-hover-${e});
 border: var(--n-border-hover-${e});
 `)]),ie("active",[L("state-border",`
 box-shadow: var(--n-box-shadow-active-${e});
 border: var(--n-border-active-${e});
 `),k("base-selection-label",`background-color: var(--n-color-active-${e});`),k("base-selection-tags",`background-color: var(--n-color-active-${e});`)]),ie("focus",[L("state-border",`
 box-shadow: var(--n-box-shadow-focus-${e});
 border: var(--n-border-focus-${e});
 `)])])]))]),k("base-selection-popover",`
 margin-bottom: -3px;
 display: flex;
 flex-wrap: wrap;
 margin-right: -8px;
 `),k("base-selection-tag-wrapper",`
 max-width: 100%;
 display: inline-flex;
 padding: 0 7px 3px 0;
 `,[ue("&:last-child","padding-right: 0;"),k("tag",`
 font-size: 14px;
 max-width: 100%;
 `,[L("content",`
 line-height: 1.25;
 text-overflow: ellipsis;
 overflow: hidden;
 `)])])]),Un=he({name:"InternalSelection",props:Object.assign(Object.assign({},Oe.props),{clsPrefix:{type:String,required:!0},bordered:{type:Boolean,default:void 0},active:Boolean,pattern:{type:String,default:""},placeholder:String,selectedOption:{type:Object,default:null},selectedOptions:{type:Array,default:null},labelField:{type:String,default:"label"},valueField:{type:String,default:"value"},multiple:Boolean,filterable:Boolean,clearable:Boolean,disabled:Boolean,size:{type:String,default:"medium"},loading:Boolean,autofocus:Boolean,showArrow:{type:Boolean,default:!0},inputProps:Object,focused:Boolean,renderTag:Function,onKeydown:Function,onClick:Function,onBlur:Function,onFocus:Function,onDeleteOption:Function,maxTagCount:[String,Number],ellipsisTagPopoverProps:Object,onClear:Function,onPatternInput:Function,onPatternFocus:Function,onPatternBlur:Function,renderLabel:Function,status:String,inlineThemeDisabled:Boolean,ignoreComposition:{type:Boolean,default:!0},onResize:Function}),setup(e){const{mergedClsPrefixRef:n,mergedRtlRef:o}=st(e),l=Ft("InternalSelection",o,n),a=F(null),f=F(null),g=F(null),d=F(null),y=F(null),w=F(null),T=F(null),S=F(null),B=F(null),O=F(null),p=F(!1),A=F(!1),G=F(!1),z=Oe("InternalSelection","-internal-selection",Kn,gn,e,Z(e,"clsPrefix")),I=_(()=>e.clearable&&!e.disabled&&(G.value||e.active)),V=_(()=>e.selectedOption?e.renderTag?e.renderTag({option:e.selectedOption,handleClose:()=>{}}):e.renderLabel?e.renderLabel(e.selectedOption,!0):Te(e.selectedOption[e.labelField],e.selectedOption,!0):e.placeholder),X=_(()=>{const r=e.selectedOption;if(r)return r[e.labelField]}),W=_(()=>e.multiple?!!(Array.isArray(e.selectedOptions)&&e.selectedOptions.length):e.selectedOption!==null);function D(){var r;const{value:v}=a;if(v){const{value:q}=f;q&&(q.style.width=`${v.offsetWidth}px`,e.maxTagCount!=="responsive"&&((r=B.value)===null||r===void 0||r.sync({showAllItemsBeforeCalculate:!1})))}}function te(){const{value:r}=O;r&&(r.style.display="none")}function ne(){const{value:r}=O;r&&(r.style.display="inline-block")}xe(Z(e,"active"),r=>{r||te()}),xe(Z(e,"pattern"),()=>{e.multiple&&Tt(D)});function ce(r){const{onFocus:v}=e;v&&v(r)}function ve(r){const{onBlur:v}=e;v&&v(r)}function J(r){const{onDeleteOption:v}=e;v&&v(r)}function ee(r){const{onClear:v}=e;v&&v(r)}function s(r){const{onPatternInput:v}=e;v&&v(r)}function b(r){var v;(!r.relatedTarget||!(!((v=g.value)===null||v===void 0)&&v.contains(r.relatedTarget)))&&ce(r)}function P(r){var v;!((v=g.value)===null||v===void 0)&&v.contains(r.relatedTarget)||ve(r)}function $(r){ee(r)}function N(){G.value=!0}function K(){G.value=!1}function E(r){!e.active||!e.filterable||r.target!==f.value&&r.preventDefault()}function j(r){J(r)}const H=F(!1);function Q(r){if(r.key==="Backspace"&&!H.value&&!e.pattern.length){const{selectedOptions:v}=e;v!=null&&v.length&&j(v[v.length-1])}}let oe=null;function i(r){const{value:v}=a;if(v){const q=r.target.value;v.textContent=q,D()}e.ignoreComposition&&H.value?oe=r:s(r)}function h(){H.value=!0}function U(){H.value=!1,e.ignoreComposition&&s(oe),oe=null}function ae(r){var v;A.value=!0,(v=e.onPatternFocus)===null||v===void 0||v.call(e,r)}function Se(r){var v;A.value=!1,(v=e.onPatternBlur)===null||v===void 0||v.call(e,r)}function fe(){var r,v;if(e.filterable)A.value=!1,(r=w.value)===null||r===void 0||r.blur(),(v=f.value)===null||v===void 0||v.blur();else if(e.multiple){const{value:q}=d;q==null||q.blur()}else{const{value:q}=y;q==null||q.blur()}}function le(){var r,v,q;e.filterable?(A.value=!1,(r=w.value)===null||r===void 0||r.focus()):e.multiple?(v=d.value)===null||v===void 0||v.focus():(q=y.value)===null||q===void 0||q.focus()}function Ce(){const{value:r}=f;r&&(ne(),r.focus())}function ge(){const{value:r}=f;r&&r.blur()}function Me(r){const{value:v}=T;v&&v.setTextContent(`+${r}`)}function ze(){const{value:r}=S;return r}function Ie(){return f.value}let pe=null;function me(){pe!==null&&window.clearTimeout(pe)}function Pe(){e.active||(me(),pe=window.setTimeout(()=>{W.value&&(p.value=!0)},100))}function ke(){me()}function _e(r){r||(me(),p.value=!1)}xe(W,r=>{r||(p.value=!1)}),Ke(()=>{vn(()=>{const r=w.value;r&&(e.disabled?r.removeAttribute("tabindex"):r.tabIndex=A.value?-1:0)})}),zt(g,e.onResize);const{inlineThemeDisabled:Re}=e,Fe=_(()=>{const{size:r}=e,{common:{cubicBezierEaseInOut:v},self:{fontWeight:q,borderRadius:Ue,color:qe,placeholderColor:Ge,textColor:Ne,paddingSingle:Ae,paddingMultiple:Le,caretColor:Ye,colorDisabled:Xe,textColorDisabled:De,placeholderColorDisabled:be,colorActive:t,boxShadowFocus:u,boxShadowActive:m,boxShadowHover:R,border:x,borderFocus:C,borderHover:M,borderActive:Y,arrowColor:se,arrowColorDisabled:Pt,loadingColor:kt,colorActiveWarning:_t,boxShadowFocusWarning:Bt,boxShadowActiveWarning:$t,boxShadowHoverWarning:Et,borderWarning:Nt,borderFocusWarning:At,borderHoverWarning:Lt,borderActiveWarning:Dt,colorActiveError:Vt,boxShadowFocusError:Wt,boxShadowActiveError:jt,boxShadowHoverError:Ht,borderError:Kt,borderFocusError:Ut,borderHoverError:qt,borderActiveError:Gt,clearColor:Yt,clearColorHover:Xt,clearColorPressed:Zt,clearSize:Jt,arrowSize:Qt,[we("height",r)]:en,[we("fontSize",r)]:tn}}=z.value,Ve=$e(Ae),We=$e(Le);return{"--n-bezier":v,"--n-border":x,"--n-border-active":Y,"--n-border-focus":C,"--n-border-hover":M,"--n-border-radius":Ue,"--n-box-shadow-active":m,"--n-box-shadow-focus":u,"--n-box-shadow-hover":R,"--n-caret-color":Ye,"--n-color":qe,"--n-color-active":t,"--n-color-disabled":Xe,"--n-font-size":tn,"--n-height":en,"--n-padding-single-top":Ve.top,"--n-padding-multiple-top":We.top,"--n-padding-single-right":Ve.right,"--n-padding-multiple-right":We.right,"--n-padding-single-left":Ve.left,"--n-padding-multiple-left":We.left,"--n-padding-single-bottom":Ve.bottom,"--n-padding-multiple-bottom":We.bottom,"--n-placeholder-color":Ge,"--n-placeholder-color-disabled":be,"--n-text-color":Ne,"--n-text-color-disabled":De,"--n-arrow-color":se,"--n-arrow-color-disabled":Pt,"--n-loading-color":kt,"--n-color-active-warning":_t,"--n-box-shadow-focus-warning":Bt,"--n-box-shadow-active-warning":$t,"--n-box-shadow-hover-warning":Et,"--n-border-warning":Nt,"--n-border-focus-warning":At,"--n-border-hover-warning":Lt,"--n-border-active-warning":Dt,"--n-color-active-error":Vt,"--n-box-shadow-focus-error":Wt,"--n-box-shadow-active-error":jt,"--n-box-shadow-hover-error":Ht,"--n-border-error":Kt,"--n-border-focus-error":Ut,"--n-border-hover-error":qt,"--n-border-active-error":Gt,"--n-clear-size":Jt,"--n-clear-color":Yt,"--n-clear-color-hover":Xt,"--n-clear-color-pressed":Zt,"--n-arrow-size":Qt,"--n-font-weight":q}}),re=Re?dt("internal-selection",_(()=>e.size[0]),Fe,e):void 0;return{mergedTheme:z,mergedClearable:I,mergedClsPrefix:n,rtlEnabled:l,patternInputFocused:A,filterablePlaceholder:V,label:X,selected:W,showTagsPanel:p,isComposing:H,counterRef:T,counterWrapperRef:S,patternInputMirrorRef:a,patternInputRef:f,selfRef:g,multipleElRef:d,singleElRef:y,patternInputWrapperRef:w,overflowRef:B,inputTagElRef:O,handleMouseDown:E,handleFocusin:b,handleClear:$,handleMouseEnter:N,handleMouseLeave:K,handleDeleteOption:j,handlePatternKeyDown:Q,handlePatternInputInput:i,handlePatternInputBlur:Se,handlePatternInputFocus:ae,handleMouseEnterCounter:Pe,handleMouseLeaveCounter:ke,handleFocusout:P,handleCompositionEnd:U,handleCompositionStart:h,onPopoverUpdateShow:_e,focus:le,focusInput:Ce,blur:fe,blurInput:ge,updateCounter:Me,getCounter:ze,getTail:Ie,renderLabel:e.renderLabel,cssVars:Re?void 0:Fe,themeClass:re==null?void 0:re.themeClass,onRender:re==null?void 0:re.onRender}},render(){const{status:e,multiple:n,size:o,disabled:l,filterable:a,maxTagCount:f,bordered:g,clsPrefix:d,ellipsisTagPopoverProps:y,onRender:w,renderTag:T,renderLabel:S}=this;w==null||w();const B=f==="responsive",O=typeof f=="number",p=B||O,A=c(fn,null,{default:()=>c(In,{clsPrefix:d,loading:this.loading,showArrow:this.showArrow,showClear:this.mergedClearable&&this.selected,onClear:this.handleClear},{default:()=>{var z,I;return(I=(z=this.$slots).arrow)===null||I===void 0?void 0:I.call(z)}})});let G;if(n){const{labelField:z}=this,I=s=>c("div",{class:`${d}-base-selection-tag-wrapper`,key:s.value},T?T({option:s,handleClose:()=>{this.handleDeleteOption(s)}}):c(Qe,{size:o,closable:!s.disabled,disabled:l,onClose:()=>{this.handleDeleteOption(s)},internalCloseIsButtonTag:!1,internalCloseFocusable:!1},{default:()=>S?S(s,!0):Te(s[z],s,!0)})),V=()=>(O?this.selectedOptions.slice(0,f):this.selectedOptions).map(I),X=a?c("div",{class:`${d}-base-selection-input-tag`,ref:"inputTagElRef",key:"__input-tag__"},c("input",Object.assign({},this.inputProps,{ref:"patternInputRef",tabindex:-1,disabled:l,value:this.pattern,autofocus:this.autofocus,class:`${d}-base-selection-input-tag__input`,onBlur:this.handlePatternInputBlur,onFocus:this.handlePatternInputFocus,onKeydown:this.handlePatternKeyDown,onInput:this.handlePatternInputInput,onCompositionstart:this.handleCompositionStart,onCompositionend:this.handleCompositionEnd})),c("span",{ref:"patternInputMirrorRef",class:`${d}-base-selection-input-tag__mirror`},this.pattern)):null,W=B?()=>c("div",{class:`${d}-base-selection-tag-wrapper`,ref:"counterWrapperRef"},c(Qe,{size:o,ref:"counterRef",onMouseenter:this.handleMouseEnterCounter,onMouseleave:this.handleMouseLeaveCounter,disabled:l})):void 0;let D;if(O){const s=this.selectedOptions.length-f;s>0&&(D=c("div",{class:`${d}-base-selection-tag-wrapper`,key:"__counter__"},c(Qe,{size:o,ref:"counterRef",onMouseenter:this.handleMouseEnterCounter,disabled:l},{default:()=>`+${s}`})))}const te=B?a?c(gt,{ref:"overflowRef",updateCounter:this.updateCounter,getCounter:this.getCounter,getTail:this.getTail,style:{width:"100%",display:"flex",overflow:"hidden"}},{default:V,counter:W,tail:()=>X}):c(gt,{ref:"overflowRef",updateCounter:this.updateCounter,getCounter:this.getCounter,style:{width:"100%",display:"flex",overflow:"hidden"}},{default:V,counter:W}):O&&D?V().concat(D):V(),ne=p?()=>c("div",{class:`${d}-base-selection-popover`},B?V():this.selectedOptions.map(I)):void 0,ce=p?Object.assign({show:this.showTagsPanel,trigger:"hover",overlap:!0,placement:"top",width:"trigger",onUpdateShow:this.onPopoverUpdateShow,theme:this.mergedTheme.peers.Popover,themeOverrides:this.mergedTheme.peerOverrides.Popover},y):null,J=(this.selected?!1:this.active?!this.pattern&&!this.isComposing:!0)?c("div",{class:`${d}-base-selection-placeholder ${d}-base-selection-overlay`},c("div",{class:`${d}-base-selection-placeholder__inner`},this.placeholder)):null,ee=a?c("div",{ref:"patternInputWrapperRef",class:`${d}-base-selection-tags`},te,B?null:X,A):c("div",{ref:"multipleElRef",class:`${d}-base-selection-tags`,tabindex:l?void 0:0},te,A);G=c(hn,null,p?c(Bn,Object.assign({},ce,{scrollable:!0,style:"max-height: calc(var(--v-target-height) * 6.6);"}),{trigger:()=>ee,default:ne}):ee,J)}else if(a){const z=this.pattern||this.isComposing,I=this.active?!z:!this.selected,V=this.active?!1:this.selected;G=c("div",{ref:"patternInputWrapperRef",class:`${d}-base-selection-label`,title:this.patternInputFocused?void 0:wt(this.label)},c("input",Object.assign({},this.inputProps,{ref:"patternInputRef",class:`${d}-base-selection-input`,value:this.active?this.pattern:"",placeholder:"",readonly:l,disabled:l,tabindex:-1,autofocus:this.autofocus,onFocus:this.handlePatternInputFocus,onBlur:this.handlePatternInputBlur,onInput:this.handlePatternInputInput,onCompositionstart:this.handleCompositionStart,onCompositionend:this.handleCompositionEnd})),V?c("div",{class:`${d}-base-selection-label__render-label ${d}-base-selection-overlay`,key:"input"},c("div",{class:`${d}-base-selection-overlay__wrapper`},T?T({option:this.selectedOption,handleClose:()=>{}}):S?S(this.selectedOption,!0):Te(this.label,this.selectedOption,!0))):null,I?c("div",{class:`${d}-base-selection-placeholder ${d}-base-selection-overlay`,key:"placeholder"},c("div",{class:`${d}-base-selection-overlay__wrapper`},this.filterablePlaceholder)):null,A)}else G=c("div",{ref:"singleElRef",class:`${d}-base-selection-label`,tabindex:this.disabled?void 0:0},this.label!==void 0?c("div",{class:`${d}-base-selection-input`,title:wt(this.label),key:"input"},c("div",{class:`${d}-base-selection-input__content`},T?T({option:this.selectedOption,handleClose:()=>{}}):S?S(this.selectedOption,!0):Te(this.label,this.selectedOption,!0))):c("div",{class:`${d}-base-selection-placeholder ${d}-base-selection-overlay`,key:"placeholder"},c("div",{class:`${d}-base-selection-placeholder__inner`},this.placeholder)),A);return c("div",{ref:"selfRef",class:[`${d}-base-selection`,this.rtlEnabled&&`${d}-base-selection--rtl`,this.themeClass,e&&`${d}-base-selection--${e}-status`,{[`${d}-base-selection--active`]:this.active,[`${d}-base-selection--selected`]:this.selected||this.active&&this.pattern,[`${d}-base-selection--disabled`]:this.disabled,[`${d}-base-selection--multiple`]:this.multiple,[`${d}-base-selection--focus`]:this.focused}],style:this.cssVars,onClick:this.onClick,onMouseenter:this.handleMouseEnter,onMouseleave:this.handleMouseLeave,onKeydown:this.onKeydown,onFocusin:this.handleFocusin,onFocusout:this.handleFocusout,onMousedown:this.handleMouseDown},G,g?c("div",{class:`${d}-base-selection__border`}):null,g?c("div",{class:`${d}-base-selection__state-border`}):null)}});function He(e){return e.type==="group"}function It(e){return e.type==="ignored"}function nt(e,n){try{return!!(1+n.toString().toLowerCase().indexOf(e.trim().toLowerCase()))}catch{return!1}}function qn(e,n){return{getIsGroup:He,getIgnored:It,getKey(l){return He(l)?l.name||l.key||"key-required":l[e]},getChildren(l){return l[n]}}}function Gn(e,n,o,l){if(!n)return e;function a(f){if(!Array.isArray(f))return[];const g=[];for(const d of f)if(He(d)){const y=a(d[l]);y.length&&g.push(Object.assign({},d,{[l]:y}))}else{if(It(d))continue;n(o,d)&&g.push(d)}return g}return a(e)}function Yn(e,n,o){const l=new Map;return e.forEach(a=>{He(a)?a[o].forEach(f=>{l.set(f[n],f)}):l.set(a[n],a)}),l}const Xn=ue([k("select",`
 z-index: auto;
 outline: none;
 width: 100%;
 position: relative;
 font-weight: var(--n-font-weight);
 `),k("select-menu",`
 margin: 4px 0;
 box-shadow: var(--n-menu-box-shadow);
 `,[Rt({originalTransition:"background-color .3s var(--n-bezier), box-shadow .3s var(--n-bezier)"})])]),Zn=Object.assign(Object.assign({},Oe.props),{to:rt.propTo,bordered:{type:Boolean,default:void 0},clearable:Boolean,clearCreatedOptionsOnClear:{type:Boolean,default:!0},clearFilterAfterSelect:{type:Boolean,default:!0},options:{type:Array,default:()=>[]},defaultValue:{type:[String,Number,Array],default:null},keyboard:{type:Boolean,default:!0},value:[String,Number,Array],placeholder:String,menuProps:Object,multiple:Boolean,size:String,menuSize:{type:String},filterable:Boolean,disabled:{type:Boolean,default:void 0},remote:Boolean,loading:Boolean,filter:Function,placement:{type:String,default:"bottom-start"},widthMode:{type:String,default:"trigger"},tag:Boolean,onCreate:Function,fallbackOption:{type:[Function,Boolean],default:void 0},show:{type:Boolean,default:void 0},showArrow:{type:Boolean,default:!0},maxTagCount:[Number,String],ellipsisTagPopoverProps:Object,consistentMenuWidth:{type:Boolean,default:!0},virtualScroll:{type:Boolean,default:!0},labelField:{type:String,default:"label"},valueField:{type:String,default:"value"},childrenField:{type:String,default:"children"},renderLabel:Function,renderOption:Function,renderTag:Function,"onUpdate:value":[Function,Array],inputProps:Object,nodeProps:Function,ignoreComposition:{type:Boolean,default:!0},showOnFocus:Boolean,onUpdateValue:[Function,Array],onBlur:[Function,Array],onClear:[Function,Array],onFocus:[Function,Array],onScroll:[Function,Array],onSearch:[Function,Array],onUpdateShow:[Function,Array],"onUpdate:show":[Function,Array],displayDirective:{type:String,default:"show"},resetMenuOnOptionsChange:{type:Boolean,default:!0},status:String,showCheckmark:{type:Boolean,default:!0},scrollbarProps:Object,onChange:[Function,Array],items:Array}),ro=he({name:"Select",props:Zn,slots:Object,setup(e){const{mergedClsPrefixRef:n,mergedBorderedRef:o,namespaceRef:l,inlineThemeDisabled:a,mergedComponentPropsRef:f}=st(e),g=Oe("Select","-select",Xn,yn,e,n),d=F(e.defaultValue),y=Z(e,"value"),w=vt(y,d),T=F(!1),S=F(""),B=zn(e,["items","options"]),O=F([]),p=F([]),A=_(()=>p.value.concat(O.value).concat(B.value)),G=_(()=>{const{filter:t}=e;if(t)return t;const{labelField:u,valueField:m}=e;return(R,x)=>{if(!x)return!1;const C=x[u];if(typeof C=="string")return nt(R,C);const M=x[m];return typeof M=="string"?nt(R,M):typeof M=="number"?nt(R,String(M)):!1}}),z=_(()=>{if(e.remote)return B.value;{const{value:t}=A,{value:u}=S;return!u.length||!e.filterable?t:Gn(t,G.value,u,e.childrenField)}}),I=_(()=>{const{valueField:t,childrenField:u}=e,m=qn(t,u);return _n(z.value,m)}),V=_(()=>Yn(A.value,e.valueField,e.childrenField)),X=F(!1),W=vt(Z(e,"show"),X),D=F(null),te=F(null),ne=F(null),{localeRef:ce}=Pn("Select"),ve=_(()=>{var t;return(t=e.placeholder)!==null&&t!==void 0?t:ce.value.placeholder}),J=[],ee=F(new Map),s=_(()=>{const{fallbackOption:t}=e;if(t===void 0){const{labelField:u,valueField:m}=e;return R=>({[u]:String(R),[m]:R})}return t===!1?!1:u=>Object.assign(t(u),{value:u})});function b(t){const u=e.remote,{value:m}=ee,{value:R}=V,{value:x}=s,C=[];return t.forEach(M=>{if(R.has(M))C.push(R.get(M));else if(u&&m.has(M))C.push(m.get(M));else if(x){const Y=x(M);Y&&C.push(Y)}}),C}const P=_(()=>{if(e.multiple){const{value:t}=w;return Array.isArray(t)?b(t):[]}return null}),$=_(()=>{const{value:t}=w;return!e.multiple&&!Array.isArray(t)?t===null?null:b([t])[0]||null:null}),N=mn(e,{mergedSize:t=>{var u,m;const{size:R}=e;if(R)return R;const{mergedSize:x}=t||{};if(x!=null&&x.value)return x.value;const C=(m=(u=f==null?void 0:f.value)===null||u===void 0?void 0:u.Select)===null||m===void 0?void 0:m.size;return C||"medium"}}),{mergedSizeRef:K,mergedDisabledRef:E,mergedStatusRef:j}=N;function H(t,u){const{onChange:m,"onUpdate:value":R,onUpdateValue:x}=e,{nTriggerFormChange:C,nTriggerFormInput:M}=N;m&&de(m,t,u),x&&de(x,t,u),R&&de(R,t,u),d.value=t,C(),M()}function Q(t){const{onBlur:u}=e,{nTriggerFormBlur:m}=N;u&&de(u,t),m()}function oe(){const{onClear:t}=e;t&&de(t)}function i(t){const{onFocus:u,showOnFocus:m}=e,{nTriggerFormFocus:R}=N;u&&de(u,t),R(),m&&fe()}function h(t){const{onSearch:u}=e;u&&de(u,t)}function U(t){const{onScroll:u}=e;u&&de(u,t)}function ae(){var t;const{remote:u,multiple:m}=e;if(u){const{value:R}=ee;if(m){const{valueField:x}=e;(t=P.value)===null||t===void 0||t.forEach(C=>{R.set(C[x],C)})}else{const x=$.value;x&&R.set(x[e.valueField],x)}}}function Se(t){const{onUpdateShow:u,"onUpdate:show":m}=e;u&&de(u,t),m&&de(m,t),X.value=t}function fe(){E.value||(Se(!0),X.value=!0,e.filterable&&Le())}function le(){Se(!1)}function Ce(){S.value="",p.value=J}const ge=F(!1);function Me(){e.filterable&&(ge.value=!0)}function ze(){e.filterable&&(ge.value=!1,W.value||Ce())}function Ie(){E.value||(W.value?e.filterable?Le():le():fe())}function pe(t){var u,m;!((m=(u=ne.value)===null||u===void 0?void 0:u.selfRef)===null||m===void 0)&&m.contains(t.relatedTarget)||(T.value=!1,Q(t),le())}function me(t){i(t),T.value=!0}function Pe(){T.value=!0}function ke(t){var u;!((u=D.value)===null||u===void 0)&&u.$el.contains(t.relatedTarget)||(T.value=!1,Q(t),le())}function _e(){var t;(t=D.value)===null||t===void 0||t.focus(),le()}function Re(t){var u;W.value&&(!((u=D.value)===null||u===void 0)&&u.$el.contains(xn(t))||le())}function Fe(t){if(!Array.isArray(t))return[];if(s.value)return Array.from(t);{const{remote:u}=e,{value:m}=V;if(u){const{value:R}=ee;return t.filter(x=>m.has(x)||R.has(x))}else return t.filter(R=>m.has(R))}}function re(t){r(t.rawNode)}function r(t){if(E.value)return;const{tag:u,remote:m,clearFilterAfterSelect:R,valueField:x}=e;if(u&&!m){const{value:C}=p,M=C[0]||null;if(M){const Y=O.value;Y.length?Y.push(M):O.value=[M],p.value=J}}if(m&&ee.value.set(t[x],t),e.multiple){const C=Fe(w.value),M=C.findIndex(Y=>Y===t[x]);if(~M){if(C.splice(M,1),u&&!m){const Y=v(t[x]);~Y&&(O.value.splice(Y,1),R&&(S.value=""))}}else C.push(t[x]),R&&(S.value="");H(C,b(C))}else{if(u&&!m){const C=v(t[x]);~C?O.value=[O.value[C]]:O.value=J}Ae(),le(),H(t[x],t)}}function v(t){return O.value.findIndex(m=>m[e.valueField]===t)}function q(t){W.value||fe();const{value:u}=t.target;S.value=u;const{tag:m,remote:R}=e;if(h(u),m&&!R){if(!u){p.value=J;return}const{onCreate:x}=e,C=x?x(u):{[e.labelField]:u,[e.valueField]:u},{valueField:M,labelField:Y}=e;B.value.some(se=>se[M]===C[M]||se[Y]===C[Y])||O.value.some(se=>se[M]===C[M]||se[Y]===C[Y])?p.value=J:p.value=[C]}}function Ue(t){t.stopPropagation();const{multiple:u,tag:m,remote:R,clearCreatedOptionsOnClear:x}=e;!u&&e.filterable&&le(),m&&!R&&x&&(O.value=J),oe(),u?H([],[]):H(null,null)}function qe(t){!Ee(t,"action")&&!Ee(t,"empty")&&!Ee(t,"header")&&t.preventDefault()}function Ge(t){U(t)}function Ne(t){var u,m,R,x,C;if(!e.keyboard){t.preventDefault();return}switch(t.key){case" ":if(e.filterable)break;t.preventDefault();case"Enter":if(!(!((u=D.value)===null||u===void 0)&&u.isComposing)){if(W.value){const M=(m=ne.value)===null||m===void 0?void 0:m.getPendingTmNode();M?re(M):e.filterable||(le(),Ae())}else if(fe(),e.tag&&ge.value){const M=p.value[0];if(M){const Y=M[e.valueField],{value:se}=w;e.multiple&&Array.isArray(se)&&se.includes(Y)||r(M)}}}t.preventDefault();break;case"ArrowUp":if(t.preventDefault(),e.loading)return;W.value&&((R=ne.value)===null||R===void 0||R.prev());break;case"ArrowDown":if(t.preventDefault(),e.loading)return;W.value?(x=ne.value)===null||x===void 0||x.next():fe();break;case"Escape":W.value&&(Sn(t),le()),(C=D.value)===null||C===void 0||C.focus();break}}function Ae(){var t;(t=D.value)===null||t===void 0||t.focus()}function Le(){var t;(t=D.value)===null||t===void 0||t.focusInput()}function Ye(){var t;W.value&&((t=te.value)===null||t===void 0||t.syncPosition())}ae(),xe(Z(e,"options"),ae);const Xe={focus:()=>{var t;(t=D.value)===null||t===void 0||t.focus()},focusInput:()=>{var t;(t=D.value)===null||t===void 0||t.focusInput()},blur:()=>{var t;(t=D.value)===null||t===void 0||t.blur()},blurInput:()=>{var t;(t=D.value)===null||t===void 0||t.blurInput()}},De=_(()=>{const{self:{menuBoxShadow:t}}=g.value;return{"--n-menu-box-shadow":t}}),be=a?dt("select",void 0,De,e):void 0;return Object.assign(Object.assign({},Xe),{mergedStatus:j,mergedClsPrefix:n,mergedBordered:o,namespace:l,treeMate:I,isMounted:wn(),triggerRef:D,menuRef:ne,pattern:S,uncontrolledShow:X,mergedShow:W,adjustedTo:rt(e),uncontrolledValue:d,mergedValue:w,followerRef:te,localizedPlaceholder:ve,selectedOption:$,selectedOptions:P,mergedSize:K,mergedDisabled:E,focused:T,activeWithoutMenuOpen:ge,inlineThemeDisabled:a,onTriggerInputFocus:Me,onTriggerInputBlur:ze,handleTriggerOrMenuResize:Ye,handleMenuFocus:Pe,handleMenuBlur:ke,handleMenuTabOut:_e,handleTriggerClick:Ie,handleToggle:re,handleDeleteOption:r,handlePatternInput:q,handleClear:Ue,handleTriggerBlur:pe,handleTriggerFocus:me,handleKeydown:Ne,handleMenuAfterLeave:Ce,handleMenuClickOutside:Re,handleMenuScroll:Ge,handleMenuKeydown:Ne,handleMenuMousedown:qe,mergedTheme:g,cssVars:a?void 0:De,themeClass:be==null?void 0:be.themeClass,onRender:be==null?void 0:be.onRender})},render(){return c("div",{class:`${this.mergedClsPrefix}-select`},c(Tn,null,{default:()=>[c(On,null,{default:()=>c(Un,{ref:"triggerRef",inlineThemeDisabled:this.inlineThemeDisabled,status:this.mergedStatus,inputProps:this.inputProps,clsPrefix:this.mergedClsPrefix,showArrow:this.showArrow,maxTagCount:this.maxTagCount,ellipsisTagPopoverProps:this.ellipsisTagPopoverProps,bordered:this.mergedBordered,active:this.activeWithoutMenuOpen||this.mergedShow,pattern:this.pattern,placeholder:this.localizedPlaceholder,selectedOption:this.selectedOption,selectedOptions:this.selectedOptions,multiple:this.multiple,renderTag:this.renderTag,renderLabel:this.renderLabel,filterable:this.filterable,clearable:this.clearable,disabled:this.mergedDisabled,size:this.mergedSize,theme:this.mergedTheme.peers.InternalSelection,labelField:this.labelField,valueField:this.valueField,themeOverrides:this.mergedTheme.peerOverrides.InternalSelection,loading:this.loading,focused:this.focused,onClick:this.handleTriggerClick,onDeleteOption:this.handleDeleteOption,onPatternInput:this.handlePatternInput,onClear:this.handleClear,onBlur:this.handleTriggerBlur,onFocus:this.handleTriggerFocus,onKeydown:this.handleKeydown,onPatternBlur:this.onTriggerInputBlur,onPatternFocus:this.onTriggerInputFocus,onResize:this.handleTriggerOrMenuResize,ignoreComposition:this.ignoreComposition},{arrow:()=>{var e,n;return[(n=(e=this.$slots).arrow)===null||n===void 0?void 0:n.call(e)]}})}),c(Mn,{ref:"followerRef",show:this.mergedShow,to:this.adjustedTo,teleportDisabled:this.adjustedTo===rt.tdkey,containerClass:this.namespace,width:this.consistentMenuWidth?"target":void 0,minWidth:"target",placement:this.placement},{default:()=>c(Ct,{name:"fade-in-scale-up-transition",appear:this.isMounted,onAfterLeave:this.handleMenuAfterLeave},{default:()=>{var e,n,o;return this.mergedShow||this.displayDirective==="show"?((e=this.onRender)===null||e===void 0||e.call(this),bn(c(Hn,Object.assign({},this.menuProps,{ref:"menuRef",onResize:this.handleTriggerOrMenuResize,inlineThemeDisabled:this.inlineThemeDisabled,virtualScroll:this.consistentMenuWidth&&this.virtualScroll,class:[`${this.mergedClsPrefix}-select-menu`,this.themeClass,(n=this.menuProps)===null||n===void 0?void 0:n.class],clsPrefix:this.mergedClsPrefix,focusable:!0,labelField:this.labelField,valueField:this.valueField,autoPending:!0,nodeProps:this.nodeProps,theme:this.mergedTheme.peers.InternalSelectMenu,themeOverrides:this.mergedTheme.peerOverrides.InternalSelectMenu,treeMate:this.treeMate,multiple:this.multiple,size:this.menuSize,renderOption:this.renderOption,renderLabel:this.renderLabel,value:this.mergedValue,style:[(o=this.menuProps)===null||o===void 0?void 0:o.style,this.cssVars],onToggle:this.handleToggle,onScroll:this.handleMenuScroll,onFocus:this.handleMenuFocus,onBlur:this.handleMenuBlur,onKeydown:this.handleMenuKeydown,onTabOut:this.handleMenuTabOut,onMousedown:this.handleMenuMousedown,show:this.mergedShow,showCheckmark:this.showCheckmark,resetMenuOnOptionsChange:this.resetMenuOnOptionsChange,scrollbarProps:this.scrollbarProps}),{empty:()=>{var l,a;return[(a=(l=this.$slots).empty)===null||a===void 0?void 0:a.call(l)]},header:()=>{var l,a;return[(a=(l=this.$slots).header)===null||a===void 0?void 0:a.call(l)]},action:()=>{var l,a;return[(a=(l=this.$slots).action)===null||a===void 0?void 0:a.call(l)]}}),this.displayDirective==="show"?[[pn,this.mergedShow],[ht,this.handleMenuClickOutside,void 0,{capture:!0}]]:[[ht,this.handleMenuClickOutside,void 0,{capture:!0}]])):null}})})]}))}});export{ro as N};
