<script setup lang="ts">
/**
 * 插件管理(V2.0 M7,单人设简化 2026-07-05):原生 + .star 统一列表 + 启用/禁用 + 热重载。
 * 单人设下不再有"按对象配置"维度(per-object 卡已删),插件即全局配置,直接显示。
 * 作者: 李文煜
 */
import { ref, onMounted } from 'vue'
import { NCard, NSpace, NButton, NSwitch, NTag, NEmpty, useMessage } from 'naive-ui'
import { listPlugins, enablePlugin, disablePlugin, reloadPlugin, reloadStar } from '@/api'

const message = useMessage()
const plugins = ref<any[]>([])

async function load() { plugins.value = await listPlugins() }
onMounted(load)

async function toggle(p: any) {
  try {
    if (p.enabled) await disablePlugin(p.name)
    else await enablePlugin(p.name)
    message.success('已更新'); await load()
  } catch (e: any) { message.error('' + e) }
}
async function reload(p: any) {
  try {
    if (p.type === 'star') await reloadStar(p.name)
    else await reloadPlugin(p.name)
    message.success('已重载'); await load()
  } catch (e: any) { message.error('重载失败: ' + e) }
}
</script>

<template>
  <n-space vertical size="large">
    <n-space><n-button @click="load">刷新插件</n-button></n-space>
    <n-card title="插件列表(原生 + .star)" size="small">
      <n-empty v-if="!plugins.length" description="无已加载插件" />
      <div v-for="p in plugins" :key="p.name + p.type"
           style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid #f0f0f0">
        <n-tag :type="p.type === 'star' ? 'warning' : 'info'" size="small">{{ p.type }}</n-tag>
        <span style="font-weight:600;min-width:120px">{{ p.display_name || p.name }}</span>
        <span style="color:#999;font-size:12px;flex:1">{{ p.description || '' }}</span>
        <n-switch v-if="p.type === 'native'" :value="!!p.enabled" @update:value="() => toggle(p)" />
        <n-button size="tiny" @click="reload(p)">重载</n-button>
      </div>
    </n-card>
  </n-space>
</template>
