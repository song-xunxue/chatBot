<script setup lang="ts">
/**
 * 移动端对话控制页(2026-09-13 队列删减重构,功能对等 PC Takeover.vue):
 * ① AI 静默开关 ② 主动发送(全宽 textarea+大按钮) ③ 发送语音 TTS 两开关(折叠)。
 * 队列卡片已删——手动 QQ 回复自动落库+静默窗,无需面板操作。
 * 作者: 李文煜
 */
import { ref, onMounted, onUnmounted, watch } from 'vue'
import {
  NSpace, NInput, NButton, NSwitch, NTag, NCard, NCollapse, NCollapseItem, useMessage,
} from 'naive-ui'
import {
  getTakeoverStatus, toggleTakeover, sendTakeover,
  getTakeoverTTSConfig, setTakeoverTTSConfig,
} from '@/api'
import { useObject } from '@/composables/useObject'

const message = useMessage()
const { oid, reloadTick, ensureOid } = useObject()
watch(reloadTick, () => load())

const enabled = ref(false)
const proactiveText = ref('')
const ttsEnable = ref(false)
const ttsSendTextAlso = ref(false)

async function load() {
  if (!oid.value || oid.value === 'default') return
  try {
    const s = await getTakeoverStatus(oid.value)
    enabled.value = s.enabled
    const tc = await getTakeoverTTSConfig(oid.value)
    ttsEnable.value = tc.enable
    ttsSendTextAlso.value = tc.send_text_also
  } catch (e: any) { message.error('' + e) }
}

async function onToggle(v: boolean) {
  try {
    await toggleTakeover(oid.value, v)
    enabled.value = v
    message.success(v ? 'AI 静默已开启(全手动)' : '已恢复自动回复')
    await load()
  } catch (e: any) { message.error('' + e); enabled.value = !v }
}

async function sendProactive() {
  const t = proactiveText.value.trim()
  if (!t) { message.warning('请输入要发送的内容'); return }
  try {
    const r = await sendTakeover(oid.value, t)
    message.success(`已发送(下发:${r.delivered ? r.mode : '失败'})`)
    proactiveText.value = ''
  } catch (e: any) { message.error('' + e) }
}

async function onTtsEnable(v: boolean) {
  try {
    await setTakeoverTTSConfig(oid.value, v, ttsSendTextAlso.value)
    ttsEnable.value = v
  } catch (e: any) { message.error('' + e); ttsEnable.value = !v }
}
async function onTtsSendText(v: boolean) {
  try {
    await setTakeoverTTSConfig(oid.value, ttsEnable.value, v)
    ttsSendTextAlso.value = v
  } catch (e: any) { message.error('' + e); ttsSendTextAlso.value = !v }
}

onMounted(async () => {
  await ensureOid()
  await load()
})
onUnmounted(() => {})
</script>

<template>
  <n-space vertical size="medium">
    <div class="m-topbar">
      <span class="m-title">对话控制</span>
      <n-button size="small" quaternary @click="load">刷新</n-button>
    </div>

    <n-card title="AI 静默模式">
      <n-space vertical size="small">
        <n-space align="center">
          <n-switch size="large" :value="enabled" @update:value="onToggle" />
          <n-tag :type="enabled ? 'warning' : 'success'">
            {{ enabled ? '静默中(全手动)' : '自动回复中' }}
          </n-tag>
        </n-space>
        <div class="m-hint">
          关(默认)=AI 自动回复,你手动 QQ 回复后 AI 自动静默 10 分钟;开=AI 完全不自动回复
        </div>
      </n-space>
    </n-card>

    <n-card title="主动发送">
      <n-space vertical size="small">
        <n-input
          v-model:value="proactiveText"
          type="textarea"
          placeholder="以清浔身份发给用户的内容..."
          :autosize="{ minRows: 2, maxRows: 6 }"
        />
        <n-button type="primary" size="large" block :disabled="!oid || oid === 'default'" @click="sendProactive">发送</n-button>
        <div v-if="!oid || oid === 'default'" class="m-hint" style="color:#d03050">
          oid 未绑定真实会话:先在 QQ 上与角色对话一次即可自动绑定
        </div>
      </n-space>
    </n-card>

    <n-collapse>
      <n-collapse-item title="发送语音(TTS)" name="tts">
        <n-space vertical>
          <n-space align="center">
            <n-switch :value="ttsEnable" @update:value="onTtsEnable" />
            <span class="m-label">{{ ttsEnable ? '发送内容转语音' : '发送纯文本' }}</span>
          </n-space>
          <n-space align="center">
            <n-switch :value="ttsSendTextAlso" :disabled="!ttsEnable" @update:value="onTtsSendText" />
            <span class="m-label" style="color:#666">同时发文本(关=只发语音;开=先文本后语音)</span>
          </n-space>
          <div class="m-hint">音色/语速等取自「插件 → 语音回复」配置。语音失败自动降级文本。</div>
        </n-space>
      </n-collapse-item>
    </n-collapse>
  </n-space>
</template>

<style scoped>
.m-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.m-title {
  font-weight: 600;
  font-size: 16px;
}
.m-label {
  font-size: 13px;
}
.m-hint {
  font-size: 11px;
  color: #999;
}
</style>
