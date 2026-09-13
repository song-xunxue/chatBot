<script setup lang="ts">
/**
 * 对话控制页(2026-09-13 队列删减重构,原「代人代答」):
 * ① AI 静默模式开关(开=AI 不自动回复,全手动;关=自动回复+手动静默期)
 * ② 主动发送(以清浔身份推消息,替代原队列代答) ③ 代答 TTS 两开关。
 * 待答队列卡片/代答输入/批量/跳过/清空已随队列删减移除——手动 QQ 回复由
 * message_sent 感知自动落库+恒正样本+静默窗,无需面板操作。
 * 作者: 李文煜
 */
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { NSpace, NInput, NButton, NSwitch, NTag, NCard, useMessage } from 'naive-ui'
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
    message.success(v ? 'AI 静默已开启(AI 不自动回复,由你 QQ 手动回复或面板发送)' : '已恢复自动回复')
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
    message.success(v ? '代答语音已开启(代答回复转语音)' : '代答语音已关闭(恢复文本代答)')
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
  <n-space vertical size="large">
    <n-space align="center" justify="space-between">
      <span style="font-weight:600">对话控制</span>
      <n-button size="small" @click="load">刷新</n-button>
    </n-space>

    <n-card title="AI 静默模式">
      <n-space vertical size="small">
        <n-space align="center">
          <n-switch :value="enabled" @update:value="onToggle" />
          <n-tag :type="enabled ? 'warning' : 'success'">
            {{ enabled ? '静默中(AI 不自动回复,全手动)' : '自动回复中(AI 正常)' }}
          </n-tag>
        </n-space>
        <span style="font-size:12px;color:#999">
          关(默认)= AI 自动回复;你用清浔 QQ 手动回复后,AI 自动静默 10 分钟(手动聊天不打扰),过后恢复。<br />
          开 = AI 完全不自动回复,由你经 QQ 手动回复或下方「主动发送」触达。
        </span>
      </n-space>
    </n-card>

    <n-card title="主动发送(以清浔身份推消息)">
      <n-space vertical size="small">
        <n-space align="center">
          <n-input v-model:value="proactiveText" placeholder="输入要以清浔身份发给用户的内容..."
                   style="width:520px" @keyup.enter="sendProactive" />
          <n-button type="primary" :disabled="!oid || oid === 'default'" @click="sendProactive">发送</n-button>
        </n-space>
        <span style="font-size:12px;color:#999">落 proxy 消息进历史 + 下发 QQ。静默与否均可使用。</span>
        <div v-if="!oid || oid === 'default'" style="font-size:12px;color:#d03050">
          oid 未绑定真实会话(V3.0 须为 QQ 号):先在 QQ 上与角色对话一次,或头部 oid 框手填用户 QQ 号后回车
        </div>
      </n-space>
    </n-card>

    <!-- 代答 TTS 两开关:逻辑同「插件 → 语音回复」,voice 参数复用之 -->
    <n-card title="发送语音(TTS)">
      <n-space vertical size="small">
        <n-space align="center">
          <n-switch :value="ttsEnable" @update:value="onTtsEnable" />
          <span style="font-size:13px">{{ ttsEnable ? '发送内容转语音' : '发送纯文本' }}</span>
        </n-space>
        <n-space align="center">
          <n-switch :value="ttsSendTextAlso" :disabled="!ttsEnable" @update:value="onTtsSendText" />
          <span style="font-size:13px;color:#666">同时发文本(关=只发语音;开=先文本后语音)</span>
        </n-space>
        <div style="font-size:12px;color:#999">音色/语速等取自「插件 → 语音回复」配置(同一 bot 音色)。语音发送失败自动降级文本。</div>
      </n-space>
    </n-card>
  </n-space>
</template>
