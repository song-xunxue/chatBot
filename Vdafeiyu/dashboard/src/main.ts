/**
 * M7 Vue 面板入口
 * 日期: 2026-06-24
 *
 * 2026-09-16 暗色重设计:引入全局主题变量与微交互动画样式(docs/05 计划书阶段1)。
 */
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import './styles/theme.css'
import './styles/tokens.css'
import './styles/animation.css'

createApp(App).use(router).mount('#app')
