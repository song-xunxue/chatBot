<script setup lang="ts">
/**
 * 对话历史(V2.0 拟人化 2026-07-07):左栏混合 chat 真实 block + roleplay 训练 block(source tag 区分),
 * 主区按 source 切换:real=真实对话流(改分+纠正回复/软删/评分总览/反推)/training=训练样本流(录入/评分/抽取为记忆)。
 * 2026-08-18:删"编辑内容"(破坏性改 content)——纠错统一走改分弹窗纠正回复(原内容保留+正样本反推)。
 * 训练样本并入对话历史页(去独立菜单),一体体验。sender=user 显示 user_alias(角色对用户称呼,拟人化)。
 * 作者: 李文煜
 */
import { ref, watch, onMounted, onUnmounted, nextTick, computed } from 'vue'
import { Bar } from 'vue-chartjs'
import { Chart as ChartJS, Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale } from 'chart.js'
import {
  NSpace, NInput, NButton, NSelect, NTag, NPopconfirm, NEmpty, NCard, NInputNumber,
  NCollapse, NCollapseItem, NModal, useMessage,
} from 'naive-ui'
import {
  listRecentBlocks, listMessages, deleteMessage, closeBlock, deleteBlock, clearHistory,
  getHealth, getSamples, reverseInferDryRun, reverseInferApply, setScore,
  listRoleplay, addRoleplay, setRoleplayScore, deleteRoleplay, extractRoleplay,
  newRoleplaySession, deleteRoleplaySession, listPersonas,
} from '@/api'
import { useObject } from '@/composables/useObject'

ChartJS.register(Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale)

const message = useMessage()
const { oid, reloadTick } = useObject()

// —— 左栏:混合 block 列表(real+training)——
const recentBlocks = ref<any[]>([])
const activeBlockId = ref('')
const activeOid = ref('')
const activeSource = ref<'real' | 'training'>('real')   // 当前 block 来源,决定主区模式
const loadingBlocks = ref(false)
const userAlias = ref('')                                // 角色对用户称呼(拟人化,显示代"user")

// —— 对话流(当前选中 block;real 用 sender 字段,training 用 role 字段)——
const currentBlock = ref<any>(null)
const messages = ref<any[]>([])
const streamEl = ref<HTMLElement | null>(null)

// —— 评分总览(real,针对 activeOid)——
const health = ref<any>(null)
const posSamples = ref<any[]>([])
const negSamples = ref<any[]>([])
const inferDiff = ref<any>(null)
const inferToken = ref('')
const inferring = ref(false)

// —— real 改分弹窗(含 note + 纠正回复/纠正分数)——
const scoreModalShow = ref(false)
const scoreModalMid = ref('')
const scoreModalBase = ref(80)
const scoreModalNote = ref('')
const scoreModalCorrected = ref('')
const scoreModalCorrectedScore = ref(100)

// —— training 录入 ——
const role = ref('user')
const rpContent = ref('')
const rpScoreBase = ref<number | null>(null)
const extracting = ref(false)
const roleOptions = [
  { label: '作为用户说(user)', value: 'user' },
  { label: '作为角色说(assistant)', value: 'assistant' },
  { label: '系统旁白(system)', value: 'system' },
]

// —— training 改分弹窗(简单,无 note)——
const rpScoreShow = ref(false)
const rpScoreMid = ref('')
const rpScoreVal = ref(80)

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
// 消息发送者标签:real user 显示 user_alias(如"煜君");proxy=面板代答/角色QQ手动回复;其余原值
// (training 消息的存储 source 是 'roleplay',原判 'training' 恒不命中,顺手修正)
function senderLabel(m: any): string {
  const s = m.source === 'roleplay' ? m.role : m.sender
  if (s === 'user' && userAlias.value) return userAlias.value
  if (s === 'proxy') return m.source === 'manual' ? '手动' : '代答'
  return s || '—'
}
// 评分样本来源标签(反推权威度:纠/手>真>剧);dialog(真实对话)不打标签保持简洁
function sourceTag(s: any): string {
  if (s.source === 'correction') return '[纠]'
  if (s.source === 'manual') return '[手]'
  if (s.source === 'roleplay') return '[剧]'
  return ''
}

// —— 左栏 block 列表(混合 real+training)——
async function loadRecentBlocks() {
  loadingBlocks.value = true
  try {
    recentBlocks.value = await listRecentBlocks(80)
    if (activeBlockId.value) {
      const b = recentBlocks.value.find((x) => x.block_id === activeBlockId.value)
      if (b) currentBlock.value = b
    }
    if (recentBlocks.value.length && !recentBlocks.value.some((b) => b.block_id === activeBlockId.value)) {
      await selectBlock(recentBlocks.value[0])
    } else if (activeBlockId.value) {
      await loadMessages()
    }
  } catch (e: any) { message.error('' + e) }
  finally { loadingBlocks.value = false }
}

async function selectBlock(b: any) {
  activeBlockId.value = b.block_id
  activeOid.value = b.object_id
  activeSource.value = b.source || 'real'
  oid.value = b.object_id
  currentBlock.value = b
  messages.value = []
  await loadMessages()
  if (activeSource.value === 'real') await loadScore()
}

async function loadMessages() {
  if (!activeOid.value || !activeBlockId.value) return
  try {
    const el = streamEl.value
    const wasAtBottom = !el || (el.scrollHeight - el.scrollTop - el.clientHeight) < 80
    // 按 source 调不同 API:real→listMessages(sender 字段)/training→listRoleplay(role 字段)
    if (activeSource.value === 'training') {
      const r = await listRoleplay(activeOid.value, { block_id: activeBlockId.value })
      messages.value = r.messages || []
    } else {
      messages.value = await listMessages(activeOid.value, { block_id: activeBlockId.value })
    }
    await nextTick()
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
  if (activeOid.value && activeSource.value === 'real') await loadScore()
}

// —— real 消息操作 ——
async function del(mid: string) {
  try { await deleteMessage(mid); message.success('已删除(若 ai/有分则已存负样本)'); await loadMessages(); await loadScore() }
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
function openScore(mid: string, scoreBase: any, scoreNote: any, corrected?: any, correctedScore?: any) {
  scoreModalMid.value = mid
  const b = Number(scoreBase)
  scoreModalBase.value = (!isNaN(b) && scoreBase !== '' && scoreBase !== undefined && scoreBase !== null) ? b : 80
  scoreModalNote.value = scoreNote || ''
  scoreModalCorrected.value = corrected || ''
  const cs = Number(correctedScore)
  scoreModalCorrectedScore.value = (!isNaN(cs) && correctedScore !== '' && correctedScore !== undefined && correctedScore !== null) ? cs : 100
  scoreModalShow.value = true
}
async function applyScore() {
  if (!scoreModalMid.value) return
  try {
    const r = await setScore(scoreModalMid.value, scoreModalBase.value, scoreModalNote.value,
                             scoreModalCorrected.value, scoreModalCorrectedScore.value)
    message.success(`已改分:score = ${r.score}`)
    scoreModalShow.value = false; scoreModalMid.value = ''
    await loadMessages(); await loadScore()
  } catch (e: any) { message.error('' + e) }
}
async function dryRun() {
  if (!activeOid.value) return
  inferring.value = true
  try {
    const r = await reverseInferDryRun(activeOid.value, { mode: 'fill_empty' })
    inferDiff.value = r.diff; inferToken.value = r.confirm_token
    message.success(`反推预览完成(正 ${r.positive_count} / 负 ${r.negative_count})`)
  } catch (e: any) { message.error('' + e) }
  finally { inferring.value = false }
}
async function applyInfer() {
  try {
    await reverseInferApply(activeOid.value, inferToken.value)
    message.success('反推已落库'); inferDiff.value = null; inferToken.value = ''
  } catch (e: any) { message.error('' + e) }
}

// —— training 训练样本操作 ——
async function addRp() {
  if (!rpContent.value.trim()) { message.warning('请输入内容'); return }
  try {
    const body: any = { role: role.value, content: rpContent.value.trim() }
    if (role.value === 'assistant' && rpScoreBase.value !== null) body.score_base = rpScoreBase.value
    await addRoleplay(activeOid.value, body)
    rpContent.value = ''; rpScoreBase.value = null
    await loadMessages(); await loadRecentBlocks()
  } catch (e: any) { message.error('' + e) }
}
async function extractRp() {
  if (!activeBlockId.value) return
  extracting.value = true
  try {
    const r = await extractRoleplay(activeOid.value, activeBlockId.value)
    message.success(`已抽取 ${r.extracted} 条 / 写入 ${r.written} 条 / 去重 ${r.skipped_dup} 条`)
  } catch (e: any) { message.error('' + e) }
  finally { extracting.value = false }
}
function openRpScore(mid: string, score: any) {
  rpScoreMid.value = mid
  const b = Number(score)
  rpScoreVal.value = (!isNaN(b) && score !== '' && score !== undefined && score !== null) ? b : 80
  rpScoreShow.value = true
}
async function applyRpScore() {
  if (!rpScoreMid.value) return
  try {
    await setRoleplayScore(activeOid.value, rpScoreMid.value, rpScoreVal.value)
    message.success(`已改分:score = ${rpScoreVal.value}`)
    rpScoreShow.value = false; rpScoreMid.value = ''
    await loadMessages()
  } catch (e: any) { message.error('' + e) }
}
async function delRp(mid: string) {
  try {
    await deleteRoleplay(activeOid.value, mid)
    message.success('已删除(→neg)'); await loadMessages(); await loadRecentBlocks()
  } catch (e: any) { message.error('' + e) }
}
async function newRpSession() {
  try {
    await newRoleplaySession(activeOid.value || oid.value)
    message.success('已新建训练会话'); await loadRecentBlocks()
  } catch (e: any) { message.error('' + e) }
}
async function delRpSession(b: any) {
  try {
    await deleteRoleplaySession(b.block_id)
    message.success(`已删除训练会话(${b.msg_count} 条)`)
    if (activeBlockId.value === b.block_id) {
      activeBlockId.value = ''; currentBlock.value = null; messages.value = []
    }
    await loadRecentBlocks()
  } catch (e: any) { message.error('' + e) }
}

watch(reloadTick, () => refreshAll())

onMounted(async () => {
  // 取角色对用户称呼(拟人化:user 消息标签显示别名)
  try {
    const personas = await listPersonas()
    if (Array.isArray(personas) && personas.length) userAlias.value = personas[0].user_alias || ''
  } catch { /* 取不到别名不阻塞 */ }
  await loadRecentBlocks()
  startPoll()
  window.addEventListener('visibilitychange', onVis)
})
onUnmounted(() => { stopPoll(); window.removeEventListener('visibilitychange', onVis) })
</script>

<template>
  <div style="display:flex; height:calc(100vh - 92px)">
    <!-- 左栏:混合 block 列表(real+training) -->
    <div style="width:230px; border-right:1px solid #efeff5; overflow:auto; padding:8px; flex-shrink:0">
      <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px">
        <span style="font-weight:600; font-size:13px">会话(混合)</span>
        <n-space :size="4">
          <n-button size="tiny" type="primary" ghost @click="newRpSession">+训练</n-button>
          <n-button size="tiny" quaternary :loading="loadingBlocks" @click="refreshAll">刷新</n-button>
        </n-space>
      </div>
      <n-empty v-if="!recentBlocks.length" size="small" description="暂无会话(真实对话自动生成,+训练手动建)" />
      <div v-for="b in recentBlocks" :key="b.source + ':' + b.block_id"
           @click="selectBlock(b)"
           :style="{ padding:'8px 10px', borderRadius:'8px', cursor:'pointer', marginBottom:'4px',
             background: b.block_id === activeBlockId ? '#e8f1ff' : 'transparent' }">
        <div style="display:flex; align-items:center; justify-content:space-between">
          <span style="font-weight:600; font-size:13px">{{ fmtTs(b.start_ts) }}</span>
          <n-space :size="4" align="center">
            <n-tag size="tiny" :type="b.source === 'training' ? 'warning' : 'success'">
              {{ b.source === 'training' ? '训练' : '真实' }}
            </n-tag>
            <n-tag v-if="b.status === 'open'" size="tiny" type="success">进行中</n-tag>
          </n-space>
        </div>
        <div style="font-size:11px; color:#999; display:flex; justify-content:space-between; align-items:center; margin-top:2px">
          <span>{{ relTs(b.start_ts) }} · {{ b.msg_count }} 条</span>
          <n-popconfirm v-if="b.source === 'training'" @positive-click="delRpSession(b)">
            <template #trigger><n-button size="tiny" text type="error" @click.stop>删除</n-button></template>
            删除该训练会话({{ b.msg_count }} 条)?物理删不可恢复。
          </n-popconfirm>
          <n-popconfirm v-else @positive-click="delBlock(b)">
            <template #trigger><n-button size="tiny" text type="error" @click.stop>删除</n-button></template>
            删除该段会话({{ b.msg_count }} 条)?物理删不可恢复。
          </n-popconfirm>
        </div>
      </div>
    </div>

    <!-- 主区:按 source 切换 real/training -->
    <div style="flex:1; display:flex; flex-direction:column; overflow:hidden; padding-left:16px; min-width:0">

      <!-- ===== real 真实对话模式 ===== -->
      <template v-if="activeSource === 'real' && activeBlockId">
        <!-- 评分总览 -->
        <n-card v-if="activeOid" size="small" style="margin-bottom:12px; flex-shrink:0">
          <template #header>
            <n-space align="center">
              <span>评分总览</span>
              <n-tag v-if="health" size="small"
                     :type="(health.avg_score || 0) >= 70 ? 'success' : ((health.avg_score || 0) >= 50 ? 'warning' : 'error')">
                均分 {{ health?.avg_score ?? '—' }} / {{ health?.count ?? 0 }} 条
              </n-tag>
              <n-popconfirm @positive-click="clearAll">
                <template #trigger><n-button size="tiny" type="error" ghost>清空全部</n-button></template>
                清空当前用户的全部会话历史?物理删不可恢复。
              </n-popconfirm>
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
          <n-button v-if="currentBlock.status === 'open'" size="tiny" text @click="closeBlk(currentBlock.block_id)">关 block</n-button>
        </div>

        <!-- 真实对话流 -->
        <div ref="streamEl" style="flex:1; overflow:auto; padding-right:8px; min-height:0">
          <n-empty v-if="!messages.length" description="该段落暂无消息" />
          <div v-for="m in messages" :key="m.mid"
               :style="{ display:'flex', justifyContent: m.sender === 'user' ? 'flex-end' : 'flex-start', margin:'4px 0' }">
            <div :style="{ maxWidth:'72%', padding:'6px 10px', borderRadius:'10px',
              background: m.sender === 'user' ? '#DCF8C6' : (m.sender === 'system' ? '#f0f0f0' : '#E8F1FF'), color:'#222' }">
              <div style="font-size:11px; color:#888; display:flex; align-items:center; gap:6px">
                <span>{{ senderLabel(m) }} · {{ fmtTs(m.ts) }}</span>
                <n-tag v-if="m.score !== '' && m.score !== undefined && m.score !== null" size="tiny"
                       :type="Number(m.score) >= 85 ? 'success' : (Number(m.score) < 60 ? 'error' : 'default')">分 {{ m.score }}</n-tag>
                <n-tag v-if="m.status && m.status !== 'active'" size="tiny">{{ m.status }}</n-tag>
              </div>
              <div style="word-break:break-all; white-space:pre-wrap">{{ m.content }}</div>
              <div v-if="m.score_note" style="font-size:11px; color:#888; margin-top:2px; font-style:italic">批注:{{ m.score_note }}</div>
              <div v-if="m.corrected" style="font-size:11px; color:#2a7de1; background:#f0f7ff; border-radius:4px; padding:3px 6px; margin-top:3px">
                纠正回复(正样本 {{ m.corrected_score ?? 100 }}分):{{ m.corrected }}
              </div>
              <n-space v-if="m.status !== 'deleted'" style="margin-top:2px" align="center" :size="4">
                <n-button v-if="m.sender === 'ai' || m.sender === 'proxy'" size="tiny" type="primary" ghost
                          @click="openScore(m.mid, m.score_base, m.score_note, m.corrected, m.corrected_score)">改分</n-button>
                <n-popconfirm @positive-click="del(m.mid)">
                  <template #trigger><n-button size="tiny" type="error" ghost>删除</n-button></template>
                  删除(不可恢复;ai 回复删前存为负样本)?
                </n-popconfirm>
              </n-space>
            </div>
          </div>
        </div>

        <!-- 正负样本(折叠) -->
        <n-collapse v-if="activeOid" style="margin-top:8px; flex-shrink:0" :default-expanded-names="[]">
          <n-collapse-item title="正反样例" name="samples">
            <n-space vertical size="small">
              <div>
                <n-tag type="success" size="small">正样本({{ posSamples.length }})</n-tag>
                <div v-for="s in posSamples" :key="s.mid + s.source"
                     style="margin:2px 0; padding:3px 8px; background:#f6ffed; border-radius:4px; font-size:12px">[{{ s.score }}]{{ sourceTag(s) }} {{ s.text }}</div>
              </div>
              <div>
                <n-tag type="error" size="small">负样本({{ negSamples.length }})</n-tag>
                <div v-for="s in negSamples" :key="s.mid + s.source"
                     style="margin:2px 0; padding:3px 8px; background:#fff2f0; border-radius:4px; font-size:12px">[{{ s.score }}]{{ sourceTag(s) }} {{ s.text }}</div>
              </div>
            </n-space>
          </n-collapse-item>
        </n-collapse>
      </template>

      <!-- ===== training 训练样本模式 ===== -->
      <template v-else-if="activeSource === 'training' && activeBlockId">
        <!-- 抽取为记忆工具栏 -->
        <div style="flex-shrink:0; padding:6px 8px; border-bottom:1px solid #efeff5; display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:8px">
          <n-button size="small" type="warning" ghost :loading="extracting" @click="extractRp">抽取当前会话为记忆</n-button>
          <span style="font-size:11px; color:#999">把本会话训练样本抽成长期记忆(过滤 system + 防幻觉,用"{{ userAlias || '用户' }}"称呼)</span>
        </div>
        <!-- 训练样本流 -->
        <div ref="streamEl" style="flex:1; overflow:auto; padding-right:8px; min-height:0">
          <n-empty v-if="!messages.length" description="该训练会话暂无样本,从下方录入第一条开始" style="margin:40px auto" />
          <div v-for="m in messages" :key="m.mid"
               :style="{ display:'flex', justifyContent: m.role === 'user' ? 'flex-end' : (m.role === 'system' ? 'center' : 'flex-start'), margin:'4px 0' }">
            <div :style="{ maxWidth:'72%', padding:'6px 10px', borderRadius:'10px',
              background: m.role === 'user' ? '#DCF8C6' : (m.role === 'system' ? '#f0f0f0' : '#E8F1FF'), color:'#222' }">
              <div style="font-size:11px; color:#888; display:flex; align-items:center; gap:6px; flex-wrap:wrap">
                <n-tag size="tiny" :type="m.role === 'assistant' ? 'info' : (m.role === 'system' ? 'warning' : 'success')">{{ senderLabel(m) }}</n-tag>
                <n-tag v-if="m.score !== '' && m.score !== undefined && m.score !== null" size="tiny"
                       :type="Number(m.score) >= 85 ? 'success' : (Number(m.score) < 60 ? 'error' : 'default')">分 {{ m.score }}</n-tag>
                <n-button v-if="m.role === 'assistant'" size="tiny" text type="primary" @click="openRpScore(m.mid, m.score)">改分</n-button>
                <n-popconfirm @positive-click="delRp(m.mid)">
                  <template #trigger><n-button size="tiny" text type="error">删除</n-button></template>
                  删除(→neg)?
                </n-popconfirm>
              </div>
              <div style="word-break:break-all; white-space:pre-wrap">{{ m.content }}</div>
            </div>
          </div>
        </div>
        <!-- 录入区 -->
        <div style="flex-shrink:0; border-top:1px solid #efeff5; padding-top:8px">
          <n-space align="center" :wrap="false">
            <n-select v-model:value="role" :options="roleOptions" style="width:200px" />
            <n-input v-model:value="rpContent" placeholder="输入内容,回车追加到训练对话流..." style="flex:1" @keyup.enter="addRp" />
            <n-input-number v-if="role === 'assistant'" v-model:value="rpScoreBase" :min="0" :max="100"
                            placeholder="角色回复分数(可空)" style="width:150px" clearable />
            <n-button type="primary" @click="addRp">追加</n-button>
          </n-space>
          <div style="font-size:11px; color:#999; margin-top:4px">
            选"角色"时可填分数:≥85 作反推正样本(加强人设),&lt;60 作负样本(纠正人设)。录入铁律:user 行只写真用户会说的话(防幻觉)。
          </div>
        </div>
      </template>

      <!-- 空状态 -->
      <n-empty v-else description="左侧选择一个会话段落(真实/训练)" style="margin:auto" />

      <!-- real 改分弹窗(含 note + 纠正回复) -->
      <n-modal v-model:show="scoreModalShow" preset="dialog" title="改分">
        <n-space vertical>
          <span style="font-size:12px; color:#999">覆盖 score_base,保留历史 mood_bias 重算 score</span>
          <n-input-number v-model:value="scoreModalBase" :min="0" :max="100" />
          <span style="font-size:12px; color:#999">批注(说明为什么这个分,可选)</span>
          <n-input v-model:value="scoreModalNote" type="textarea" :rows="2" placeholder="例:语气自然但稍微跑题" />
          <span style="font-size:12px; color:#999">纠正回复(更符合人设的理想回复,可选)</span>
          <n-input v-model:value="scoreModalCorrected" type="textarea" :rows="3"
                   placeholder="例:换成角色口吻的理想说法。将作为正样本(最高权威)进人设反推;原回复保留不动" />
          <n-space align="center">
            <span style="font-size:12px; color:#999">纠正分数(纠正版有多理想,默认 100)</span>
            <n-input-number v-model:value="scoreModalCorrectedScore" :min="0" :max="100" size="small" style="width:120px" />
          </n-space>
          <span style="font-size:11px; color:#999">
            用法:原回复打低分(负样本,应避免)+ 填纠正回复(正样本,应学习),双样本驱动反推;QQ 已发的消息不重发
          </span>
        </n-space>
        <template #action>
          <n-button @click="scoreModalShow = false">取消</n-button>
          <n-button type="primary" @click="applyScore">确定</n-button>
        </template>
      </n-modal>

      <!-- training 改分弹窗 -->
      <n-modal v-model:show="rpScoreShow" preset="dialog" title="改 roleplay 评分">
        <n-space vertical>
          <span style="font-size:12px; color:#999">覆盖该角色回复分数(联动反推样本队列:高分正样本/低分负样本)</span>
          <n-input-number v-model:value="rpScoreVal" :min="0" :max="100" />
        </n-space>
        <template #action>
          <n-button @click="rpScoreShow = false">取消</n-button>
          <n-button type="primary" @click="applyRpScore">确定</n-button>
        </template>
      </n-modal>
    </div>
  </div>
</template>
