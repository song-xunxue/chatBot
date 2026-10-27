import{i as vo,j as ho,k as po,l as pe,m as mo,n as fo,p as me,q as Te,r as L,d as M,s as d,t as ve,v as te,x as go,y as f,z as ue,A as oe,C as V,D as h,E as I,F as z,G as We,H as we,I as bo,J as Ce,T as Ye,K as ce,L as Xe,M as J,O as Qe,X as yo,P as xo,Q as wo,R as Co,S as se,U as v,V as ge,W as zo,Y as G,Z as Y,_ as ae,$ as Ze,a0 as So,a1 as Io,a2 as Ro,a3 as Oe,a4 as Po,a5 as No,a6 as Be,a7 as ko,a8 as _o,a9 as Ao,aa as To,ab as je,w as ie,u as U,o as Pe,a as re,h as Q,ac as Oo,g as Le,ad as Ne,f as Ko,ae as $o,B as Ho,c as Fo,af as Eo,ag as Mo,e as Bo,ah as jo,b as Lo}from"./index-aEyr6MLK.js";import{u as Do}from"./useObject-Dxi31HJ3.js";import{p as Uo,l as Vo,a as Go,b as Je,u as qo,N as De,c as Wo,d as Yo}from"./useNapcatWatch-tWtWppSC.js";import{N as eo,p as Ke,f as be,r as Xo}from"./Popover-aWeLpzJW.js";import{C as oo}from"./ChevronRight-BiFHcOCX.js";import{B as Qo,V as Zo,a as Jo,u as et}from"./Follower-Cg6Qi6oB.js";import{h as Ue}from"./happens-in-CM8LO42l.js";import{u as xe,N as ot}from"./Input-B-08Tmlm.js";import{c as ye,V as tt}from"./create-MDFTPoYJ.js";import{_ as nt}from"./_plugin-vue_export-helper-DlAUqK2U.js";import"./index-Dx1FU_Yj.js";function rt(e={},o){const t=fo({ctrl:!1,command:!1,win:!1,shift:!1,tab:!1}),{keydown:r,keyup:i}=e,n=s=>{switch(s.key){case"Control":t.ctrl=!0;break;case"Meta":t.command=!0,t.win=!0;break;case"Shift":t.shift=!0;break;case"Tab":t.tab=!0;break}r!==void 0&&Object.keys(r).forEach(b=>{if(b!==s.key)return;const w=r[b];if(typeof w=="function")w(s);else{const{stop:R=!1,prevent:m=!1}=w;R&&s.stopPropagation(),m&&s.preventDefault(),w.handler(s)}})},c=s=>{switch(s.key){case"Control":t.ctrl=!1;break;case"Meta":t.command=!1,t.win=!1;break;case"Shift":t.shift=!1;break;case"Tab":t.tab=!1;break}i!==void 0&&Object.keys(i).forEach(b=>{if(b!==s.key)return;const w=i[b];if(typeof w=="function")w(s);else{const{stop:R=!1,prevent:m=!1}=w;R&&s.stopPropagation(),m&&s.preventDefault(),w.handler(s)}})},u=()=>{(o===void 0||o.value)&&(me("keydown",document,n),me("keyup",document,c)),o!==void 0&&Te(o,s=>{s?(me("keydown",document,n),me("keyup",document,c)):(pe("keydown",document,n),pe("keyup",document,c))})};return vo()?(ho(u),po(()=>{(o===void 0||o.value)&&(pe("keydown",document,n),pe("keyup",document,c))})):u(),mo(t)}function it(e,o,t){const r=L(e.value);let i=null;return Te(e,n=>{i!==null&&window.clearTimeout(i),n===!0?t&&!t.value?r.value=!0:i=window.setTimeout(()=>{r.value=!0},o):r.value=!1}),r}function lt(e){return o=>{o?e.value=o.$el:e.value=null}}const at=M({name:"ChevronDownFilled",render(){return d("svg",{viewBox:"0 0 16 16",fill:"none",xmlns:"http://www.w3.org/2000/svg"},d("path",{d:"M3.20041 5.73966C3.48226 5.43613 3.95681 5.41856 4.26034 5.70041L8 9.22652L11.7397 5.70041C12.0432 5.41856 12.5177 5.43613 12.7996 5.73966C13.0815 6.0432 13.0639 6.51775 12.7603 6.7996L8.51034 10.7996C8.22258 11.0668 7.77743 11.0668 7.48967 10.7996L3.23966 6.7996C2.93613 6.51775 2.91856 6.0432 3.20041 5.73966Z",fill:"currentColor"}))}}),dt=Object.assign(Object.assign({},Ke),te.props),st=M({name:"Tooltip",props:dt,slots:Object,__popover__:!0,setup(e){const{mergedClsPrefixRef:o}=ve(e),t=te("Tooltip","-tooltip",void 0,go,e,o),r=L(null);return Object.assign(Object.assign({},{syncPosition(){r.value.syncPosition()},setShow(n){r.value.setShow(n)}}),{popoverRef:r,mergedTheme:t,popoverThemeOverrides:f(()=>t.value.self)})},render(){const{mergedTheme:e,internalExtraClass:o}=this;return d(eo,Object.assign(Object.assign({},this.$props),{theme:e.peers.Popover,themeOverrides:e.peerOverrides.Popover,builtinThemeOverrides:this.popoverThemeOverrides,internalExtraClass:o.concat("tooltip"),ref:"popoverRef"}),this.$slots)}}),$e=ue("n-dropdown-menu"),ze=ue("n-dropdown"),Ve=ue("n-dropdown-option"),to=M({name:"DropdownDivider",props:{clsPrefix:{type:String,required:!0}},render(){return d("div",{class:`${this.clsPrefix}-dropdown-divider`})}}),ct=M({name:"DropdownGroupHeader",props:{clsPrefix:{type:String,required:!0},tmNode:{type:Object,required:!0}},setup(){const{showIconRef:e,hasSubmenuRef:o}=V($e),{renderLabelRef:t,labelFieldRef:r,nodePropsRef:i,renderOptionRef:n}=V(ze);return{labelField:r,showIcon:e,hasSubmenu:o,renderLabel:t,nodeProps:i,renderOption:n}},render(){var e;const{clsPrefix:o,hasSubmenu:t,showIcon:r,nodeProps:i,renderLabel:n,renderOption:c}=this,{rawNode:u}=this.tmNode,s=d("div",Object.assign({class:`${o}-dropdown-option`},i==null?void 0:i(u)),d("div",{class:`${o}-dropdown-option-body ${o}-dropdown-option-body--group`},d("div",{"data-dropdown-option":!0,class:[`${o}-dropdown-option-body__prefix`,r&&`${o}-dropdown-option-body__prefix--show-icon`]},oe(u.icon)),d("div",{class:`${o}-dropdown-option-body__label`,"data-dropdown-option":!0},n?n(u):oe((e=u.title)!==null&&e!==void 0?e:u[this.labelField])),d("div",{class:[`${o}-dropdown-option-body__suffix`,t&&`${o}-dropdown-option-body__suffix--has-submenu`],"data-dropdown-option":!0})));return c?c({node:s,option:u}):s}}),ut=h("icon",`
 height: 1em;
 width: 1em;
 line-height: 1em;
 text-align: center;
 display: inline-block;
 position: relative;
 fill: currentColor;
`,[I("color-transition",{transition:"color .3s var(--n-bezier)"}),I("depth",{color:"var(--n-color)"},[z("svg",{opacity:"var(--n-opacity)",transition:"opacity .3s var(--n-bezier)"})]),z("svg",{height:"1em",width:"1em"})]),vt=Object.assign(Object.assign({},te.props),{depth:[String,Number],size:[Number,String],color:String,component:[Object,Function]}),ht=M({_n_icon__:!0,name:"Icon",inheritAttrs:!1,props:vt,setup(e){const{mergedClsPrefixRef:o,inlineThemeDisabled:t}=ve(e),r=te("Icon","-icon",ut,bo,e,o),i=f(()=>{const{depth:c}=e,{common:{cubicBezierEaseInOut:u},self:s}=r.value;if(c!==void 0){const{color:b,[`opacity${c}Depth`]:w}=s;return{"--n-bezier":u,"--n-color":b,"--n-opacity":w}}return{"--n-bezier":u,"--n-color":"","--n-opacity":""}}),n=t?Ce("icon",f(()=>`${e.depth||"d"}`),i,e):void 0;return{mergedClsPrefix:o,mergedStyle:f(()=>{const{size:c,color:u}=e;return{fontSize:be(c),color:u}}),cssVars:t?void 0:i,themeClass:n==null?void 0:n.themeClass,onRender:n==null?void 0:n.onRender}},render(){var e;const{$parent:o,depth:t,mergedClsPrefix:r,component:i,onRender:n,themeClass:c}=this;return!((e=o==null?void 0:o.$options)===null||e===void 0)&&e._n_icon__&&We("icon","don't wrap `n-icon` inside `n-icon`"),n==null||n(),d("i",we(this.$attrs,{role:"img",class:[`${r}-icon`,c,{[`${r}-icon--depth`]:t,[`${r}-icon--color-transition`]:t!==void 0}],style:[this.cssVars,this.mergedStyle]}),i?d(i):this.$slots)}});function ke(e,o){return e.type==="submenu"||e.type===void 0&&e[o]!==void 0}function pt(e){return e.type==="group"}function no(e){return e.type==="divider"}function mt(e){return e.type==="render"}const ro=M({name:"DropdownOption",props:{clsPrefix:{type:String,required:!0},tmNode:{type:Object,required:!0},parentKey:{type:[String,Number],default:null},placement:{type:String,default:"right-start"},props:Object,scrollable:Boolean},setup(e){const o=V(ze),{hoverKeyRef:t,keyboardKeyRef:r,lastToggledSubmenuKeyRef:i,pendingKeyPathRef:n,activeKeyPathRef:c,animatedRef:u,mergedShowRef:s,renderLabelRef:b,renderIconRef:w,labelFieldRef:R,childrenFieldRef:m,renderOptionRef:T,nodePropsRef:O,menuPropsRef:K}=o,S=V(Ve,null),F=V($e),B=V(Xe),q=f(()=>e.tmNode.rawNode),D=f(()=>{const{value:p}=m;return ke(e.tmNode.rawNode,p)}),$=f(()=>{const{disabled:p}=e.tmNode;return p}),P=f(()=>{if(!D.value)return!1;const{key:p,disabled:_}=e.tmNode;if(_)return!1;const{value:j}=t,{value:ne}=r,{value:g}=i,{value:y}=n;return j!==null?y.includes(p):ne!==null?y.includes(p)&&y[y.length-1]!==p:g!==null?y.includes(p):!1}),N=f(()=>r.value===null&&!u.value),X=it(P,300,N),W=f(()=>!!(S!=null&&S.enteringSubmenuRef.value)),ee=L(!1);J(Ve,{enteringSubmenuRef:ee});function E(){ee.value=!0}function le(){ee.value=!1}function Z(){const{parentKey:p,tmNode:_}=e;_.disabled||s.value&&(i.value=p,r.value=null,t.value=_.key)}function C(){const{tmNode:p}=e;p.disabled||s.value&&t.value!==p.key&&Z()}function k(p){if(e.tmNode.disabled||!s.value)return;const{relatedTarget:_}=p;_&&!Ue({target:_},"dropdownOption")&&!Ue({target:_},"scrollbarRail")&&(t.value=null)}function A(){const{value:p}=D,{tmNode:_}=e;s.value&&!p&&!_.disabled&&(o.doSelect(_.key,_.rawNode),o.doUpdateShow(!1))}return{labelField:R,renderLabel:b,renderIcon:w,siblingHasIcon:F.showIconRef,siblingHasSubmenu:F.hasSubmenuRef,menuProps:K,popoverBody:B,animated:u,mergedShowSubmenu:f(()=>X.value&&!W.value),rawNode:q,hasSubmenu:D,pending:ce(()=>{const{value:p}=n,{key:_}=e.tmNode;return p.includes(_)}),childActive:ce(()=>{const{value:p}=c,{key:_}=e.tmNode,j=p.findIndex(ne=>_===ne);return j===-1?!1:j<p.length-1}),active:ce(()=>{const{value:p}=c,{key:_}=e.tmNode,j=p.findIndex(ne=>_===ne);return j===-1?!1:j===p.length-1}),mergedDisabled:$,renderOption:T,nodeProps:O,handleClick:A,handleMouseMove:C,handleMouseEnter:Z,handleMouseLeave:k,handleSubmenuBeforeEnter:E,handleSubmenuAfterEnter:le}},render(){var e,o;const{animated:t,rawNode:r,mergedShowSubmenu:i,clsPrefix:n,siblingHasIcon:c,siblingHasSubmenu:u,renderLabel:s,renderIcon:b,renderOption:w,nodeProps:R,props:m,scrollable:T}=this;let O=null;if(i){const B=(e=this.menuProps)===null||e===void 0?void 0:e.call(this,r,r.children);O=d(io,Object.assign({},B,{clsPrefix:n,scrollable:this.scrollable,tmNodes:this.tmNode.children,parentKey:this.tmNode.key}))}const K={class:[`${n}-dropdown-option-body`,this.pending&&`${n}-dropdown-option-body--pending`,this.active&&`${n}-dropdown-option-body--active`,this.childActive&&`${n}-dropdown-option-body--child-active`,this.mergedDisabled&&`${n}-dropdown-option-body--disabled`],onMousemove:this.handleMouseMove,onMouseenter:this.handleMouseEnter,onMouseleave:this.handleMouseLeave,onClick:this.handleClick},S=R==null?void 0:R(r),F=d("div",Object.assign({class:[`${n}-dropdown-option`,S==null?void 0:S.class],"data-dropdown-option":!0},S),d("div",we(K,m),[d("div",{class:[`${n}-dropdown-option-body__prefix`,c&&`${n}-dropdown-option-body__prefix--show-icon`]},[b?b(r):oe(r.icon)]),d("div",{"data-dropdown-option":!0,class:`${n}-dropdown-option-body__label`},s?s(r):oe((o=r[this.labelField])!==null&&o!==void 0?o:r.title)),d("div",{"data-dropdown-option":!0,class:[`${n}-dropdown-option-body__suffix`,u&&`${n}-dropdown-option-body__suffix--has-submenu`]},this.hasSubmenu?d(ht,null,{default:()=>d(oo,null)}):null)]),this.hasSubmenu?d(Qo,null,{default:()=>[d(Zo,null,{default:()=>d("div",{class:`${n}-dropdown-offset-container`},d(Jo,{show:this.mergedShowSubmenu,placement:this.placement,to:T&&this.popoverBody||void 0,teleportDisabled:!T},{default:()=>d("div",{class:`${n}-dropdown-menu-wrapper`},t?d(Ye,{onBeforeEnter:this.handleSubmenuBeforeEnter,onAfterEnter:this.handleSubmenuAfterEnter,name:"fade-in-scale-up-transition",appear:!0},{default:()=>O}):O)}))})]}):null);return w?w({node:F,option:r}):F}}),ft=M({name:"NDropdownGroup",props:{clsPrefix:{type:String,required:!0},tmNode:{type:Object,required:!0},parentKey:{type:[String,Number],default:null}},render(){const{tmNode:e,parentKey:o,clsPrefix:t}=this,{children:r}=e;return d(Qe,null,d(ct,{clsPrefix:t,tmNode:e,key:e.key}),r==null?void 0:r.map(i=>{const{rawNode:n}=i;return n.show===!1?null:no(n)?d(to,{clsPrefix:t,key:i.key}):i.isGroup?(We("dropdown","`group` node is not allowed to be put in `group` node."),null):d(ro,{clsPrefix:t,tmNode:i,parentKey:o,key:i.key})}))}}),gt=M({name:"DropdownRenderOption",props:{tmNode:{type:Object,required:!0}},render(){const{rawNode:{render:e,props:o}}=this.tmNode;return d("div",o,[e==null?void 0:e()])}}),io=M({name:"DropdownMenu",props:{scrollable:Boolean,showArrow:Boolean,arrowStyle:[String,Object],clsPrefix:{type:String,required:!0},tmNodes:{type:Array,default:()=>[]},parentKey:{type:[String,Number],default:null}},setup(e){const{renderIconRef:o,childrenFieldRef:t}=V(ze);J($e,{showIconRef:f(()=>{const i=o.value;return e.tmNodes.some(n=>{var c;if(n.isGroup)return(c=n.children)===null||c===void 0?void 0:c.some(({rawNode:s})=>i?i(s):s.icon);const{rawNode:u}=n;return i?i(u):u.icon})}),hasSubmenuRef:f(()=>{const{value:i}=t;return e.tmNodes.some(n=>{var c;if(n.isGroup)return(c=n.children)===null||c===void 0?void 0:c.some(({rawNode:s})=>ke(s,i));const{rawNode:u}=n;return ke(u,i)})})});const r=L(null);return J(xo,null),J(wo,null),J(Xe,r),{bodyRef:r}},render(){const{parentKey:e,clsPrefix:o,scrollable:t}=this,r=this.tmNodes.map(i=>{const{rawNode:n}=i;return n.show===!1?null:mt(n)?d(gt,{tmNode:i,key:i.key}):no(n)?d(to,{clsPrefix:o,key:i.key}):pt(n)?d(ft,{clsPrefix:o,tmNode:i,parentKey:e,key:i.key}):d(ro,{clsPrefix:o,tmNode:i,parentKey:e,key:i.key,props:n.props,scrollable:t})});return d("div",{class:[`${o}-dropdown-menu`,t&&`${o}-dropdown-menu--scrollable`],ref:"bodyRef"},t?d(yo,{contentClass:`${o}-dropdown-menu__content`},{default:()=>r}):r,this.showArrow?Xo({clsPrefix:o,arrowStyle:this.arrowStyle,arrowClass:void 0,arrowWrapperClass:void 0,arrowWrapperStyle:void 0}):null)}}),bt=h("dropdown-menu",`
 transform-origin: var(--v-transform-origin);
 background-color: var(--n-color);
 border-radius: var(--n-border-radius);
 box-shadow: var(--n-box-shadow);
 position: relative;
 transition:
 background-color .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier);
`,[Co(),h("dropdown-option",`
 position: relative;
 `,[z("a",`
 text-decoration: none;
 color: inherit;
 outline: none;
 `,[z("&::before",`
 content: "";
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 `)]),h("dropdown-option-body",`
 display: flex;
 cursor: pointer;
 position: relative;
 height: var(--n-option-height);
 line-height: var(--n-option-height);
 font-size: var(--n-font-size);
 color: var(--n-option-text-color);
 transition: color .3s var(--n-bezier);
 `,[z("&::before",`
 content: "";
 position: absolute;
 top: 0;
 bottom: 0;
 left: 4px;
 right: 4px;
 transition: background-color .3s var(--n-bezier);
 border-radius: var(--n-border-radius);
 `),se("disabled",[I("pending",`
 color: var(--n-option-text-color-hover);
 `,[v("prefix, suffix",`
 color: var(--n-option-text-color-hover);
 `),z("&::before","background-color: var(--n-option-color-hover);")]),I("active",`
 color: var(--n-option-text-color-active);
 `,[v("prefix, suffix",`
 color: var(--n-option-text-color-active);
 `),z("&::before","background-color: var(--n-option-color-active);")]),I("child-active",`
 color: var(--n-option-text-color-child-active);
 `,[v("prefix, suffix",`
 color: var(--n-option-text-color-child-active);
 `)])]),I("disabled",`
 cursor: not-allowed;
 opacity: var(--n-option-opacity-disabled);
 `),I("group",`
 font-size: calc(var(--n-font-size) - 1px);
 color: var(--n-group-header-text-color);
 `,[v("prefix",`
 width: calc(var(--n-option-prefix-width) / 2);
 `,[I("show-icon",`
 width: calc(var(--n-option-icon-prefix-width) / 2);
 `)])]),v("prefix",`
 width: var(--n-option-prefix-width);
 display: flex;
 justify-content: center;
 align-items: center;
 color: var(--n-prefix-color);
 transition: color .3s var(--n-bezier);
 z-index: 1;
 `,[I("show-icon",`
 width: var(--n-option-icon-prefix-width);
 `),h("icon",`
 font-size: var(--n-option-icon-size);
 `)]),v("label",`
 white-space: nowrap;
 flex: 1;
 z-index: 1;
 `),v("suffix",`
 box-sizing: border-box;
 flex-grow: 0;
 flex-shrink: 0;
 display: flex;
 justify-content: flex-end;
 align-items: center;
 min-width: var(--n-option-suffix-width);
 padding: 0 8px;
 transition: color .3s var(--n-bezier);
 color: var(--n-suffix-color);
 z-index: 1;
 `,[I("has-submenu",`
 width: var(--n-option-icon-suffix-width);
 `),h("icon",`
 font-size: var(--n-option-icon-size);
 `)]),h("dropdown-menu","pointer-events: all;")]),h("dropdown-offset-container",`
 pointer-events: none;
 position: absolute;
 left: 0;
 right: 0;
 top: -4px;
 bottom: -4px;
 `)]),h("dropdown-divider",`
 transition: background-color .3s var(--n-bezier);
 background-color: var(--n-divider-color);
 height: 1px;
 margin: 4px 0;
 `),h("dropdown-menu-wrapper",`
 transform-origin: var(--v-transform-origin);
 width: fit-content;
 `),z(">",[h("scrollbar",`
 height: inherit;
 max-height: inherit;
 `)]),se("scrollable",`
 padding: var(--n-padding);
 `),I("scrollable",[v("content",`
 padding: var(--n-padding);
 `)])]),yt={animated:{type:Boolean,default:!0},keyboard:{type:Boolean,default:!0},size:String,inverted:Boolean,placement:{type:String,default:"bottom"},onSelect:[Function,Array],options:{type:Array,default:()=>[]},menuProps:Function,showArrow:Boolean,renderLabel:Function,renderIcon:Function,renderOption:Function,nodeProps:Function,labelField:{type:String,default:"label"},keyField:{type:String,default:"key"},childrenField:{type:String,default:"children"},value:[String,Number]},xt=Object.keys(Ke),wt=Object.assign(Object.assign(Object.assign({},Ke),yt),te.props),Ct=M({name:"Dropdown",inheritAttrs:!1,props:wt,setup(e){const o=L(!1),t=xe(Y(e,"show"),o),r=f(()=>{const{keyField:C,childrenField:k}=e;return ye(e.options,{getKey(A){return A[C]},getDisabled(A){return A.disabled===!0},getIgnored(A){return A.type==="divider"||A.type==="render"},getChildren(A){return A[k]}})}),i=f(()=>r.value.treeNodes),n=L(null),c=L(null),u=L(null),s=f(()=>{var C,k,A;return(A=(k=(C=n.value)!==null&&C!==void 0?C:c.value)!==null&&k!==void 0?k:u.value)!==null&&A!==void 0?A:null}),b=f(()=>r.value.getPath(s.value).keyPath),w=f(()=>r.value.getPath(e.value).keyPath),R=ce(()=>e.keyboard&&t.value);rt({keydown:{ArrowUp:{prevent:!0,handler:N},ArrowRight:{prevent:!0,handler:P},ArrowDown:{prevent:!0,handler:X},ArrowLeft:{prevent:!0,handler:$},Enter:{prevent:!0,handler:W},Escape:D}},R);const{mergedClsPrefixRef:m,inlineThemeDisabled:T,mergedComponentPropsRef:O}=ve(e),K=f(()=>{var C,k;return e.size||((k=(C=O==null?void 0:O.value)===null||C===void 0?void 0:C.Dropdown)===null||k===void 0?void 0:k.size)||"medium"}),S=te("Dropdown","-dropdown",bt,zo,e,m);J(ze,{labelFieldRef:Y(e,"labelField"),childrenFieldRef:Y(e,"childrenField"),renderLabelRef:Y(e,"renderLabel"),renderIconRef:Y(e,"renderIcon"),hoverKeyRef:n,keyboardKeyRef:c,lastToggledSubmenuKeyRef:u,pendingKeyPathRef:b,activeKeyPathRef:w,animatedRef:Y(e,"animated"),mergedShowRef:t,nodePropsRef:Y(e,"nodeProps"),renderOptionRef:Y(e,"renderOption"),menuPropsRef:Y(e,"menuProps"),doSelect:F,doUpdateShow:B}),Te(t,C=>{!e.animated&&!C&&q()});function F(C,k){const{onSelect:A}=e;A&&G(A,C,k)}function B(C){const{"onUpdate:show":k,onUpdateShow:A}=e;k&&G(k,C),A&&G(A,C),o.value=C}function q(){n.value=null,c.value=null,u.value=null}function D(){B(!1)}function $(){E("left")}function P(){E("right")}function N(){E("up")}function X(){E("down")}function W(){const C=ee();C!=null&&C.isLeaf&&t.value&&(F(C.key,C.rawNode),B(!1))}function ee(){var C;const{value:k}=r,{value:A}=s;return!k||A===null?null:(C=k.getNode(A))!==null&&C!==void 0?C:null}function E(C){const{value:k}=s,{value:{getFirstAvailableNode:A}}=r;let p=null;if(k===null){const _=A();_!==null&&(p=_.key)}else{const _=ee();if(_){let j;switch(C){case"down":j=_.getNext();break;case"up":j=_.getPrev();break;case"right":j=_.getChild();break;case"left":j=_.getParent();break}j&&(p=j.key)}}p!==null&&(n.value=null,c.value=p)}const le=f(()=>{const{inverted:C}=e,k=K.value,{common:{cubicBezierEaseInOut:A},self:p}=S.value,{padding:_,dividerColor:j,borderRadius:ne,optionOpacityDisabled:g,[ae("optionIconSuffixWidth",k)]:y,[ae("optionSuffixWidth",k)]:a,[ae("optionIconPrefixWidth",k)]:x,[ae("optionPrefixWidth",k)]:H,[ae("fontSize",k)]:Se,[ae("optionHeight",k)]:Ie,[ae("optionIconSize",k)]:Re}=p,l={"--n-bezier":A,"--n-font-size":Se,"--n-padding":_,"--n-border-radius":ne,"--n-option-height":Ie,"--n-option-prefix-width":H,"--n-option-icon-prefix-width":x,"--n-option-suffix-width":a,"--n-option-icon-suffix-width":y,"--n-option-icon-size":Re,"--n-divider-color":j,"--n-option-opacity-disabled":g};return C?(l["--n-color"]=p.colorInverted,l["--n-option-color-hover"]=p.optionColorHoverInverted,l["--n-option-color-active"]=p.optionColorActiveInverted,l["--n-option-text-color"]=p.optionTextColorInverted,l["--n-option-text-color-hover"]=p.optionTextColorHoverInverted,l["--n-option-text-color-active"]=p.optionTextColorActiveInverted,l["--n-option-text-color-child-active"]=p.optionTextColorChildActiveInverted,l["--n-prefix-color"]=p.prefixColorInverted,l["--n-suffix-color"]=p.suffixColorInverted,l["--n-group-header-text-color"]=p.groupHeaderTextColorInverted):(l["--n-color"]=p.color,l["--n-option-color-hover"]=p.optionColorHover,l["--n-option-color-active"]=p.optionColorActive,l["--n-option-text-color"]=p.optionTextColor,l["--n-option-text-color-hover"]=p.optionTextColorHover,l["--n-option-text-color-active"]=p.optionTextColorActive,l["--n-option-text-color-child-active"]=p.optionTextColorChildActive,l["--n-prefix-color"]=p.prefixColor,l["--n-suffix-color"]=p.suffixColor,l["--n-group-header-text-color"]=p.groupHeaderTextColor),l}),Z=T?Ce("dropdown",f(()=>`${K.value[0]}${e.inverted?"i":""}`),le,e):void 0;return{mergedClsPrefix:m,mergedTheme:S,mergedSize:K,tmNodes:i,mergedShow:t,handleAfterLeave:()=>{e.animated&&q()},doUpdateShow:B,cssVars:T?void 0:le,themeClass:Z==null?void 0:Z.themeClass,onRender:Z==null?void 0:Z.onRender}},render(){const e=(r,i,n,c,u)=>{var s;const{mergedClsPrefix:b,menuProps:w}=this;(s=this.onRender)===null||s===void 0||s.call(this);const R=(w==null?void 0:w(void 0,this.tmNodes.map(T=>T.rawNode)))||{},m={ref:lt(i),class:[r,`${b}-dropdown`,`${b}-dropdown--${this.mergedSize}-size`,this.themeClass],clsPrefix:b,tmNodes:this.tmNodes,style:[...n,this.cssVars],showArrow:this.showArrow,arrowStyle:this.arrowStyle,scrollable:this.scrollable,onMouseenter:c,onMouseleave:u};return d(io,we(this.$attrs,m,R))},{mergedTheme:o}=this,t={show:this.mergedShow,theme:o.peers.Popover,themeOverrides:o.peerOverrides.Popover,internalOnAfterLeave:this.handleAfterLeave,internalRenderBody:e,onUpdateShow:this.doUpdateShow,"onUpdate:show":void 0};return d(eo,Object.assign({},ge(this.$props,xt),t),{trigger:()=>{var r,i;return(i=(r=this.$slots).default)===null||i===void 0?void 0:i.call(r)}})}}),zt=h("layout-sider",`
 flex-shrink: 0;
 box-sizing: border-box;
 position: relative;
 z-index: 1;
 color: var(--n-text-color);
 transition:
 color .3s var(--n-bezier),
 border-color .3s var(--n-bezier),
 min-width .3s var(--n-bezier),
 max-width .3s var(--n-bezier),
 transform .3s var(--n-bezier),
 background-color .3s var(--n-bezier);
 background-color: var(--n-color);
 display: flex;
 justify-content: flex-end;
`,[I("bordered",[v("border",`
 content: "";
 position: absolute;
 top: 0;
 bottom: 0;
 width: 1px;
 background-color: var(--n-border-color);
 transition: background-color .3s var(--n-bezier);
 `)]),v("left-placement",[I("bordered",[v("border",`
 right: 0;
 `)])]),I("right-placement",`
 justify-content: flex-start;
 `,[I("bordered",[v("border",`
 left: 0;
 `)]),I("collapsed",[h("layout-toggle-button",[h("base-icon",`
 transform: rotate(180deg);
 `)]),h("layout-toggle-bar",[z("&:hover",[v("top",{transform:"rotate(-12deg) scale(1.15) translateY(-2px)"}),v("bottom",{transform:"rotate(12deg) scale(1.15) translateY(2px)"})])])]),h("layout-toggle-button",`
 left: 0;
 transform: translateX(-50%) translateY(-50%);
 `,[h("base-icon",`
 transform: rotate(0);
 `)]),h("layout-toggle-bar",`
 left: -28px;
 transform: rotate(180deg);
 `,[z("&:hover",[v("top",{transform:"rotate(12deg) scale(1.15) translateY(-2px)"}),v("bottom",{transform:"rotate(-12deg) scale(1.15) translateY(2px)"})])])]),I("collapsed",[h("layout-toggle-bar",[z("&:hover",[v("top",{transform:"rotate(-12deg) scale(1.15) translateY(-2px)"}),v("bottom",{transform:"rotate(12deg) scale(1.15) translateY(2px)"})])]),h("layout-toggle-button",[h("base-icon",`
 transform: rotate(0);
 `)])]),h("layout-toggle-button",`
 transition:
 color .3s var(--n-bezier),
 right .3s var(--n-bezier),
 left .3s var(--n-bezier),
 border-color .3s var(--n-bezier),
 background-color .3s var(--n-bezier);
 cursor: pointer;
 width: 24px;
 height: 24px;
 position: absolute;
 top: 50%;
 right: 0;
 border-radius: 50%;
 display: flex;
 align-items: center;
 justify-content: center;
 font-size: 18px;
 color: var(--n-toggle-button-icon-color);
 border: var(--n-toggle-button-border);
 background-color: var(--n-toggle-button-color);
 box-shadow: 0 2px 4px 0px rgba(0, 0, 0, .06);
 transform: translateX(50%) translateY(-50%);
 z-index: 1;
 `,[h("base-icon",`
 transition: transform .3s var(--n-bezier);
 transform: rotate(180deg);
 `)]),h("layout-toggle-bar",`
 cursor: pointer;
 height: 72px;
 width: 32px;
 position: absolute;
 top: calc(50% - 36px);
 right: -28px;
 `,[v("top, bottom",`
 position: absolute;
 width: 4px;
 border-radius: 2px;
 height: 38px;
 left: 14px;
 transition: 
 background-color .3s var(--n-bezier),
 transform .3s var(--n-bezier);
 `),v("bottom",`
 position: absolute;
 top: 34px;
 `),z("&:hover",[v("top",{transform:"rotate(12deg) scale(1.15) translateY(-2px)"}),v("bottom",{transform:"rotate(-12deg) scale(1.15) translateY(2px)"})]),v("top, bottom",{backgroundColor:"var(--n-toggle-bar-color)"}),z("&:hover",[v("top, bottom",{backgroundColor:"var(--n-toggle-bar-color-hover)"})])]),v("border",`
 position: absolute;
 top: 0;
 right: 0;
 bottom: 0;
 width: 1px;
 transition: background-color .3s var(--n-bezier);
 `),h("layout-sider-scroll-container",`
 flex-grow: 1;
 flex-shrink: 0;
 box-sizing: border-box;
 height: 100%;
 opacity: 0;
 transition: opacity .3s var(--n-bezier);
 max-width: 100%;
 `),I("show-content",[h("layout-sider-scroll-container",{opacity:1})]),I("absolute-positioned",`
 position: absolute;
 left: 0;
 top: 0;
 bottom: 0;
 `)]),St=M({props:{clsPrefix:{type:String,required:!0},onClick:Function},render(){const{clsPrefix:e}=this;return d("div",{onClick:this.onClick,class:`${e}-layout-toggle-bar`},d("div",{class:`${e}-layout-toggle-bar__top`}),d("div",{class:`${e}-layout-toggle-bar__bottom`}))}}),It=M({name:"LayoutToggleButton",props:{clsPrefix:{type:String,required:!0},onClick:Function},render(){const{clsPrefix:e}=this;return d("div",{class:`${e}-layout-toggle-button`,onClick:this.onClick},d(Ze,{clsPrefix:e},{default:()=>d(oo,null)}))}}),Rt={position:Uo,bordered:Boolean,collapsedWidth:{type:Number,default:48},width:{type:[Number,String],default:272},contentClass:String,contentStyle:{type:[String,Object],default:""},collapseMode:{type:String,default:"transform"},collapsed:{type:Boolean,default:void 0},defaultCollapsed:Boolean,showCollapsedContent:{type:Boolean,default:!0},showTrigger:{type:[Boolean,String],default:!1},nativeScrollbar:{type:Boolean,default:!0},inverted:Boolean,scrollbarProps:Object,triggerClass:String,triggerStyle:[String,Object],collapsedTriggerClass:String,collapsedTriggerStyle:[String,Object],"onUpdate:collapsed":[Function,Array],onUpdateCollapsed:[Function,Array],onAfterEnter:Function,onAfterLeave:Function,onExpand:[Function,Array],onCollapse:[Function,Array],onScroll:Function},Pt=M({name:"LayoutSider",props:Object.assign(Object.assign({},te.props),Rt),setup(e){const o=V(Go),t=L(null),r=L(null),i=L(e.defaultCollapsed),n=xe(Y(e,"collapsed"),i),c=f(()=>be(n.value?e.collapsedWidth:e.width)),u=f(()=>e.collapseMode!=="transform"?{}:{minWidth:be(e.width)}),s=f(()=>o?o.siderPlacement:"left");function b($,P){if(e.nativeScrollbar){const{value:N}=t;N&&(P===void 0?N.scrollTo($):N.scrollTo($,P))}else{const{value:N}=r;N&&N.scrollTo($,P)}}function w(){const{"onUpdate:collapsed":$,onUpdateCollapsed:P,onExpand:N,onCollapse:X}=e,{value:W}=n;P&&G(P,!W),$&&G($,!W),i.value=!W,W?N&&G(N):X&&G(X)}let R=0,m=0;const T=$=>{var P;const N=$.target;R=N.scrollLeft,m=N.scrollTop,(P=e.onScroll)===null||P===void 0||P.call(e,$)};Io(()=>{if(e.nativeScrollbar){const $=t.value;$&&($.scrollTop=m,$.scrollLeft=R)}}),J(Je,{collapsedRef:n,collapseModeRef:Y(e,"collapseMode")});const{mergedClsPrefixRef:O,inlineThemeDisabled:K}=ve(e),S=te("Layout","-layout-sider",zt,Vo,e,O);function F($){var P,N;$.propertyName==="max-width"&&(n.value?(P=e.onAfterLeave)===null||P===void 0||P.call(e):(N=e.onAfterEnter)===null||N===void 0||N.call(e))}const B={scrollTo:b},q=f(()=>{const{common:{cubicBezierEaseInOut:$},self:P}=S.value,{siderToggleButtonColor:N,siderToggleButtonBorder:X,siderToggleBarColor:W,siderToggleBarColorHover:ee}=P,E={"--n-bezier":$,"--n-toggle-button-color":N,"--n-toggle-button-border":X,"--n-toggle-bar-color":W,"--n-toggle-bar-color-hover":ee};return e.inverted?(E["--n-color"]=P.siderColorInverted,E["--n-text-color"]=P.textColorInverted,E["--n-border-color"]=P.siderBorderColorInverted,E["--n-toggle-button-icon-color"]=P.siderToggleButtonIconColorInverted,E.__invertScrollbar=P.__invertScrollbar):(E["--n-color"]=P.siderColor,E["--n-text-color"]=P.textColor,E["--n-border-color"]=P.siderBorderColor,E["--n-toggle-button-icon-color"]=P.siderToggleButtonIconColor),E}),D=K?Ce("layout-sider",f(()=>e.inverted?"a":"b"),q,e):void 0;return Object.assign({scrollableElRef:t,scrollbarInstRef:r,mergedClsPrefix:O,mergedTheme:S,styleMaxWidth:c,mergedCollapsed:n,scrollContainerStyle:u,siderPlacement:s,handleNativeElScroll:T,handleTransitionend:F,handleTriggerClick:w,inlineThemeDisabled:K,cssVars:q,themeClass:D==null?void 0:D.themeClass,onRender:D==null?void 0:D.onRender},B)},render(){var e;const{mergedClsPrefix:o,mergedCollapsed:t,showTrigger:r}=this;return(e=this.onRender)===null||e===void 0||e.call(this),d("aside",{class:[`${o}-layout-sider`,this.themeClass,`${o}-layout-sider--${this.position}-positioned`,`${o}-layout-sider--${this.siderPlacement}-placement`,this.bordered&&`${o}-layout-sider--bordered`,t&&`${o}-layout-sider--collapsed`,(!t||this.showCollapsedContent)&&`${o}-layout-sider--show-content`],onTransitionend:this.handleTransitionend,style:[this.inlineThemeDisabled?void 0:this.cssVars,{maxWidth:this.styleMaxWidth,width:be(this.width)}]},this.nativeScrollbar?d("div",{class:[`${o}-layout-sider-scroll-container`,this.contentClass],onScroll:this.handleNativeElScroll,style:[this.scrollContainerStyle,{overflow:"auto"},this.contentStyle],ref:"scrollableElRef"},this.$slots):d(So,Object.assign({},this.scrollbarProps,{onScroll:this.onScroll,ref:"scrollbarInstRef",style:this.scrollContainerStyle,contentStyle:this.contentStyle,contentClass:this.contentClass,theme:this.mergedTheme.peers.Scrollbar,themeOverrides:this.mergedTheme.peerOverrides.Scrollbar,builtinThemeOverrides:this.inverted&&this.cssVars.__invertScrollbar==="true"?{colorHover:"rgba(255, 255, 255, .4)",color:"rgba(255, 255, 255, .3)"}:void 0}),this.$slots),r?r==="bar"?d(St,{clsPrefix:o,class:t?this.collapsedTriggerClass:this.triggerClass,style:t?this.collapsedTriggerStyle:this.triggerStyle,onClick:this.handleTriggerClick}):d(It,{clsPrefix:o,class:t?this.collapsedTriggerClass:this.triggerClass,style:t?this.collapsedTriggerStyle:this.triggerStyle,onClick:this.handleTriggerClick}):null,this.bordered?d("div",{class:`${o}-layout-sider__border`}):null)}}),he=ue("n-menu"),lo=ue("n-submenu"),He=ue("n-menu-item-group"),Ge=[z("&::before","background-color: var(--n-item-color-hover);"),v("arrow",`
 color: var(--n-arrow-color-hover);
 `),v("icon",`
 color: var(--n-item-icon-color-hover);
 `),h("menu-item-content-header",`
 color: var(--n-item-text-color-hover);
 `,[z("a",`
 color: var(--n-item-text-color-hover);
 `),v("extra",`
 color: var(--n-item-text-color-hover);
 `)])],qe=[v("icon",`
 color: var(--n-item-icon-color-hover-horizontal);
 `),h("menu-item-content-header",`
 color: var(--n-item-text-color-hover-horizontal);
 `,[z("a",`
 color: var(--n-item-text-color-hover-horizontal);
 `),v("extra",`
 color: var(--n-item-text-color-hover-horizontal);
 `)])],Nt=z([h("menu",`
 background-color: var(--n-color);
 color: var(--n-item-text-color);
 overflow: hidden;
 transition: background-color .3s var(--n-bezier);
 box-sizing: border-box;
 font-size: var(--n-font-size);
 padding-bottom: 6px;
 `,[I("horizontal",`
 max-width: 100%;
 width: 100%;
 display: flex;
 overflow: hidden;
 padding-bottom: 0;
 `,[h("submenu","margin: 0;"),h("menu-item","margin: 0;"),h("menu-item-content",`
 padding: 0 20px;
 border-bottom: 2px solid #0000;
 `,[z("&::before","display: none;"),I("selected","border-bottom: 2px solid var(--n-border-color-horizontal)")]),h("menu-item-content",[I("selected",[v("icon","color: var(--n-item-icon-color-active-horizontal);"),h("menu-item-content-header",`
 color: var(--n-item-text-color-active-horizontal);
 `,[z("a","color: var(--n-item-text-color-active-horizontal);"),v("extra","color: var(--n-item-text-color-active-horizontal);")])]),I("child-active",`
 border-bottom: 2px solid var(--n-border-color-horizontal);
 `,[h("menu-item-content-header",`
 color: var(--n-item-text-color-child-active-horizontal);
 `,[z("a",`
 color: var(--n-item-text-color-child-active-horizontal);
 `),v("extra",`
 color: var(--n-item-text-color-child-active-horizontal);
 `)]),v("icon",`
 color: var(--n-item-icon-color-child-active-horizontal);
 `)]),se("disabled",[se("selected, child-active",[z("&:focus-within",qe)]),I("selected",[de(null,[v("icon","color: var(--n-item-icon-color-active-hover-horizontal);"),h("menu-item-content-header",`
 color: var(--n-item-text-color-active-hover-horizontal);
 `,[z("a","color: var(--n-item-text-color-active-hover-horizontal);"),v("extra","color: var(--n-item-text-color-active-hover-horizontal);")])])]),I("child-active",[de(null,[v("icon","color: var(--n-item-icon-color-child-active-hover-horizontal);"),h("menu-item-content-header",`
 color: var(--n-item-text-color-child-active-hover-horizontal);
 `,[z("a","color: var(--n-item-text-color-child-active-hover-horizontal);"),v("extra","color: var(--n-item-text-color-child-active-hover-horizontal);")])])]),de("border-bottom: 2px solid var(--n-border-color-horizontal);",qe)]),h("menu-item-content-header",[z("a","color: var(--n-item-text-color-horizontal);")])])]),se("responsive",[h("menu-item-content-header",`
 overflow: hidden;
 text-overflow: ellipsis;
 `)]),I("collapsed",[h("menu-item-content",[I("selected",[z("&::before",`
 background-color: var(--n-item-color-active-collapsed) !important;
 `)]),h("menu-item-content-header","opacity: 0;"),v("arrow","opacity: 0;"),v("icon","color: var(--n-item-icon-color-collapsed);")])]),h("menu-item",`
 height: var(--n-item-height);
 margin-top: 6px;
 position: relative;
 `),h("menu-item-content",`
 box-sizing: border-box;
 line-height: 1.75;
 height: 100%;
 display: grid;
 grid-template-areas: "icon content arrow";
 grid-template-columns: auto 1fr auto;
 align-items: center;
 cursor: pointer;
 position: relative;
 padding-right: 18px;
 transition:
 background-color .3s var(--n-bezier),
 padding-left .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 `,[z("> *","z-index: 1;"),z("&::before",`
 z-index: auto;
 content: "";
 background-color: #0000;
 position: absolute;
 left: 8px;
 right: 8px;
 top: 0;
 bottom: 0;
 pointer-events: none;
 border-radius: var(--n-border-radius);
 transition: background-color .3s var(--n-bezier);
 `),I("disabled",`
 opacity: .45;
 cursor: not-allowed;
 `),I("collapsed",[v("arrow","transform: rotate(0);")]),I("selected",[z("&::before","background-color: var(--n-item-color-active);"),v("arrow","color: var(--n-arrow-color-active);"),v("icon","color: var(--n-item-icon-color-active);"),h("menu-item-content-header",`
 color: var(--n-item-text-color-active);
 `,[z("a","color: var(--n-item-text-color-active);"),v("extra","color: var(--n-item-text-color-active);")])]),I("child-active",[h("menu-item-content-header",`
 color: var(--n-item-text-color-child-active);
 `,[z("a",`
 color: var(--n-item-text-color-child-active);
 `),v("extra",`
 color: var(--n-item-text-color-child-active);
 `)]),v("arrow",`
 color: var(--n-arrow-color-child-active);
 `),v("icon",`
 color: var(--n-item-icon-color-child-active);
 `)]),se("disabled",[se("selected, child-active",[z("&:focus-within",Ge)]),I("selected",[de(null,[v("arrow","color: var(--n-arrow-color-active-hover);"),v("icon","color: var(--n-item-icon-color-active-hover);"),h("menu-item-content-header",`
 color: var(--n-item-text-color-active-hover);
 `,[z("a","color: var(--n-item-text-color-active-hover);"),v("extra","color: var(--n-item-text-color-active-hover);")])])]),I("child-active",[de(null,[v("arrow","color: var(--n-arrow-color-child-active-hover);"),v("icon","color: var(--n-item-icon-color-child-active-hover);"),h("menu-item-content-header",`
 color: var(--n-item-text-color-child-active-hover);
 `,[z("a","color: var(--n-item-text-color-child-active-hover);"),v("extra","color: var(--n-item-text-color-child-active-hover);")])])]),I("selected",[de(null,[z("&::before","background-color: var(--n-item-color-active-hover);")])]),de(null,Ge)]),v("icon",`
 grid-area: icon;
 color: var(--n-item-icon-color);
 transition:
 color .3s var(--n-bezier),
 font-size .3s var(--n-bezier),
 margin-right .3s var(--n-bezier);
 box-sizing: content-box;
 display: inline-flex;
 align-items: center;
 justify-content: center;
 `),v("arrow",`
 grid-area: arrow;
 font-size: 16px;
 color: var(--n-arrow-color);
 transform: rotate(180deg);
 opacity: 1;
 transition:
 color .3s var(--n-bezier),
 transform 0.2s var(--n-bezier),
 opacity 0.2s var(--n-bezier);
 `),h("menu-item-content-header",`
 grid-area: content;
 transition:
 color .3s var(--n-bezier),
 opacity .3s var(--n-bezier);
 opacity: 1;
 white-space: nowrap;
 color: var(--n-item-text-color);
 `,[z("a",`
 outline: none;
 text-decoration: none;
 transition: color .3s var(--n-bezier);
 color: var(--n-item-text-color);
 `,[z("&::before",`
 content: "";
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 `)]),v("extra",`
 font-size: .93em;
 color: var(--n-group-text-color);
 transition: color .3s var(--n-bezier);
 `)])]),h("submenu",`
 cursor: pointer;
 position: relative;
 margin-top: 6px;
 `,[h("menu-item-content",`
 height: var(--n-item-height);
 `),h("submenu-children",`
 overflow: hidden;
 padding: 0;
 `,[Ro({duration:".2s"})])]),h("menu-item-group",[h("menu-item-group-title",`
 margin-top: 6px;
 color: var(--n-group-text-color);
 cursor: default;
 font-size: .93em;
 height: 36px;
 display: flex;
 align-items: center;
 transition:
 padding-left .3s var(--n-bezier),
 color .3s var(--n-bezier);
 `)])]),h("menu-tooltip",[z("a",`
 color: inherit;
 text-decoration: none;
 `)]),h("menu-divider",`
 transition: background-color .3s var(--n-bezier);
 background-color: var(--n-divider-color);
 height: 1px;
 margin: 6px 18px;
 `)]);function de(e,o){return[I("hover",e,o),z("&:hover",e,o)]}const ao=M({name:"MenuOptionContent",props:{collapsed:Boolean,disabled:Boolean,title:[String,Function],icon:Function,extra:[String,Function],showArrow:Boolean,childActive:Boolean,hover:Boolean,paddingLeft:Number,selected:Boolean,maxIconSize:{type:Number,required:!0},activeIconSize:{type:Number,required:!0},iconMarginRight:{type:Number,required:!0},clsPrefix:{type:String,required:!0},onClick:Function,tmNode:{type:Object,required:!0},isEllipsisPlaceholder:Boolean},setup(e){const{props:o}=V(he);return{menuProps:o,style:f(()=>{const{paddingLeft:t}=e;return{paddingLeft:t&&`${t}px`}}),iconStyle:f(()=>{const{maxIconSize:t,activeIconSize:r,iconMarginRight:i}=e;return{width:`${t}px`,height:`${t}px`,fontSize:`${r}px`,marginRight:`${i}px`}})}},render(){const{clsPrefix:e,tmNode:o,menuProps:{renderIcon:t,renderLabel:r,renderExtra:i,expandIcon:n}}=this,c=t?t(o.rawNode):oe(this.icon);return d("div",{onClick:u=>{var s;(s=this.onClick)===null||s===void 0||s.call(this,u)},role:"none",class:[`${e}-menu-item-content`,{[`${e}-menu-item-content--selected`]:this.selected,[`${e}-menu-item-content--collapsed`]:this.collapsed,[`${e}-menu-item-content--child-active`]:this.childActive,[`${e}-menu-item-content--disabled`]:this.disabled,[`${e}-menu-item-content--hover`]:this.hover}],style:this.style},c&&d("div",{class:`${e}-menu-item-content__icon`,style:this.iconStyle,role:"none"},[c]),d("div",{class:`${e}-menu-item-content-header`,role:"none"},this.isEllipsisPlaceholder?this.title:r?r(o.rawNode):oe(this.title),this.extra||i?d("span",{class:`${e}-menu-item-content-header__extra`}," ",i?i(o.rawNode):oe(this.extra)):null),this.showArrow?d(Ze,{ariaHidden:!0,class:`${e}-menu-item-content__arrow`,clsPrefix:e},{default:()=>n?n(o.rawNode):d(at,null)}):null)}}),fe=8;function Fe(e){const o=V(he),{props:t,mergedCollapsedRef:r}=o,i=V(lo,null),n=V(He,null),c=f(()=>t.mode==="horizontal"),u=f(()=>c.value?t.dropdownPlacement:"tmNodes"in e?"right-start":"right"),s=f(()=>{var m;return Math.max((m=t.collapsedIconSize)!==null&&m!==void 0?m:t.iconSize,t.iconSize)}),b=f(()=>{var m;return!c.value&&e.root&&r.value&&(m=t.collapsedIconSize)!==null&&m!==void 0?m:t.iconSize}),w=f(()=>{if(c.value)return;const{collapsedWidth:m,indent:T,rootIndent:O}=t,{root:K,isGroup:S}=e,F=O===void 0?T:O;return K?r.value?m/2-s.value/2:F:n&&typeof n.paddingLeftRef.value=="number"?T/2+n.paddingLeftRef.value:i&&typeof i.paddingLeftRef.value=="number"?(S?T/2:T)+i.paddingLeftRef.value:0}),R=f(()=>{const{collapsedWidth:m,indent:T,rootIndent:O}=t,{value:K}=s,{root:S}=e;return c.value||!S||!r.value?fe:(O===void 0?T:O)+K+fe-(m+K)/2});return{dropdownPlacement:u,activeIconSize:b,maxIconSize:s,paddingLeft:w,iconMarginRight:R,NMenu:o,NSubmenu:i,NMenuOptionGroup:n}}const Ee={internalKey:{type:[String,Number],required:!0},root:Boolean,isGroup:Boolean,level:{type:Number,required:!0},title:[String,Function],extra:[String,Function]},kt=M({name:"MenuDivider",setup(){const e=V(he),{mergedClsPrefixRef:o,isHorizontalRef:t}=e;return()=>t.value?null:d("div",{class:`${o.value}-menu-divider`})}}),so=Object.assign(Object.assign({},Ee),{tmNode:{type:Object,required:!0},disabled:Boolean,icon:Function,onClick:Function}),_t=Oe(so),At=M({name:"MenuOption",props:so,setup(e){const o=Fe(e),{NSubmenu:t,NMenu:r,NMenuOptionGroup:i}=o,{props:n,mergedClsPrefixRef:c,mergedCollapsedRef:u}=r,s=t?t.mergedDisabledRef:i?i.mergedDisabledRef:{value:!1},b=f(()=>s.value||e.disabled);function w(m){const{onClick:T}=e;T&&T(m)}function R(m){b.value||(r.doSelect(e.internalKey,e.tmNode.rawNode),w(m))}return{mergedClsPrefix:c,dropdownPlacement:o.dropdownPlacement,paddingLeft:o.paddingLeft,iconMarginRight:o.iconMarginRight,maxIconSize:o.maxIconSize,activeIconSize:o.activeIconSize,mergedTheme:r.mergedThemeRef,menuProps:n,dropdownEnabled:ce(()=>e.root&&u.value&&n.mode!=="horizontal"&&!b.value),selected:ce(()=>r.mergedValueRef.value===e.internalKey),mergedDisabled:b,handleClick:R}},render(){const{mergedClsPrefix:e,mergedTheme:o,tmNode:t,menuProps:{renderLabel:r,nodeProps:i}}=this,n=i==null?void 0:i(t.rawNode);return d("div",Object.assign({},n,{role:"menuitem",class:[`${e}-menu-item`,n==null?void 0:n.class]}),d(st,{theme:o.peers.Tooltip,themeOverrides:o.peerOverrides.Tooltip,trigger:"hover",placement:this.dropdownPlacement,disabled:!this.dropdownEnabled||this.title===void 0,internalExtraClass:["menu-tooltip"]},{default:()=>r?r(t.rawNode):oe(this.title),trigger:()=>d(ao,{tmNode:t,clsPrefix:e,paddingLeft:this.paddingLeft,iconMarginRight:this.iconMarginRight,maxIconSize:this.maxIconSize,activeIconSize:this.activeIconSize,selected:this.selected,title:this.title,extra:this.extra,disabled:this.mergedDisabled,icon:this.icon,onClick:this.handleClick})}))}}),co=Object.assign(Object.assign({},Ee),{tmNode:{type:Object,required:!0},tmNodes:{type:Array,required:!0}}),Tt=Oe(co),Ot=M({name:"MenuOptionGroup",props:co,setup(e){const o=Fe(e),{NSubmenu:t}=o,r=f(()=>t!=null&&t.mergedDisabledRef.value?!0:e.tmNode.disabled);J(He,{paddingLeftRef:o.paddingLeft,mergedDisabledRef:r});const{mergedClsPrefixRef:i,props:n}=V(he);return function(){const{value:c}=i,u=o.paddingLeft.value,{nodeProps:s}=n,b=s==null?void 0:s(e.tmNode.rawNode);return d("div",{class:`${c}-menu-item-group`,role:"group"},d("div",Object.assign({},b,{class:[`${c}-menu-item-group-title`,b==null?void 0:b.class],style:[(b==null?void 0:b.style)||"",u!==void 0?`padding-left: ${u}px;`:""]}),oe(e.title),e.extra?d(Qe,null," ",oe(e.extra)):null),d("div",null,e.tmNodes.map(w=>Me(w,n))))}}});function _e(e){return e.type==="divider"||e.type==="render"}function Kt(e){return e.type==="divider"}function Me(e,o){const{rawNode:t}=e,{show:r}=t;if(r===!1)return null;if(_e(t))return Kt(t)?d(kt,Object.assign({key:e.key},t.props)):null;const{labelField:i}=o,{key:n,level:c,isGroup:u}=e,s=Object.assign(Object.assign({},t),{title:t.title||t[i],extra:t.titleExtra||t.extra,key:n,internalKey:n,level:c,root:c===0,isGroup:u});return e.children?e.isGroup?d(Ot,ge(s,Tt,{tmNode:e,tmNodes:e.children,key:n})):d(Ae,ge(s,$t,{key:n,rawNodes:t[o.childrenField],tmNodes:e.children,tmNode:e})):d(At,ge(s,_t,{key:n,tmNode:e}))}const uo=Object.assign(Object.assign({},Ee),{rawNodes:{type:Array,default:()=>[]},tmNodes:{type:Array,default:()=>[]},tmNode:{type:Object,required:!0},disabled:Boolean,icon:Function,onClick:Function,domId:String,virtualChildActive:{type:Boolean,default:void 0},isEllipsisPlaceholder:Boolean}),$t=Oe(uo),Ae=M({name:"Submenu",props:uo,setup(e){const o=Fe(e),{NMenu:t,NSubmenu:r}=o,{props:i,mergedCollapsedRef:n,mergedThemeRef:c}=t,u=f(()=>{const{disabled:m}=e;return r!=null&&r.mergedDisabledRef.value||i.disabled?!0:m}),s=L(!1);J(lo,{paddingLeftRef:o.paddingLeft,mergedDisabledRef:u}),J(He,null);function b(){const{onClick:m}=e;m&&m()}function w(){u.value||(n.value||t.toggleExpand(e.internalKey),b())}function R(m){s.value=m}return{menuProps:i,mergedTheme:c,doSelect:t.doSelect,inverted:t.invertedRef,isHorizontal:t.isHorizontalRef,mergedClsPrefix:t.mergedClsPrefixRef,maxIconSize:o.maxIconSize,activeIconSize:o.activeIconSize,iconMarginRight:o.iconMarginRight,dropdownPlacement:o.dropdownPlacement,dropdownShow:s,paddingLeft:o.paddingLeft,mergedDisabled:u,mergedValue:t.mergedValueRef,childActive:ce(()=>{var m;return(m=e.virtualChildActive)!==null&&m!==void 0?m:t.activePathRef.value.includes(e.internalKey)}),collapsed:f(()=>i.mode==="horizontal"?!1:n.value?!0:!t.mergedExpandedKeysRef.value.includes(e.internalKey)),dropdownEnabled:f(()=>!u.value&&(i.mode==="horizontal"||n.value)),handlePopoverShowChange:R,handleClick:w}},render(){var e;const{mergedClsPrefix:o,menuProps:{renderIcon:t,renderLabel:r}}=this,i=()=>{const{isHorizontal:c,paddingLeft:u,collapsed:s,mergedDisabled:b,maxIconSize:w,activeIconSize:R,title:m,childActive:T,icon:O,handleClick:K,menuProps:{nodeProps:S},dropdownShow:F,iconMarginRight:B,tmNode:q,mergedClsPrefix:D,isEllipsisPlaceholder:$,extra:P}=this,N=S==null?void 0:S(q.rawNode);return d("div",Object.assign({},N,{class:[`${D}-menu-item`,N==null?void 0:N.class],role:"menuitem"}),d(ao,{tmNode:q,paddingLeft:u,collapsed:s,disabled:b,iconMarginRight:B,maxIconSize:w,activeIconSize:R,title:m,extra:P,showArrow:!c,childActive:T,clsPrefix:D,icon:O,hover:F,onClick:K,isEllipsisPlaceholder:$}))},n=()=>d(Po,null,{default:()=>{const{tmNodes:c,collapsed:u}=this;return u?null:d("div",{class:`${o}-submenu-children`,role:"menu"},c.map(s=>Me(s,this.menuProps)))}});return this.root?d(Ct,Object.assign({size:"large",trigger:"hover"},(e=this.menuProps)===null||e===void 0?void 0:e.dropdownProps,{themeOverrides:this.mergedTheme.peerOverrides.Dropdown,theme:this.mergedTheme.peers.Dropdown,builtinThemeOverrides:{fontSizeLarge:"14px",optionIconSizeLarge:"18px"},value:this.mergedValue,disabled:!this.dropdownEnabled,placement:this.dropdownPlacement,keyField:this.menuProps.keyField,labelField:this.menuProps.labelField,childrenField:this.menuProps.childrenField,onUpdateShow:this.handlePopoverShowChange,options:this.rawNodes,onSelect:this.doSelect,inverted:this.inverted,renderIcon:t,renderLabel:r}),{default:()=>d("div",{class:`${o}-submenu`,role:"menu","aria-expanded":!this.collapsed,id:this.domId},i(),this.isHorizontal?null:n())}):d("div",{class:`${o}-submenu`,role:"menu","aria-expanded":!this.collapsed,id:this.domId},i(),n())}}),Ht=Object.assign(Object.assign({},te.props),{options:{type:Array,default:()=>[]},collapsed:{type:Boolean,default:void 0},collapsedWidth:{type:Number,default:48},iconSize:{type:Number,default:20},collapsedIconSize:{type:Number,default:24},rootIndent:Number,indent:{type:Number,default:32},labelField:{type:String,default:"label"},keyField:{type:String,default:"key"},childrenField:{type:String,default:"children"},disabledField:{type:String,default:"disabled"},defaultExpandAll:Boolean,defaultExpandedKeys:Array,expandedKeys:Array,value:[String,Number],defaultValue:{type:[String,Number],default:null},mode:{type:String,default:"vertical"},watchProps:{type:Array,default:void 0},disabled:Boolean,show:{type:Boolean,default:!0},inverted:Boolean,"onUpdate:expandedKeys":[Function,Array],onUpdateExpandedKeys:[Function,Array],onUpdateValue:[Function,Array],"onUpdate:value":[Function,Array],expandIcon:Function,renderIcon:Function,renderLabel:Function,renderExtra:Function,dropdownProps:Object,accordion:Boolean,nodeProps:Function,dropdownPlacement:{type:String,default:"bottom"},responsive:Boolean,items:Array,onOpenNamesChange:[Function,Array],onSelect:[Function,Array],onExpandedNamesChange:[Function,Array],expandedNames:Array,defaultExpandedNames:Array}),Ft=M({name:"Menu",inheritAttrs:!1,props:Ht,setup(e){const{mergedClsPrefixRef:o,inlineThemeDisabled:t}=ve(e),r=te("Menu","-menu",Nt,_o,e,o),i=V(Je,null),n=f(()=>{var g;const{collapsed:y}=e;if(y!==void 0)return y;if(i){const{collapseModeRef:a,collapsedRef:x}=i;if(a.value==="width")return(g=x.value)!==null&&g!==void 0?g:!1}return!1}),c=f(()=>{const{keyField:g,childrenField:y,disabledField:a}=e;return ye(e.items||e.options,{getIgnored(x){return _e(x)},getChildren(x){return x[y]},getDisabled(x){return x[a]},getKey(x){var H;return(H=x[g])!==null&&H!==void 0?H:x.name}})}),u=f(()=>new Set(c.value.treeNodes.map(g=>g.key))),{watchProps:s}=e,b=L(null);s!=null&&s.includes("defaultValue")?Be(()=>{b.value=e.defaultValue}):b.value=e.defaultValue;const w=Y(e,"value"),R=xe(w,b),m=L([]),T=()=>{m.value=e.defaultExpandAll?c.value.getNonLeafKeys():e.defaultExpandedNames||e.defaultExpandedKeys||c.value.getPath(R.value,{includeSelf:!1}).keyPath};s!=null&&s.includes("defaultExpandedKeys")?Be(T):T();const O=et(e,["expandedNames","expandedKeys"]),K=xe(O,m),S=f(()=>c.value.treeNodes),F=f(()=>c.value.getPath(R.value).keyPath);J(he,{props:e,mergedCollapsedRef:n,mergedThemeRef:r,mergedValueRef:R,mergedExpandedKeysRef:K,activePathRef:F,mergedClsPrefixRef:o,isHorizontalRef:f(()=>e.mode==="horizontal"),invertedRef:Y(e,"inverted"),doSelect:B,toggleExpand:D});function B(g,y){const{"onUpdate:value":a,onUpdateValue:x,onSelect:H}=e;x&&G(x,g,y),a&&G(a,g,y),H&&G(H,g,y),b.value=g}function q(g){const{"onUpdate:expandedKeys":y,onUpdateExpandedKeys:a,onExpandedNamesChange:x,onOpenNamesChange:H}=e;y&&G(y,g),a&&G(a,g),x&&G(x,g),H&&G(H,g),m.value=g}function D(g){const y=Array.from(K.value),a=y.findIndex(x=>x===g);if(~a)y.splice(a,1);else{if(e.accordion&&u.value.has(g)){const x=y.findIndex(H=>u.value.has(H));x>-1&&y.splice(x,1)}y.push(g)}q(y)}const $=g=>{const y=c.value.getPath(g??R.value,{includeSelf:!1}).keyPath;if(!y.length)return;const a=Array.from(K.value),x=new Set([...a,...y]);e.accordion&&u.value.forEach(H=>{x.has(H)&&!y.includes(H)&&x.delete(H)}),q(Array.from(x))},P=f(()=>{const{inverted:g}=e,{common:{cubicBezierEaseInOut:y},self:a}=r.value,{borderRadius:x,borderColorHorizontal:H,fontSize:Se,itemHeight:Ie,dividerColor:Re}=a,l={"--n-divider-color":Re,"--n-bezier":y,"--n-font-size":Se,"--n-border-color-horizontal":H,"--n-border-radius":x,"--n-item-height":Ie};return g?(l["--n-group-text-color"]=a.groupTextColorInverted,l["--n-color"]=a.colorInverted,l["--n-item-text-color"]=a.itemTextColorInverted,l["--n-item-text-color-hover"]=a.itemTextColorHoverInverted,l["--n-item-text-color-active"]=a.itemTextColorActiveInverted,l["--n-item-text-color-child-active"]=a.itemTextColorChildActiveInverted,l["--n-item-text-color-child-active-hover"]=a.itemTextColorChildActiveInverted,l["--n-item-text-color-active-hover"]=a.itemTextColorActiveHoverInverted,l["--n-item-icon-color"]=a.itemIconColorInverted,l["--n-item-icon-color-hover"]=a.itemIconColorHoverInverted,l["--n-item-icon-color-active"]=a.itemIconColorActiveInverted,l["--n-item-icon-color-active-hover"]=a.itemIconColorActiveHoverInverted,l["--n-item-icon-color-child-active"]=a.itemIconColorChildActiveInverted,l["--n-item-icon-color-child-active-hover"]=a.itemIconColorChildActiveHoverInverted,l["--n-item-icon-color-collapsed"]=a.itemIconColorCollapsedInverted,l["--n-item-text-color-horizontal"]=a.itemTextColorHorizontalInverted,l["--n-item-text-color-hover-horizontal"]=a.itemTextColorHoverHorizontalInverted,l["--n-item-text-color-active-horizontal"]=a.itemTextColorActiveHorizontalInverted,l["--n-item-text-color-child-active-horizontal"]=a.itemTextColorChildActiveHorizontalInverted,l["--n-item-text-color-child-active-hover-horizontal"]=a.itemTextColorChildActiveHoverHorizontalInverted,l["--n-item-text-color-active-hover-horizontal"]=a.itemTextColorActiveHoverHorizontalInverted,l["--n-item-icon-color-horizontal"]=a.itemIconColorHorizontalInverted,l["--n-item-icon-color-hover-horizontal"]=a.itemIconColorHoverHorizontalInverted,l["--n-item-icon-color-active-horizontal"]=a.itemIconColorActiveHorizontalInverted,l["--n-item-icon-color-active-hover-horizontal"]=a.itemIconColorActiveHoverHorizontalInverted,l["--n-item-icon-color-child-active-horizontal"]=a.itemIconColorChildActiveHorizontalInverted,l["--n-item-icon-color-child-active-hover-horizontal"]=a.itemIconColorChildActiveHoverHorizontalInverted,l["--n-arrow-color"]=a.arrowColorInverted,l["--n-arrow-color-hover"]=a.arrowColorHoverInverted,l["--n-arrow-color-active"]=a.arrowColorActiveInverted,l["--n-arrow-color-active-hover"]=a.arrowColorActiveHoverInverted,l["--n-arrow-color-child-active"]=a.arrowColorChildActiveInverted,l["--n-arrow-color-child-active-hover"]=a.arrowColorChildActiveHoverInverted,l["--n-item-color-hover"]=a.itemColorHoverInverted,l["--n-item-color-active"]=a.itemColorActiveInverted,l["--n-item-color-active-hover"]=a.itemColorActiveHoverInverted,l["--n-item-color-active-collapsed"]=a.itemColorActiveCollapsedInverted):(l["--n-group-text-color"]=a.groupTextColor,l["--n-color"]=a.color,l["--n-item-text-color"]=a.itemTextColor,l["--n-item-text-color-hover"]=a.itemTextColorHover,l["--n-item-text-color-active"]=a.itemTextColorActive,l["--n-item-text-color-child-active"]=a.itemTextColorChildActive,l["--n-item-text-color-child-active-hover"]=a.itemTextColorChildActiveHover,l["--n-item-text-color-active-hover"]=a.itemTextColorActiveHover,l["--n-item-icon-color"]=a.itemIconColor,l["--n-item-icon-color-hover"]=a.itemIconColorHover,l["--n-item-icon-color-active"]=a.itemIconColorActive,l["--n-item-icon-color-active-hover"]=a.itemIconColorActiveHover,l["--n-item-icon-color-child-active"]=a.itemIconColorChildActive,l["--n-item-icon-color-child-active-hover"]=a.itemIconColorChildActiveHover,l["--n-item-icon-color-collapsed"]=a.itemIconColorCollapsed,l["--n-item-text-color-horizontal"]=a.itemTextColorHorizontal,l["--n-item-text-color-hover-horizontal"]=a.itemTextColorHoverHorizontal,l["--n-item-text-color-active-horizontal"]=a.itemTextColorActiveHorizontal,l["--n-item-text-color-child-active-horizontal"]=a.itemTextColorChildActiveHorizontal,l["--n-item-text-color-child-active-hover-horizontal"]=a.itemTextColorChildActiveHoverHorizontal,l["--n-item-text-color-active-hover-horizontal"]=a.itemTextColorActiveHoverHorizontal,l["--n-item-icon-color-horizontal"]=a.itemIconColorHorizontal,l["--n-item-icon-color-hover-horizontal"]=a.itemIconColorHoverHorizontal,l["--n-item-icon-color-active-horizontal"]=a.itemIconColorActiveHorizontal,l["--n-item-icon-color-active-hover-horizontal"]=a.itemIconColorActiveHoverHorizontal,l["--n-item-icon-color-child-active-horizontal"]=a.itemIconColorChildActiveHorizontal,l["--n-item-icon-color-child-active-hover-horizontal"]=a.itemIconColorChildActiveHoverHorizontal,l["--n-arrow-color"]=a.arrowColor,l["--n-arrow-color-hover"]=a.arrowColorHover,l["--n-arrow-color-active"]=a.arrowColorActive,l["--n-arrow-color-active-hover"]=a.arrowColorActiveHover,l["--n-arrow-color-child-active"]=a.arrowColorChildActive,l["--n-arrow-color-child-active-hover"]=a.arrowColorChildActiveHover,l["--n-item-color-hover"]=a.itemColorHover,l["--n-item-color-active"]=a.itemColorActive,l["--n-item-color-active-hover"]=a.itemColorActiveHover,l["--n-item-color-active-collapsed"]=a.itemColorActiveCollapsed),l}),N=t?Ce("menu",f(()=>e.inverted?"a":"b"),P,e):void 0,X=ko(),W=L(null),ee=L(null);let E=!0;const le=()=>{var g;E?E=!1:(g=W.value)===null||g===void 0||g.sync({showAllItemsBeforeCalculate:!0})};function Z(){return document.getElementById(X)}const C=L(-1);function k(g){C.value=e.options.length-g}function A(g){g||(C.value=-1)}const p=f(()=>{const g=C.value;return{children:g===-1?[]:e.options.slice(g)}}),_=f(()=>{const{childrenField:g,disabledField:y,keyField:a}=e;return ye([p.value],{getIgnored(x){return _e(x)},getChildren(x){return x[g]},getDisabled(x){return x[y]},getKey(x){var H;return(H=x[a])!==null&&H!==void 0?H:x.name}})}),j=f(()=>ye([{}]).treeNodes[0]);function ne(){var g;if(C.value===-1)return d(Ae,{root:!0,level:0,key:"__ellpisisGroupPlaceholder__",internalKey:"__ellpisisGroupPlaceholder__",title:"···",tmNode:j.value,domId:X,isEllipsisPlaceholder:!0});const y=_.value.treeNodes[0],a=F.value,x=!!(!((g=y.children)===null||g===void 0)&&g.some(H=>a.includes(H.key)));return d(Ae,{level:0,root:!0,key:"__ellpisisGroup__",internalKey:"__ellpisisGroup__",title:"···",virtualChildActive:x,tmNode:y,domId:X,rawNodes:y.rawNode.children||[],tmNodes:y.children||[],isEllipsisPlaceholder:!0})}return{mergedClsPrefix:o,controlledExpandedKeys:O,uncontrolledExpanededKeys:m,mergedExpandedKeys:K,uncontrolledValue:b,mergedValue:R,activePath:F,tmNodes:S,mergedTheme:r,mergedCollapsed:n,cssVars:t?void 0:P,themeClass:N==null?void 0:N.themeClass,overflowRef:W,counterRef:ee,updateCounter:()=>{},onResize:le,onUpdateOverflow:A,onUpdateCount:k,renderCounter:ne,getCounter:Z,onRender:N==null?void 0:N.onRender,showOption:$,deriveResponsiveState:le}},render(){const{mergedClsPrefix:e,mode:o,themeClass:t,onRender:r}=this;r==null||r();const i=()=>this.tmNodes.map(s=>Me(s,this.$props)),c=o==="horizontal"&&this.responsive,u=()=>d("div",we(this.$attrs,{role:o==="horizontal"?"menubar":"menu",class:[`${e}-menu`,t,`${e}-menu--${o}`,c&&`${e}-menu--responsive`,this.mergedCollapsed&&`${e}-menu--collapsed`],style:this.cssVars}),c?d(tt,{ref:"overflowRef",onUpdateOverflow:this.onUpdateOverflow,getCounter:this.getCounter,onUpdateCount:this.onUpdateCount,updateCounter:this.updateCounter,style:{width:"100%",display:"flex",overflow:"hidden"}},{default:i,counter:this.renderCounter}):i());return c?d(No,{onResize:this.onResize},{default:u}):u()}}),Et={class:"logo card-hover"},Mt={class:"side-foot"},Bt={class:"clock"},jt={class:"title"},Lt={style:{display:"flex","align-items":"center",gap:"12px"}},Dt={key:0,class:"offline-capsule drop-in"},Ut={class:"offline-detail"},Vt=M({__name:"MainLayout",setup(e){const o=Bo(),t=Lo(),{oid:r,triggerReload:i}=Do(),{offline:n,detail:c}=qo(),u=[{label:"人设管理",key:"persona"},{label:"对话历史",key:"history"},{label:"记忆查看",key:"memory"},{label:"心情系统",key:"mood"},{label:"插件管理",key:"plugin"},{label:"系统配置",key:"system"},{label:"对话控制",key:"takeover"}],s=f(()=>o.name||"history"),b=f(()=>o.meta.title||"大肥鱼 管理面板"),w=L("");let R;function m(){w.value=new Date().toLocaleTimeString("zh-CN",{hour12:!1})}Ao(()=>{m(),R=window.setInterval(m,1e3)}),To(()=>{R&&window.clearInterval(R)});function T(K){t.push({name:K})}function O(){localStorage.removeItem("access_token"),t.push({name:"login"})}return(K,S)=>{const F=jo("router-view");return Pe(),je(U(De),{"has-sider":"",style:{height:"100vh"}},{default:ie(()=>[re(U(Pt),{width:216,"content-style":"display:flex;flex-direction:column;height:100%",class:"side"},{default:ie(()=>[Q("div",Et,[Q("span",{class:Oo(["dot",{"dot-off":U(n),"pulse-dot":!U(n)}])},null,2),S[1]||(S[1]=Q("span",{class:"logo-text"},[Le("大肥鱼 "),Q("span",{class:"logo-ver"},"3.0")],-1))]),re(U(Ft),{value:s.value,options:u,indent:18,class:"menu","onUpdate:value":T},null,8,["value"]),Q("div",Mt,[S[2]||(S[2]=Q("span",null,"mychat-v3",-1)),Q("span",Bt,Ne(w.value),1)])]),_:1}),re(U(De),null,{default:ie(()=>[re(U(Wo),{bordered:"",class:"topbar"},{default:ie(()=>[Q("span",jt,Ne(b.value),1),Q("div",Lt,[re(U(ot),{value:U(r),"onUpdate:value":S[0]||(S[0]=B=>$o(r)?r.value=B:null),placeholder:"object_id(共享,回车刷新)",size:"small",style:{width:"240px"},onKeyup:Ko(U(i),["enter"])},null,8,["value","onKeyup"]),re(U(Ho),{size:"small",quaternary:"",onClick:O},{default:ie(()=>[...S[3]||(S[3]=[Le("登出",-1)])]),_:1})])]),_:1}),U(n)?(Pe(),Fo("div",Dt,[S[4]||(S[4]=Q("span",{class:"dot dot-off pulse-dot",style:{width:"8px",height:"8px"}},null,-1)),S[5]||(S[5]=Q("b",null,"大肥鱼 QQ 已掉线,消息正在丢失!",-1)),Q("span",Ut,Ne(U(c))+" —— 打开 NapCat WebUI(6080)扫码重登;二维码刷新失败时重启 napcat-v4 容器",1)])):Eo("",!0),re(U(Yo),{"content-style":"padding:20px","native-scrollbar":!1},{default:ie(()=>[re(F,null,{default:ie(({Component:B})=>[re(Ye,{name:"page",mode:"out-in"},{default:ie(()=>[(Pe(),je(Mo(B),{key:U(o).path}))]),_:2},1024)]),_:1})]),_:1})]),_:1})]),_:1})}}}),nn=nt(Vt,[["__scopeId","data-v-44b9e105"]]);export{nn as default};
