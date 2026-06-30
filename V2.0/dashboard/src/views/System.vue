<script setup lang="ts">
/**
 * 系统配置页(M7):LLM provider 配置状态(只读)+ 重载配置按钮。
 * V2.0 模型走 .env(不做运行时切换);改 .env 后点重载,新配置 in-place 生效,不重启进程。
 * 作者: 李文煜
 */
import { ref, onMounted } from 'vue'
import { NCard, NSpace, NButton, NTag, NSpin, NEmpty, useMessage } from 'naive-ui'
import { getSystemConfig, reloadSystem } from '@/api'

const message = useMessage()
const config = ref<any>(null)
const loading = ref(false)
const reloading = ref(false)

async function load() {
  loading.value = true
  try { config.value = await getSystemConfig() }
  catch (e: any) { message.error('' + e) }
  finally { loading.value = false }
}

async function reload() {
  reloading.value = true
  try {
    const r = await reloadSystem()
    message.success(`配置已重载,可用 provider: ${r.providers.join(', ') || '无'}`)
    await load()
  } catch (e: any) { message.error('' + e) }
  finally { reloading.value = false }
}

onMounted(load)
</script>

<template>
  <n-space vertical size="large">
    <n-space align="center">
      <n-button type="primary" :loading="reloading" @click="reload">重载配置</n-button>
      <span style="color:#999;font-size:12px">改服务器 .env 后点击,新配置即时生效(不重启进程、不断连)</span>
    </n-space>
    <n-spin :show="loading">
      <n-card title="LLM Provider 配置状态">
        <n-empty v-if="!config" description="加载中..." />
        <n-space v-else vertical size="large">
          <div v-for="p in config.providers" :key="p.name"
               style="display:flex;align-items:center;gap:12px">
            <n-tag :type="p.available ? 'success' : 'default'" size="large">{{ p.name }}</n-tag>
            <n-tag :type="p.configured ? 'success' : 'warning'" size="small">
              {{ p.configured ? '已配置 key' : '未配置 key' }}
            </n-tag>
            <n-tag :type="p.available ? 'success' : 'error'" size="small">
              {{ p.available ? '可用' : '不可用' }}
            </n-tag>
          </div>
          <span style="color:#999;font-size:12px">共 {{ config.available.length }} 个 provider 可用(评分/反推/记忆编码会自动选用)</span>
        </n-space>
      </n-card>
    </n-spin>
  </n-space>
</template>
