<script setup lang="ts">
/**
 * 对话历史(V2.0 改造 2026-07-05):左栏改为 block 级会话列表(每段对话一条,
 * 5h 后再聊自动开新 block → 左栏出现新会话条目,符合"会话=一段对话"心智)。
 * 主区显示选中 block 的消息流;每条消息支持「改分」(ai/proxy)/「编辑内容」(软改)/「软删」三种操作并存。
 * 评分总览(健康度/反推/正负样本)针对选中 block 所属 object_id。
 * 作者: 李文煜
 */
import { ref, watch, onMounted, onUnmounted, nextTick, computed } from 'vue'
import { Bar } from 'vue-chartjs'
import { Chart as ChartJS, Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale } from 'chart.js'
import {
  NSpace, NButton, NTag, NPopconfirm, NEmpty, NCard,
  NCollapse, NCollapseItem, NModal, NInput, NInputNumber, useMessage,
} from 'naive-ui'
import {
  listRecentBlocks, listMessages, updateMessage, deleteMessage, closeBlock, deleteBlock, clearHistory,
  getHealth, getSamples, reverseInferDryRun, reverseInferApply, setScore,
} from '@/api'
import { useObject } from '@/composables/useObject'

ChartJS.register(Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale)

const message = useMessage()
const { oid, reloadTick } = useObject()

// —— 左栏:block 级会话列表 ——
const recentBlocks = ref<any[]>([])
const activeBlockId = ref('')
const activeOid = ref('')
const loadingBlocks = ref(false)

// —— 对话流(当前选中 block)——
const currentBlock = ref<any>(null)
const messages = ref<any[]>([])
const streamEl = ref<HTMLElement | null>(null)

// —— 评分总览(针对 activeOid)——
const health = ref<any>(null)
const posSamples = ref<any[]>([])
const negSamples = ref<any[]>([])
const inferDiff = ref<any>(null)
const inferToken = ref('')
const inferring = ref(false)

// —— 内联改分弹窗 ——
const scoreModalShow = ref(false)
const scoreModalMid = ref('')
const scoreModalBase = ref(80)
const scoreModalNote = ref('')

// —— 编辑内容弹窗(软改)——
const editModalShow = ref(false)
const editModalMid = ref('')
const editModalContent = ref('')

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

function fmtTs(ts: any): string {
  const n = Number(ts)
  if (!n) return '—'
  const d = new Date(n); const p = (x: number) => String(x).padStart(2, '0')
  return `${d.getMonth() + 1}/${d.getDate()} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function relTs(ts: any): string {
  const n = Number(ts)
  if (!n) return '—'
  const diff = Date.now() - n
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h`
  return `${Math.floor(diff / 86_400_000)}d`
}
function shortOid(s: string): string { return s ? s.slice(0, 6) : '—' }

// —— 左栏 block 列表 ——
async function loadRecentBlocks() {
  loadingBlocks.value = true
  try {
    recentBlocks.value = await listRecentBlocks(80)
    // 刷新当前 block 元信息(msg_count/status 可能变)
    if (activeBlockId.value) {
      const b = recentBlocks.value.find((x) => x.block_id === activeBlockId.value)
      if (b) currentBlock.value = b
    }
    // 无选中 或 选中已不在列表 → 自动选最近(第一个,通常 status=open 的最近一段)
    if (recentBlocks.value.length && !recentBlocks.value.some((b) => b.block_id === activeBlockId.value)) {
      await selectBlock(recentBlocks.value[0])
    } else if (activeBlockId.value) {
      await loadMessages()   // 刷新当前 block 新消息
    }
  } catch (e: any) { message.error('' + e) }
  finally { loadingBlocks.value = false }
}

async function selectBlock(b: any) {
  activeBlockId.value = b.block_id
  activeOid.value = b.object_id
  oid.value = b.object_id              // 同步全局(Memory/Mood 等页跟随)
  currentBlock.value = b
  messages.value = []
  await loadMessages()
  await loadScore()
}

async function loadMessages() {
  if (!activeOid.value || !activeBlockId.value) return
  try {
    // 记录刷新前是否在底部附近(用户没主动向上滚查看历史)。距底部 < 80px 视为在底部
    const el = streamEl.value
    const wasAtBottom = !el || (el.scrollHeight - el.scrollTop - el.clientHeight) < 80
    messages.value = await listMessages(activeOid.value, { block_id: activeBlockId.value })
    await nextTick()
    // 只在用户原本在底部时跟随滚底(向上滚查看/改上面的内容时,轮询刷新不打断)
    if (wasAtBottom && streamEl.value) streamEl.value.scrollTop = streamEl.value.scrollHeight
  } catch (e: any) { message.error('' + e) }
}

async function loadScore() {
  if (!activeOid.value) return
  try {
    health.value = await getHealth(activeOid.value)
    posSamples.value = await getSamples(activeOid.value, 'positive')
    negSamples.value = await getSamples(activeOid.value, 'negative')
  } catch (e: any) { /* 评分加载失败不阻塞对话流 */ }
}

async function poll() {
  if (typeof document !== 'undefined' && document.hidden) return
  await loadRecentBlocks()
}
function startPoll() { stopPoll(); pollTimer = window.setInterval(poll, POLL_MS) }
function stopPoll() { if (pollTimer !== null) { clearInterval(pollTimer); pollTimer = null } }
function onVis() { document.hidden ? stopPoll() : (poll(), startPoll()) }

async function refreshAll() {
  await loadRecentBlocks()
  if (activeOid.value) await loadScore()
}

// —— 消息操作 ——
async function del(mid: string) {
  try { await deleteMessage(mid); message.success('已软删(若 ai/有分则联动负样本)'); await loadMessages(); await loadScore() }
  catch (e: any) { message.error('' + e) }
}
async function closeBlk(bid: string) {
  try { await closeBlock(bid); message.success('已关闭 block'); await loadRecentBlocks() }
  catch (e: any) { message.error('' + e) }
}

async function delBlock(b: any) {
  try {
    await deleteBlock(b.block_id)
    message.success(`已删除该段(${b.msg_count} 条)`)
    if (activeBlockId.value === b.block_id) {
      activeBlockId.value = ''; currentBlock.value = null; messages.value = []; activeOid.value = ''
    }
    await loadRecentBlocks()
  } catch (e: any) { message.error('' + e) }
}

async function clearAll() {
  if (!activeOid.value) { message.warning('请先选择一个会话段落'); return }
  try {
    const r = await clearHistory(activeOid.value)
    message.success(`已清空全部历史(${r.deleted_blocks} 段, ${r.deleted_msgs} 条)`)
    activeBlockId.value = ''; currentBlock.value = null; messages.value = []; activeOid.value = ''
    await loadRecentBlocks()
  } catch (e: any) { message.error('' + e) }
}

// —— 内联改分 ——
function openScore(mid: string, scoreBase: any, scoreNote: any) {
  scoreModalMid.value = mid
  const b = Number(scoreBase)
  scoreModalBase.value = (!isNaN(b) && scoreBase !== '' && scoreBase !== undefined && scoreBase !== null) ? b : 80
  scoreModalNote.value = scoreNote || ''
  scoreModalShow.value = true
}
async function applyScore() {
  if (!scoreModalMid.value) return
  try {
    const r = await setScore(scoreModalMid.value, scoreModalBase.value, scoreModalNote.value)
    message.success(`已改分:score = ${r.score}`)
    scoreModalShow.value = false; scoreModalMid.value = ''
    await loadMessages(); await loadScore()
  } catch (e: any) { message.error('' + e) }
}

// —— 编辑内容(软改)——
function openEdit(mid: string, content: string) {
  editModalMid.value = mid
  editModalContent.value = content || ''
  editModalShow.value = true
}
async function applyEdit() {
  if (!editModalMid.value) return
  try {
    await updateMessage(editModalMid.value, { content: editModalContent.value })
    message.success('已修改内容')
    editModalShow.value = false; editModalMid.value = ''
    await loadMessages()
  } catch (e: any) { message.error('' + e) }
}

// —— 反推人设 ——
async function dryRun() {
  if (!activeOid.value) return
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
    inferDiff.value = null; inferToken.value = ''
  } catch (e: any) { message.error('' + e) }
}

// 头部 oid 回车:刷新(选中由 block 列表驱动,头部仅触发刷新)
watch(reloadTick, () => refreshAll())

onMounted(async () => {
  await loadRecentBlocks()
  startPoll()
  window.addEventListener('visibilitychange', onVis)
})
onUnmounted(() => { stopPoll(); window.removeEventListener('visibilitychange', onVis) })
</script>

<template>
  <div style="display:flex; height:calc(100vh - 92px)">
    <!-- 左栏:block 级会话列表(每段对话一条) -->
    <div style="width:230px; border-right:1px solid #efeff5; overflow:auto; padding:8px; flex-shrink:0">
      <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px">
        <span style="font-weight:600; font-size:13px">会话(按段落)</span>
        <n-space :size="4">
          <n-popconfirm @positive-click="clearAll">
            <template #trigger>
              <n-button size="tiny" type="error" ghost :disabled="!activeOid">清空全部</n-button>
            </template>
            清空当前用户的全部会话历史?物理删不可恢复。
          </n-popconfirm>
          <n-button size="tiny" quaternary :loading="loadingBlocks" @click="refreshAll">刷新</n-button>
        </n-space>
      </div>
      <n-empty v-if="!recentBlocks.length" size="small" description="暂无会话" />
      <div v-for="b in recentBlocks" :key="b.block_id"
           @click="selectBlock(b)"
           :style="{ padding:'8px 10px', borderRadius:'8px', cursor:'pointer', marginBottom:'4px',
             background: b.block_id === activeBlockId ? '#e8f1ff' : 'transparent' }">
        <div style="display:flex; align-items:center; justify-content:space-between">
          <span style="font-weight:600; font-size:13px">{{ fmtTs(b.start_ts) }}</span>
          <n-tag size="tiny" :type="b.status === 'open' ? 'success' : 'default'">{{ b.status === 'open' ? '进行中' : '已结束' }}</n-tag>
        </div>
        <div style="font-size:11px; color:#999; display:flex; justify-content:space-between; align-items:center; margin-top:2px">
          <span>{{ relTs(b.start_ts) }} · {{ b.msg_count }} 条</span>
          <n-popconfirm @positive-click="delBlock(b)">
            <template #trigger>
              <n-button size="tiny" text type="error" @click.stop>删除</n-button>
            </template>
            删除该段会话({{ b.msg_count }} 条)?物理删不可恢复。
          </n-popconfirm>
        </div>
      </div>
    </div>

    <!-- 主区:评分总览 + 对话流 + 正负样本 -->
    <div style="flex:1; display:flex; flex-direction:column; overflow:hidden; padding-left:16px; min-width:0">
      <!-- 评分总览(针对当前 object_id) -->
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

      <!-- 当前 block 信息条 -->
      <div v-if="currentBlock" style="font-size:12px; color:#888; margin-bottom:6px; flex-shrink:0">
        当前段落:{{ fmtTs(currentBlock.start_ts) }} → {{ fmtTs(currentBlock.end_ts) }} · {{ currentBlock.msg_count }} 条 ·
        <n-tag size="tiny" :type="currentBlock.status === 'open' ? 'success' : 'default'">{{ currentBlock.status }}</n-tag>
        <n-button v-if="currentBlock.status === 'open'" size="tiny" text @click="closeBlk(currentBlock.block_id)">关 block(强制开新段落)</n-button>
      </div>

      <!-- 对话流 -->
      <div v-if="activeBlockId" ref="streamEl" style="flex:1; overflow:auto; padding-right:8px; min-height:0">
        <n-empty v-if="!messages.length" description="该段落暂无消息" />
        <div v-for="m in messages" :key="m.mid"
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
            <div style="word-break:break-all; white-space:pre-wrap">{{ m.content }}</div>
            <div v-if="m.score_note" style="font-size:11px; color:#888; margin-top:2px; font-style:italic">批注:{{ m.score_note }}</div>
            <!-- 操作:改分(仅 ai/proxy)/ 编辑内容(软改,所有)/ 软删(所有) 三者并存 -->
            <n-space v-if="m.status !== 'deleted'" style="margin-top:2px" align="center" :size="4">
              <n-button v-if="m.sender === 'ai' || m.sender === 'proxy'" size="tiny" type="primary" ghost
                        @click="openScore(m.mid, m.score_base, m.score_note)">改分</n-button>
              <n-button size="tiny" type="info" ghost @click="openEdit(m.mid, m.content)">编辑内容</n-button>
              <n-popconfirm @positive-click="del(m.mid)">
                <template #trigger><n-button size="tiny" type="error" ghost>软删</n-button></template>
                软删(→负样本)?
              </n-popconfirm>
            </n-space>
          </div>
        </div>
      </div>
      <n-empty v-else description="左侧选择一个会话段落" style="margin:auto" />

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

    <!-- 内联改分弹窗 -->
    <n-modal v-model:show="scoreModalShow" preset="dialog" title="改分">
      <n-space vertical>
        <span style="font-size:12px; color:#999">覆盖 score_base,保留历史 mood_bias 重算 score</span>
        <n-input-number v-model:value="scoreModalBase" :min="0" :max="100" />
        <span style="font-size:12px; color:#999">批注(说明为什么这个分,可选)</span>
        <n-input v-model:value="scoreModalNote" type="textarea" :rows="2" placeholder="例:语气自然但稍微跑题" />
      </n-space>
      <template #action>
        <n-button @click="scoreModalShow = false">取消</n-button>
        <n-button type="primary" @click="applyScore">确定</n-button>
      </template>
    </n-modal>

    <!-- 编辑内容弹窗(软改) -->
    <n-modal v-model:show="editModalShow" preset="card" title="编辑消息内容" style="width:640px;max-width:92vw">
      <n-space vertical :size="12">
        <n-input v-model:value="editModalContent" type="textarea" :rows="10" autofocus />
        <n-space justify="end">
          <n-button @click="editModalShow = false">取消</n-button>
          <n-button type="primary" @click="applyEdit">确定</n-button>
        </n-space>
      </n-space>
    </n-modal>
  </div>
</template>
