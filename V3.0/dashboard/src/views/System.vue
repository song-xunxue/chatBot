<script setup lang="ts">
/**
 * 系统配置页(M7;2026-08-17 V3.0 精简):LLM provider 配置状态(只读)+ 重载配置 + 清空所有数据。
 * QQ 官方机器人凭证卡已删(V3.0 纯 QQ 号/OneBot 项目,无官方凭证概念)。
 * 清空所有数据:删运行时数据(对话/记忆/训练样本/评分/mood值/代答),保留人设+配置,需输入"清空"确认。
 * 作者: 李文煜
 */
import { ref, onMounted } from 'vue'
import { NCard, NSpace, NButton, NTag, NSpin, NEmpty, NInput, NModal, useMessage } from 'naive-ui'
import { getSystemConfig, reloadSystem, resetAllData } from '@/api'

const message = useMessage()
const config = ref<any>(null)
const loading = ref(false)
const reloading = ref(false)

// 清空所有数据(危险操作)
const resetShow = ref(false)
const resetConfirm = ref('')
const resetting = ref(false)

async function load() {
  loading.value = true
  try {
    config.value = await getSystemConfig()
  } catch (e: any) { message.error('' + e) }
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

function openReset() {
  resetConfirm.value = ''
  resetShow.value = true
}

async function doReset() {
  if (resetConfirm.value !== '清空') { message.warning('请输入"清空"二字确认'); return }
  resetting.value = true
  try {
    const r = await resetAllData()
    message.success(`已清空(删 ${r.deleted} 键,保留 ${r.kept} 键)`)
    resetShow.value = false
  } catch (e: any) { message.error('' + e) }
  finally { resetting.value = false }
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
    <n-card title="危险操作">
      <n-space vertical size="large">
        <span style="color:#999;font-size:12px">
          清空所有运行时数据(对话历史/训练样本/记忆/评分/mood值/代答队列),保留人设 + 心情档位 + 插件开关。<b style="color:#d03050">不可恢复</b>。
        </span>
        <n-button type="error" @click="openReset">清空所有数据</n-button>
      </n-space>
    </n-card>

    <!-- 清空确认弹窗(输入"清空"二次确认) -->
    <n-modal v-model:show="resetShow" preset="card" title="清空所有数据(危险操作)" style="width:480px;max-width:92vw">
      <n-space vertical :size="12">
        <div style="color:#d03050;font-size:13px">
          将清空:对话历史 / 训练样本 / 四级记忆 / 评分样本 / mood值+历史 / 代答队列。保留:人设 / 心情档位 / 插件开关。<b>不可恢复</b>。
        </div>
        <n-input v-model:value="resetConfirm" placeholder='输入"清空"二字确认' autofocus />
        <n-space justify="end">
          <n-button @click="resetShow = false">取消</n-button>
          <n-button type="error" :loading="resetting" :disabled="resetConfirm !== '清空'" @click="doReset">确认清空</n-button>
        </n-space>
      </n-space>
    </n-modal>
  </n-space>
</template>
