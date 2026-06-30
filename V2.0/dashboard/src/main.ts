/**
 * M7 Vue 面板入口
 * 作者: 李文煜
 * 日期: 2026-06-24
 */
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'

createApp(App).use(router).mount('#app')
