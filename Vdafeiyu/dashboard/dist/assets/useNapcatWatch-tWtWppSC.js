import{ap as P,aq as j,ar as E,as as S,z as p,D as y,E as g,d as B,s as f,a0 as N,t as I,v as C,a1 as _,J as T,y as m,r as v,M as H,a9 as V,aa as k}from"./index-aEyr6MLK.js";import{a2 as D}from"./index-Dx1FU_Yj.js";function F(t){const{baseColor:e,textColor2:r,bodyColor:l,cardColor:s,dividerColor:o,actionColor:h,scrollbarColor:d,scrollbarColorHover:n,invertedColor:c}=t;return{textColor:r,textColorInverted:"#FFF",color:l,colorEmbedded:h,headerColor:s,headerColorInverted:c,footerColor:h,footerColorInverted:c,headerBorderColor:o,headerBorderColorInverted:c,footerBorderColor:o,footerBorderColorInverted:c,siderBorderColor:o,siderBorderColorInverted:c,siderColor:s,siderColorInverted:c,siderToggleButtonBorder:`1px solid ${o}`,siderToggleButtonColor:e,siderToggleButtonIconColor:r,siderToggleButtonIconColorInverted:r,siderToggleBarColor:S(l,d),siderToggleBarColorHover:S(l,n),__invertScrollbar:"true"}}const R=P({name:"Layout",common:E,peers:{Scrollbar:j},self:F}),Y=p("n-layout-sider"),z={type:String,default:"static"},M=y("layout",`
 color: var(--n-text-color);
 background-color: var(--n-color);
 box-sizing: border-box;
 position: relative;
 z-index: auto;
 flex: auto;
 overflow: hidden;
 transition:
 box-shadow .3s var(--n-bezier),
 background-color .3s var(--n-bezier),
 color .3s var(--n-bezier);
`,[y("layout-scroll-container",`
 overflow-x: hidden;
 box-sizing: border-box;
 height: 100%;
 `),g("absolute-positioned",`
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 `)]),K={embedded:Boolean,position:z,nativeScrollbar:{type:Boolean,default:!0},scrollbarProps:Object,onScroll:Function,contentClass:String,contentStyle:{type:[String,Object],default:""},hasSider:Boolean,siderPlacement:{type:String,default:"left"}},W=p("n-layout");function L(t){return B({name:t?"LayoutContent":"Layout",props:Object.assign(Object.assign({},C.props),K),setup(e){const r=v(null),l=v(null),{mergedClsPrefixRef:s,inlineThemeDisabled:o}=I(e),h=C("Layout","-layout",M,R,e,s);function d(a,i){if(e.nativeScrollbar){const{value:u}=r;u&&(i===void 0?u.scrollTo(a):u.scrollTo(a,i))}else{const{value:u}=l;u&&u.scrollTo(a,i)}}H(W,e);let n=0,c=0;const $=a=>{var i;const u=a.target;n=u.scrollLeft,c=u.scrollTop,(i=e.onScroll)===null||i===void 0||i.call(e,a)};_(()=>{if(e.nativeScrollbar){const a=r.value;a&&(a.scrollTop=c,a.scrollLeft=n)}});const w={display:"flex",flexWrap:"nowrap",width:"100%",flexDirection:"row"},O={scrollTo:d},x=m(()=>{const{common:{cubicBezierEaseInOut:a},self:i}=h.value;return{"--n-bezier":a,"--n-color":e.embedded?i.colorEmbedded:i.color,"--n-text-color":i.textColor}}),b=o?T("layout",m(()=>e.embedded?"e":""),x,e):void 0;return Object.assign({mergedClsPrefix:s,scrollableElRef:r,scrollbarInstRef:l,hasSiderStyle:w,mergedTheme:h,handleNativeElScroll:$,cssVars:o?void 0:x,themeClass:b==null?void 0:b.themeClass,onRender:b==null?void 0:b.onRender},O)},render(){var e;const{mergedClsPrefix:r,hasSider:l}=this;(e=this.onRender)===null||e===void 0||e.call(this);const s=l?this.hasSiderStyle:void 0,o=[this.themeClass,t&&`${r}-layout-content`,`${r}-layout`,`${r}-layout--${this.position}-positioned`];return f("div",{class:o,style:this.cssVars},this.nativeScrollbar?f("div",{ref:"scrollableElRef",class:[`${r}-layout-scroll-container`,this.contentClass],style:[this.contentStyle,s],onScroll:this.handleNativeElScroll},this.$slots):f(N,Object.assign({},this.scrollbarProps,{onScroll:this.onScroll,ref:"scrollbarInstRef",theme:this.mergedTheme.peers.Scrollbar,themeOverrides:this.mergedTheme.peerOverrides.Scrollbar,contentClass:this.contentClass,contentStyle:[this.contentStyle,s]}),this.$slots))}})}const A=L(!1),G=L(!0),q=y("layout-header",`
 transition:
 color .3s var(--n-bezier),
 background-color .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 box-sizing: border-box;
 width: 100%;
 background-color: var(--n-color);
 color: var(--n-text-color);
`,[g("absolute-positioned",`
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 `),g("bordered",`
 border-bottom: solid 1px var(--n-border-color);
 `)]),J={position:z,inverted:Boolean,bordered:{type:Boolean,default:!1}},Q=B({name:"LayoutHeader",props:Object.assign(Object.assign({},C.props),J),setup(t){const{mergedClsPrefixRef:e,inlineThemeDisabled:r}=I(t),l=C("Layout","-layout-header",q,R,t,e),s=m(()=>{const{common:{cubicBezierEaseInOut:h},self:d}=l.value,n={"--n-bezier":h};return t.inverted?(n["--n-color"]=d.headerColorInverted,n["--n-text-color"]=d.textColorInverted,n["--n-border-color"]=d.headerBorderColorInverted):(n["--n-color"]=d.headerColor,n["--n-text-color"]=d.textColor,n["--n-border-color"]=d.headerBorderColor),n}),o=r?T("layout-header",m(()=>t.inverted?"a":"b"),s,t):void 0;return{mergedClsPrefix:e,cssVars:r?void 0:s,themeClass:o==null?void 0:o.themeClass,onRender:o==null?void 0:o.onRender}},render(){var t;const{mergedClsPrefix:e}=this;return(t=this.onRender)===null||t===void 0||t.call(this),f("div",{class:[`${e}-layout-header`,this.themeClass,this.position&&`${e}-layout-header--${this.position}-positioned`,this.bordered&&`${e}-layout-header--bordered`],style:this.cssVars},this.$slots)}});function Z(){const t=v(!1),e=v(""),r=v(0);let l;async function s(){try{const o=await D();t.value=(o==null?void 0:o.state)==="offline",e.value=(o==null?void 0:o.detail)||"",r.value=(o==null?void 0:o.offline_since_ts)||0}catch{}}return V(()=>{s(),l=window.setInterval(s,6e4)}),k(()=>{l&&window.clearInterval(l)}),{offline:t,detail:e,sinceTs:r}}export{A as N,W as a,Y as b,Q as c,G as d,R as l,z as p,Z as u};
