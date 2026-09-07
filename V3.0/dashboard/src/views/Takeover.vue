<script setup lang="ts">
/**
 * 代人代答(V2.0 改造 2026-07-05):用全局 oid(对齐真实 QQ openid,解决 per-object 开关不匹配导致
 * LLM 没拦住/看不到 pending/切页丢状态)+ onMounted 自动 load + 5s 轮询 + 主动发送(不需用户先发)。
 * takeover 模式开启时:webhook 拦截 LLM(用户消息入 pending 队列不进 pipeline),
 * 管理员可代答(消费 pending)或主动发(无 pending 直接推)。去 oid 输入框。
 * 作者: 李文煜
 */
import { ref, reactive, onMounted, onUnmounted, watch } from 'vue'
import {
  NSpace, NInput, NButton, NSwitch, NTag, NPopconfirm, NEmpty, NCard, useMessage,
} from 'naive-ui'
import {
  getTakeoverStatus, toggleTakeover, listTakeoverQueue,
  answerTakeover, answerTakeoverBatch, skipTakeover, sendTakeover,
  clearTakeoverQueue, getTakeoverTTSConfig, setTakeoverTTSConfig,
} from '@/api'
import { useObject } from '@/composables/useObject'

const message = useMessage()
const { oid, reloadTick, ensureOid } = useObject()
watch(reloadTick, () => load())

const enabled = ref(false)
const queueLength = ref(0)
const queue = ref<any[]>([])
// 每条 pending 的代答输入(pid -> answer),reactive 支持动态 key v-model
const answers = reactive<Record<string, string>>({})
// 主动发送内容
const proactiveText = ref('')
// 代答 TTS 两开关(M-tts:启用语音 / 启用时是否同发文本)
const ttsEnable = ref(false)
const ttsSendTextAlso = ref(false)

const POLL_MS = 5000
let pollTimer: number | null = null

function fmtTs(ts: any): string {
  const n = Number(ts)
  if (!n) return '—'
  const d = new Date(n); const p = (x: number) => String(x).padStart(2, '0')
  return `${d.getMonth() + 1}/${d.getDate()} ${p(d.getHours())}:${p(d.getMinutes())}`
}

async function load() {
  if (!oid.value || oid.value === 'default') return
  try {
    const s = await getTakeoverStatus(oid.value)
    enabled.value = s.enabled
    queueLength.value = s.queue_length
    const q = await listTakeoverQueue(oid.value)
    queue.value = q.queue || []
    const tc = await getTakeoverTTSConfig(oid.value)
    ttsEnable.value = tc.enable
    ttsSendTextAlso.value = tc.send_text_also
  } catch (e: any) { message.error('' + e) }
}

async function onToggle(v: boolean) {
  try {
    await toggleTakeover(oid.value, v)
    enabled.value = v
    message.success(v ? '代答模式已开启(用户消息入队,LLM 不自动回复)' : '代答模式已关闭(恢复 LLM 自动回复)')
    await load()
  } catch (e: any) { message.error('' + e); enabled.value = !v }
}

async function submitOne(p: any) {
  const ans = (answers[p.pid] || '').trim()
  if (!ans) { message.warning('请输入代答内容'); return }
  try {
    const r = await answerTakeover(oid.value, { pid: p.pid, answer: ans })
    message.success(`已代答(下发:${r.delivered ? r.mode : '失败,可重试'})`)
    answers[p.pid] = ''
    await load()
  } catch (e: any) { message.error('' + e) }
}

async function submitBatch() {
  const items = queue.value
    .map((p) => ({ pid: p.pid, answer: (answers[p.pid] || '').trim() }))
    .filter((it) => it.answer)
  if (!items.length) { message.warning('请至少填写一条代答'); return }
  try {
    const r = await answerTakeoverBatch(oid.value, items)
    message.success(`批量代答完成(${r.success}/${items.length} 成功${r.truncated ? ',超限已截断' : ''})`)
    items.forEach((it) => { answers[it.pid] = '' })
    await load()
  } catch (e: any) { message.error('' + e) }
}

async function skip(p: any) {
  try {
    const r = await skipTakeover(oid.value, p.pid)
    if (r.skipped) message.success(r.archived ? '已跳过(消息已存入历史)' : '已跳过')
    else message.warning('该条已不存在(可能已被手动回复消化)')
    await load()
  } catch (e: any) { message.error('' + e) }
}

async function clearQueue() {
  try {
    const r = await clearTakeoverQueue(oid.value)
    message.success(`已清空待答队列(${r.cleared} 条,${r.archived} 条已归档到历史)`)
    await load()
  } catch (e: any) { message.error('' + e) }
}

async function sendProactive() {
  const t = proactiveText.value.trim()
  if (!t) { message.warning('请输入主动发送的内容'); return }
  try {
    const r = await sendTakeover(oid.value, t)
    message.success(`已主动发送(下发:${r.delivered ? r.mode : '失败'})`)
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

async function poll() {
  if (typeof document !== 'undefined' && document.hidden) return
  await load()
}
function startPoll() { stopPoll(); pollTimer = window.setInterval(poll, POLL_MS) }
function stopPoll() { if (pollTimer !== null) { clearInterval(pollTimer); pollTimer = null } }
function onVis() { document.hidden ? stopPoll() : (poll(), startPoll()) }

onMounted(async () => {
  await ensureOid()
  await load()
  startPoll()
  window.addEventListener('visibilitychange', onVis)
})
onUnmounted(() => { stopPoll(); window.removeEventListener('visibilitychange', onVis) })
</script>

<template>
  <n-space vertical size="large">
    <n-space align="center" justify="space-between">
      <span style="font-weight:600">代人代答</span>
      <n-button size="small" @click="load">刷新</n-button>
    </n-space>

    <n-card title="代答模式">
      <n-space align="center">
        <n-switch :value="enabled" @update:value="onToggle" />
        <n-tag :type="enabled ? 'warning' : 'default'">{{ enabled ? '代答中(LLM 不回复,用户消息入队)' : '自动回复(LLM 正常)' }}</n-tag>
        <n-tag size="small">队列 {{ queueLength }} 条</n-tag>
        <n-popconfirm @positive-click="clearQueue">
          <template #trigger>
            <n-button size="small" type="warning" ghost :disabled="!queueLength">清空队列</n-button>
          </template>
          清空全部待答消息?用户消息会先逐条归档到聊天历史(不丢失),仅放弃代答。
        </n-popconfirm>
      </n-space>
      <div style="font-size:12px;color:#999;margin-top:6px">
        直接用角色 QQ 号(手机端)手动回复用户时,待答队列会自动消化:用户消息+手动回复自动进聊天历史(标「手动」),
        手动回复作为正样本参与人设反推。
      </div>
    </n-card>

    <!-- 代答 TTS 两开关(M-tts):逻辑同「插件 → 语音回复」,voice 参数复用之 -->
    <n-card title="代答语音(TTS)">
      <n-space vertical>
        <n-space align="center">
          <n-switch :value="ttsEnable" @update:value="onTtsEnable" />
          <span style="font-size:13px">{{ ttsEnable ? '代答回复转语音发送' : '代答回复纯文本' }}</span>
        </n-space>
        <n-space align="center">
          <n-switch :value="ttsSendTextAlso" :disabled="!ttsEnable" @update:value="onTtsSendText" />
          <span style="font-size:13px;color:#666">同时发文本(关=只发语音,替换文本;开=先文本后语音)</span>
        </n-space>
        <div style="font-size:12px;color:#999">音色/语速/gain/情感取自「插件 → 语音回复」配置(同一 bot 音色)。语音发送失败自动降级文本。</div>
      </n-space>
    </n-card>

    <!-- 主动发送(不需用户先发) -->
    <n-card title="主动发送(直接推消息给用户)">
      <n-space align="center">
        <n-input v-model:value="proactiveText" placeholder="输入要主动发给用户的内容..." style="width:520px"
                 @keyup.enter="sendProactive" />
        <n-button type="primary" :disabled="!oid || oid === 'default'" @click="sendProactive">主动发送</n-button>
      </n-space>
      <div style="font-size:12px;color:#999;margin-top:6px">
        不依赖用户先发消息;落 proxy 消息进历史 + 下发 QQ(主动消息耗月配额)。代答模式开关与否均可使用。
      </div>
      <div v-if="!oid || oid === 'default'" style="font-size:12px;color:#d03050;margin-top:4px">
        oid 未绑定真实会话(V3.0 须为 QQ 号):先在 QQ 上与角色对话一次,或头部 oid 框手填用户 QQ 号后回车
      </div>
    </n-card>

    <n-empty v-if="!queue.length" description="暂无待答消息(代答模式开启后,用户消息会出现在此)" />
    <n-card v-else title="待答队列(FIFO,队首在前)">
      <n-space vertical>
        <div v-for="p in queue" :key="p.pid" style="border:1px solid #eee;border-radius:6px;padding:10px">
          <div style="font-size:12px;color:#888;margin-bottom:4px">
            {{ fmtTs(p.created_ts) }}
            <n-tag v-if="p.msg_id" size="tiny" type="info">有 msg_id(可被动回复)</n-tag>
          </div>
          <div style="background:#f6ffed;padding:6px 10px;border-radius:4px;margin-bottom:6px;word-break:break-all">
            {{ p.user_text }}
          </div>
          <n-space align="center">
            <n-input v-model:value="answers[p.pid]" placeholder="输入代答回复..." style="width:380px"
                     @keyup.enter="submitOne(p)" />
            <n-button type="primary" size="small" @click="submitOne(p)">代答</n-button>
            <n-popconfirm @positive-click="skip(p)">
              <template #trigger><n-button size="small" quaternary>跳过</n-button></template>
              跳过该条(不代答)?消息会保留进聊天历史。
            </n-popconfirm>
          </n-space>
        </div>
        <n-button type="info" @click="submitBatch">批量提交已填写的代答</n-button>
      </n-space>
    </n-card>
  </n-space>
</template>
