<script setup lang="ts">
/**
 * 移动端代人代答(功能对等 PC Takeover.vue,窄屏重排):
 * ① 待答队列置顶(最高频,textarea 全宽 + block 代答按钮 + 跳过,批量次要入口)
 * ② 代答模式开关 ③ 主动发送 ④ 代答语音(TTS)折叠置底
 * 逻辑与 PC 端完全一致(useObject 共享 oid + 5s 轮询 + visibilitychange 暂停),
 * 仅 template 按手机窄屏重组:删写死宽度→全宽、按钮 size large(touch≥44px)、单行输入改 textarea。
 * 鉴权:无 token 时 router 守卫跳登录页(输 token 存 localStorage),axios 拦截器自动注入 X-Access-Token。
 * 作者: 李文煜
 */
import { ref, reactive, onMounted, onUnmounted, watch } from 'vue'
import {
  NSpace, NInput, NButton, NSwitch, NTag, NPopconfirm, NEmpty, NCard, NCollapse, NCollapseItem, useMessage,
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
  <n-space vertical size="medium">
    <!-- 顶栏:标题 + 刷新(本页持有,不放 MobileLayout) -->
    <div class="m-topbar">
      <span class="m-title">代人代答</span>
      <n-button size="small" quaternary @click="load">刷新</n-button>
    </div>

    <!-- ① 待答队列(置顶,最高频) -->
    <n-card>
      <template #header>
        <span>待答队列</span>
        <n-tag size="small" style="margin-left:8px">{{ queueLength }} 条</n-tag>
        <n-popconfirm @positive-click="clearQueue">
          <template #trigger>
            <n-button size="small" type="warning" ghost style="margin-left:8px" :disabled="!queueLength">清空</n-button>
          </template>
          清空全部待答消息?用户消息会先逐条归档到聊天历史(不丢失),仅放弃代答。
        </n-popconfirm>
      </template>
      <div v-if="queue.length" class="m-hint" style="margin-bottom:8px">
        用角色 QQ 号(手机端)手动回复会自动消化队列:消息进历史(标「手动」)+ 正样本反哺人设
      </div>
      <n-empty v-if="!queue.length" size="small" description="暂无待答消息" />
      <n-space v-else vertical size="medium">
        <div v-for="p in queue" :key="p.pid" class="m-pending-card">
          <div class="m-meta">
            <span class="m-ts">{{ fmtTs(p.created_ts) }}</span>
            <n-tag v-if="p.msg_id" size="tiny" type="info">可被动回复</n-tag>
          </div>
          <div class="m-user-text">{{ p.user_text }}</div>
          <n-input
            v-model:value="answers[p.pid]"
            type="textarea"
            placeholder="输入代答回复..."
            :autosize="{ minRows: 2, maxRows: 6 }"
            @keyup.enter="submitOne(p)"
          />
          <n-space align="center" style="margin-top:8px">
            <n-button type="primary" size="large" style="flex:1" @click="submitOne(p)">代答</n-button>
            <n-popconfirm @positive-click="skip(p)">
              <template #trigger><n-button size="large" quaternary>跳过</n-button></template>
              跳过该条(不代答)?消息会保留进聊天历史。
            </n-popconfirm>
          </n-space>
        </div>
        <n-button size="medium" quaternary block @click="submitBatch">批量提交已填写的代答</n-button>
      </n-space>
    </n-card>

    <!-- ② 代答模式开关 -->
    <n-card title="代答模式">
      <n-space align="center">
        <n-switch size="large" :value="enabled" @update:value="onToggle" />
        <n-tag :type="enabled ? 'warning' : 'default'">
          {{ enabled ? '代答中(LLM 不回复)' : '自动回复(LLM 正常)' }}
        </n-tag>
      </n-space>
    </n-card>

    <!-- ③ 主动发送 -->
    <n-card title="主动发送">
      <n-space vertical size="small">
        <n-input
          v-model:value="proactiveText"
          type="textarea"
          placeholder="输入要主动发给用户的内容..."
          :autosize="{ minRows: 2, maxRows: 6 }"
        />
        <n-button type="primary" size="large" block :disabled="!oid || oid === 'default'" @click="sendProactive">主动发送</n-button>
        <div class="m-hint">不依赖用户先发;落 proxy 消息进历史 + 下发 QQ(主动消息耗月配额)。</div>
        <div v-if="!oid || oid === 'default'" class="m-hint" style="color:#d03050">
          oid 未绑定真实会话(V3.0 须为 QQ 号):先在 QQ 上与角色对话一次即可自动绑定
        </div>
      </n-space>
    </n-card>

    <!-- ④ 代答语音 TTS(折叠置底,低频配置项) -->
    <n-collapse>
      <n-collapse-item title="代答语音(TTS)" name="tts">
        <n-space vertical>
          <n-space align="center">
            <n-switch :value="ttsEnable" @update:value="onTtsEnable" />
            <span class="m-label">{{ ttsEnable ? '代答回复转语音' : '代答回复纯文本' }}</span>
          </n-space>
          <n-space align="center">
            <n-switch :value="ttsSendTextAlso" :disabled="!ttsEnable" @update:value="onTtsSendText" />
            <span class="m-label" style="color:#666">同时发文本(关=只语音;开=先文本后语音)</span>
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
.m-pending-card {
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 10px;
}
.m-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.m-ts {
  font-size: 12px;
  color: #888;
}
.m-user-text {
  background: #f6ffed;
  padding: 6px 10px;
  border-radius: 4px;
  margin-bottom: 8px;
  word-break: break-all;
}
.m-label {
  font-size: 13px;
}
.m-hint {
  font-size: 11px;
  color: #999;
}
</style>
