<script setup lang="ts">
/**
 * 对话历史(V2.0 改造 2026-07-03):IM 风格 = 左侧会话列表(自动列最近活跃,无需手填 openid)+
 * 主区对话流(进页面自动加载 + 5s 轮询刷新)+ 每条 ai/proxy 消息内联改分 +
 * 评分总览(健康度/反推/正负样本,合并自原 Score.vue,Score tab 已删)。
 * 选中会话 → 同步 useObject.oid(Memory/Mood 等页跟随,顺带修同类 oid bug)。
 * 作者: 李文煜
 */
import { ref, watch, onMounted, onUnmounted, nextTick, computed } from 'vue'
import { Bar } from 'vue-chartjs'
import { Chart as ChartJS, Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale } from 'chart.js'
import {
  NSpace, NButton, NInputNumber, NTag, NPopconfirm, NEmpty, NCard,
  NCollapse, NCollapseItem, NModal, useMessage,
} from 'naive-ui'
import {
  listSessions, listBlocks, listMessages, deleteMessage, closeBlock,
  getHealth, getSamples, reverseInferDryRun, reverseInferApply, setScore,
} from '@/api'
import { useObject } from '@/composables/useObject'

ChartJS.register(Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale)

const message = useMessage()
const { oid, reloadTick } = useObject()

// —— 会话列表(左栏)——
const sessions = ref<any[]>([])
const activeOid = ref('')                       // 当前选中会话(本地,同步到全局 oid)
const loadingSessions = ref(false)

// —— 对话流(主区)——
const blocks = ref<any[]>([])                   // 当前会话 blocks(每个含 _messages)
const streamEl = ref<HTMLElement | null>(null)  // 对话流滚动容器(新消息自动滚底)

// —— 评分总览(合并自 Score.vue)——
const health = ref<any>(null)
const posSamples = ref<any[]>([])
const negSamples = ref<any[]>([])
const inferDiff = ref<any>(null)
const inferToken = ref('')
const inferring = ref(false)

// —— 内联改分(单例 NModal 服务所有消息)——
const scoreModalShow = ref(false)
const scoreModalMid = ref('')
const scoreModalBase = ref(80)

const POLL_MS = 5000
let pollTimer: number | null = null

const chartData = computed(() => ({
  labels: ['正样本', '中性', '负样本'],
  datasets: [{
    label: '计数',
    backgroundColor: ['#18a058', '#909399', '#d03050'],
    data: [health.value?.positive || 0, health.value?.neutral || 0, health.value?.negative || 0],
  }],
}))
const chartOptions = { responsive: true, plugins: { legend: { display: false } } }

// —— 时间格式化 ——
function fmtTs(ts: any): string {
  const n = Number(ts)
  if (!n) return '—'
  const d = new Date(n); const p = (x: number) => String(x).padStart(2, '0')
  return `${d.getMonth() + 1}/${d.getDate()} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function relTs(ts: any): string {
  // 相对时间:刚刚 / Xm / Xh / Xd(左侧会话列表活跃度展示)
  const n = Number(ts)
  if (!n) return '—'
  const diff = Date.now() - n
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h`
  return `${Math.floor(diff / 86_400_000)}d`
}
function shortOid(s: string): string { return s ? s.slice(0, 8) : '—' }

// —— 会话列表 ——
async function loadSessions() {
  loadingSessions.value = true
  try {
    sessions.value = await listSessions(50)
    // 无选中 或 选中已不在列表 → 自动选最近活跃(第一个)
    if (sessions.value.length && !sessions.value.some(s => s.object_id === activeOid.value)) {
      await selectSession(sessions.value[0].object_id)
    }
  } catch (e: any) { message.error('会话列表加载失败: ' + e) }
  finally { loadingSessions.value = false }
}

async function selectSession(objectId: string) {
  if (activeOid.value !== objectId) {
    activeOid.value = objectId
    oid.value = objectId              // 同步全局(Memory/Mood 等页跟随)
    blocks.value = []
  }
  await loadHistory()
  await loadScore()
}

// —— 对话流(当前选中会话)——
async function loadHistory() {
  if (!activeOid.value) return
  try {
    const bs: any[] = await listBlocks(activeOid.value)
    for (const b of bs) {
      b._messages = await listMessages(activeOid.value, { block_id: b.block_id })
    }
    blocks.value = bs.slice().reverse()   // 正序(旧在前、新 block 在底部),新消息出现在底部可见(修历史不更新)
    await nextTick()
    if (streamEl.value) streamEl.value.scrollTop = streamEl.value.scrollHeight  // 新消息滚底
  } catch (e: any) { message.error('' + e) }
}

// —— 评分总览 ——
async function loadScore() {
  if (!activeOid.value) return
  try {
    health.value = await getHealth(activeOid.value)
    posSamples.value = await getSamples(activeOid.value, 'positive')
    negSamples.value = await getSamples(activeOid.value, 'negative')
  } catch (e: any) { /* 评分加载失败不阻塞对话流 */ }
}

// —— 轮询:刷新会话列表 + 当前会话历史(评分不每轮刷,selectSession/refreshAll/改分时刷)——
async function poll() {
  if (typeof document !== 'undefined' && document.hidden) return
  await loadSessions()
  if (activeOid.value) await loadHistory()
}
function startPoll() { stopPoll(); pollTimer = window.setInterval(poll, POLL_MS) }
function stopPoll() { if (pollTimer !== null) { clearInterval(pollTimer); pollTimer = null } }
function onVis() { document.hidden ? stopPoll() : (poll(), startPoll()) }

async function refreshAll() {
  await loadSessions()
  if (activeOid.value) { await loadHistory(); await loadScore() }
}

// —— 消息操作 ——
async function del(mid: string) {
  try { await deleteMessage(mid); message.success('已软删(若 ai/有分则联动负样本)'); await loadHistory(); await loadScore() }
  catch (e: any) { message.error('' + e) }
}
async function closeBlk(bid: string) {
  try { await closeBlock(bid); message.success('已关闭 block'); await loadHistory() }
  catch (e: any) { message.error('' + e) }
}

// —— 内联改分(每条 ai/proxy 消息)——
function openScore(mid: string, scoreBase: any) {
  scoreModalMid.value = mid
  const b = Number(scoreBase)
  scoreModalBase.value = (!isNaN(b) && scoreBase !== '' && scoreBase !== undefined && scoreBase !== null) ? b : 80
  scoreModalShow.value = true
}
async function applyScore() {
  if (!scoreModalMid.value) return
  try {
    const r = await setScore(scoreModalMid.value, scoreModalBase.value)
    message.success(`已改分:score = ${r.score}`)
    scoreModalShow.value = false
    scoreModalMid.value = ''
    await loadHistory()
    await loadScore()
  } catch (e: any) { message.error('' + e) }
}

// —— 反推人设(移自 Score.vue)——
async function dryRun() {
  inferring.value = true
  try {
    const r = await reverseInferDryRun(activeOid.value, { mode: 'fill_empty' })
    inferDiff.value = r.diff
    inferToken.value = r.confirm_token
    message.success(`反推预览完成(正 ${r.positive_count} / 负 ${r.negative_count})`)
  } catch (e: any) { message.error('' + e) }
  finally { inferring.value = false }
}
async function applyInfer() {
  try {
    await reverseInferApply(activeOid.value, inferToken.value)
    message.success('反推已落库')
    inferDiff.value = null
    inferToken.value = ''
  } catch (e: any) { message.error('' + e) }
}

// 头部 oid 回车(顶栏手输特殊 openid):切换或刷新
watch(reloadTick, () => {
  if (oid.value && oid.value !== 'default' && oid.value !== activeOid.value) selectSession(oid.value)
  else refreshAll()
})

onMounted(async () => {
  // 全局已有有效 oid(从其他页带来)→ 优先;否则 loadSessions 自动选最近活跃
  if (oid.value && oid.value !== 'default') activeOid.value = oid.value
  await loadSessions()
  if (activeOid.value) { await loadHistory(); await loadScore() }
  startPoll()
  window.addEventListener('visibilitychange', onVis)
})
onUnmounted(() => { stopPoll(); window.removeEventListener('visibilitychange', onVis) })
</script>

<template>
  <div style="display:flex; height:calc(100vh - 92px)">
    <!-- 左侧会话列表 -->
    <div style="width:220px; border-right:1px solid #efeff5; overflow:auto; padding:8px; flex-shrink:0">
      <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px">
        <span style="font-weight:600; font-size:13px">会话</span>
        <n-button size="tiny" quaternary :loading="loadingSessions" @click="refreshAll">刷新</n-button>
      </div>
      <n-empty v-if="!sessions.length" size="small" description="暂无会话" />
      <div v-for="s in sessions" :key="s.object_id"
           @click="selectSession(s.object_id)"
           :style="{ padding:'8px 10px', borderRadius:'8px', cursor:'pointer', marginBottom:'4px',
             background: s.object_id === activeOid ? '#e8f1ff' : 'transparent' }">
        <div style="font-weight:600; font-size:13px">{{ shortOid(s.object_id) }}</div>
        <div style="font-size:11px; color:#999; display:flex; justify-content:space-between">
          <span>{{ relTs(s.last_ts) }}</span><span>{{ s.block_count }} 块</span>
        </div>
      </div>
    </div>

    <!-- 主区:评分总览 + 对话流 + 正负样本 -->
    <div style="flex:1; display:flex; flex-direction:column; overflow:hidden; padding-left:16px; min-width:0">
      <!-- 评分总览(合并自 Score.vue) -->
      <n-card v-if="activeOid" size="small" style="margin-bottom:12px; flex-shrink:0">
        <template #header>
          <n-space align="center">
            <span>评分总览</span>
            <n-tag v-if="health" size="small"
                   :type="(health.avg_score || 0) >= 70 ? 'success' : ((health.avg_score || 0) >= 50 ? 'warning' : 'error')">
              均分 {{ health?.avg_score ?? '—' }} / {{ health?.count ?? 0 }} 条
            </n-tag>
          </n-space>
        </template>
        <n-space align="center" :wrap="false">
          <div v-if="health && health.count > 0" style="width:220px"><Bar :data="chartData" :options="chartOptions" /></div>
          <n-space vertical>
            <n-space align="center">
              <n-button size="small" type="primary" :loading="inferring" @click="dryRun">反推人设</n-button>
              <n-popconfirm v-if="inferToken" @positive-click="applyInfer">
                <template #trigger><n-button size="small" type="warning">确认落库</n-button></template>
                确认应用反推 diff 到人设?
              </n-popconfirm>
              <span v-if="health && (health.avg_score || 0) < 60 && health.count > 0" style="color:#d03050; font-size:12px">
                ⚠ 人设可能跑偏
              </span>
            </n-space>
            <details v-if="inferDiff">
              <summary style="cursor:pointer; font-size:12px; color:#666">反推 diff 预览</summary>
              <pre style="background:#f5f5f5; padding:8px; max-height:160px; overflow:auto; font-size:11px; margin:4px 0">{{ JSON.stringify(inferDiff, null, 2) }}</pre>
            </details>
          </n-space>
        </n-space>
      </n-card>

      <!-- 对话流 -->
      <div v-if="activeOid" ref="streamEl" style="flex:1; overflow:auto; padding-right:8px; min-height:0">
        <n-empty v-if="!blocks.length" description="该会话暂无消息" />
        <div v-for="b in blocks" :key="b.block_id">
          <!-- block 时间分隔线 -->
          <div style="text-align:center; margin:12px 0 6px; font-size:11px; color:#bbb">
            — {{ fmtTs(b.start_ts) }} → {{ fmtTs(b.end_ts) }} · {{ b.msg_count }} 条 ·
            <n-tag size="tiny" :type="b.status === 'open' ? 'success' : 'default'">{{ b.status }}</n-tag>
            <n-button v-if="b.status === 'open'" size="tiny" text @click="closeBlk(b.block_id)">关 block</n-button>
          </div>
          <!-- 消息气泡 -->
          <div v-for="m in (b._messages || [])" :key="m.mid"
               :style="{ display:'flex', justifyContent: m.sender === 'user' ? 'flex-end' : 'flex-start', margin:'4px 0' }">
            <div :style="{ maxWidth:'72%', padding:'6px 10px', borderRadius:'10px',
              background: m.sender === 'user' ? '#DCF8C6' : (m.sender === 'system' ? '#f0f0f0' : '#E8F1FF'), color:'#222' }">
              <div style="font-size:11px; color:#888; display:flex; align-items:center; gap:6px">
                <span>{{ m.sender }} · {{ fmtTs(m.ts) }}</span>
                <n-tag v-if="m.score !== '' && m.score !== undefined && m.score !== null" size="tiny"
                       :type="Number(m.score) >= 85 ? 'success' : (Number(m.score) < 60 ? 'error' : 'default')">
                  分 {{ m.score }}
                </n-tag>
                <n-tag v-if="m.status && m.status !== 'active'" size="tiny">{{ m.status }}</n-tag>
              </div>
              <div style="word-break:break-all">{{ m.content }}</div>
              <!-- 操作:ai/proxy 可改分(代答 proxy 同样支持);所有可软删 -->
              <n-space v-if="m.status !== 'deleted'" style="margin-top:2px" align="center" :size="4">
                <n-button v-if="m.sender === 'ai' || m.sender === 'proxy'" size="tiny" type="primary" ghost
                          @click="openScore(m.mid, m.score_base)">改分</n-button>
                <n-popconfirm @positive-click="del(m.mid)">
                  <template #trigger><n-button size="tiny" type="error" ghost>软删</n-button></template>
                  软删(→负样本)?
                </n-popconfirm>
              </n-space>
            </div>
          </div>
        </div>
      </div>
      <n-empty v-else description="左侧选择一个会话" style="margin:auto" />

      <!-- 正负样本(折叠) -->
      <n-collapse v-if="activeOid" style="margin-top:8px; flex-shrink:0" :default-expanded-names="[]">
        <n-collapse-item title="正反样例" name="samples">
          <n-space vertical size="small">
            <div>
              <n-tag type="success" size="small">正样本({{ posSamples.length }})</n-tag>
              <div v-for="s in posSamples" :key="s.mid"
                   style="margin:2px 0; padding:3px 8px; background:#f6ffed; border-radius:4px; font-size:12px">
                [{{ s.score }}] {{ s.text }}
              </div>
            </div>
            <div>
              <n-tag type="error" size="small">负样本({{ negSamples.length }})</n-tag>
              <div v-for="s in negSamples" :key="s.mid"
                   style="margin:2px 0; padding:3px 8px; background:#fff2f0; border-radius:4px; font-size:12px">
                [{{ s.score }}] {{ s.text }}
              </div>
            </div>
          </n-space>
        </n-collapse-item>
      </n-collapse>
    </div>

    <!-- 内联改分弹窗(单例,服务所有 ai/proxy 消息) -->
    <n-modal v-model:show="scoreModalShow" preset="dialog" title="改分">
      <n-space vertical>
        <span style="font-size:12px; color:#999">覆盖 score_base,保留历史 mood_bias 重算 score</span>
        <n-input-number v-model:value="scoreModalBase" :min="0" :max="100" />
      </n-space>
      <template #action>
        <n-button @click="scoreModalShow = false">取消</n-button>
        <n-button type="primary" @click="applyScore">确定</n-button>
      </template>
    </n-modal>
  </div>
</template>
