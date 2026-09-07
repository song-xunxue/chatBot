<script setup lang="ts">
/**
 * 移动端对话历史(功能对等 PC History.vue,窄屏重排):
 * ① 顶栏 + 会话段选择弹窗(替代 PC 左栏混合 block 列表 real+training:切换/新建训练会话/删除段)
 * ② 全宽 IM 对话流(real:user 右·其余左;training:user 右·system 居中·assistant 左;
 *    user 显示 user_alias,proxy 显示 代答/手动),ai/proxy 改分(含纠正回复)+删除,training 录入/改分/删除/抽取为记忆
 * ③ 评分总览(均分+正中负文字计数,Bar 图省略)+ 反推 dryRun/确认落库 + 正反样例 折叠置底
 * 逻辑与 PC 端完全一致(useObject 共享 oid + ensureOid + 5s 轮询 + visibilitychange 暂停),
 * 仅 template 按手机窄屏重组:左栏→弹窗选择器、图表→文字计数、单行输入改 textarea、主按钮 size large(触摸≥44px)。
 * 作者: 李文煜
 */
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import {
  NSpace, NInput, NButton, NSelect, NTag, NPopconfirm, NEmpty, NInputNumber,
  NCollapse, NCollapseItem, NModal, useMessage,
} from 'naive-ui'
import {
  listRecentBlocks, listMessages, deleteMessage, closeBlock, deleteBlock, clearHistory,
  getHealth, getSamples, reverseInferDryRun, reverseInferApply, setScore,
  listRoleplay, addRoleplay, setRoleplayScore, deleteRoleplay, extractRoleplay,
  newRoleplaySession, deleteRoleplaySession, listPersonas,
} from '@/api'
import { useObject } from '@/composables/useObject'

const message = useMessage()
const { oid, reloadTick, ensureOid } = useObject()
watch(reloadTick, () => load())

// —— 会话段列表(混合 real+training,弹窗选择器承载,替代 PC 左栏)——
const recentBlocks = ref<any[]>([])
const activeBlockId = ref('')
const activeOid = ref('')
const activeSource = ref<'real' | 'training'>('real')   // 当前 block 来源,决定主区模式
const loadingBlocks = ref(false)
const userAlias = ref('')                                // 角色对用户称呼(拟人化,显示代"user")
const blockPickerShow = ref(false)                       // 会话段选择弹窗

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

// —— 会话段列表(混合 real+training,轮询入口)——
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

// 页面总 load(刷新按钮/reloadTick 挂点):oid 无效直接返回(V3.0 须为 QQ 号)
async function load() {
  if (!oid.value || oid.value === 'default') return
  await loadRecentBlocks()
  if (activeOid.value && activeSource.value === 'real') await loadScore()
}

// 弹窗里选中一个会话段:切换 + 关弹窗
async function pickBlock(b: any) {
  await selectBlock(b)
  blockPickerShow.value = false
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

onMounted(async () => {
  await ensureOid()
  // 取角色对用户称呼(拟人化:user 消息标签显示别名)
  try {
    const personas = await listPersonas()
    if (Array.isArray(personas) && personas.length) userAlias.value = personas[0].user_alias || ''
  } catch { /* 取不到别名不阻塞 */ }
  await load()
  startPoll()
  window.addEventListener('visibilitychange', onVis)
})
onUnmounted(() => { stopPoll(); window.removeEventListener('visibilitychange', onVis) })
</script>

<template>
  <n-space vertical size="medium">
    <!-- 顶栏:标题 + 刷新 + 会话段切换(替代 PC 左栏) -->
    <div class="m-topbar">
      <span class="m-title">对话历史</span>
      <n-space :size="6">
        <n-button size="small" quaternary :loading="loadingBlocks" @click="load">刷新</n-button>
        <n-button size="small" type="primary" ghost @click="blockPickerShow = true">切换会话</n-button>
      </n-space>
    </div>

    <!-- 当前会话段信息条(选中后展示;关 block 入口) -->
    <div v-if="currentBlock && activeBlockId" class="m-blockbar">
      <n-space :size="6" align="center">
        <n-tag size="small" :type="activeSource === 'training' ? 'warning' : 'success'">
          {{ activeSource === 'training' ? '训练' : '真实' }}
        </n-tag>
        <span class="m-label">{{ fmtTs(currentBlock.start_ts) }} → {{ fmtTs(currentBlock.end_ts) }} · {{ currentBlock.msg_count }} 条</span>
      </n-space>
      <n-space :size="6" align="center">
        <n-tag size="small" :type="currentBlock.status === 'open' ? 'success' : 'default'">{{ currentBlock.status }}</n-tag>
        <n-button v-if="currentBlock.status === 'open'" size="small" quaternary @click="closeBlk(currentBlock.block_id)">关 block</n-button>
      </n-space>
    </div>

    <!-- oid 未绑定提示(照 TakeoverMobile:V3.0 oid 须为 QQ 号) -->
    <div v-if="!oid || oid === 'default'" class="m-hint" style="color:#d03050">
      oid 未绑定真实会话(V3.0 须为 QQ 号):先在 QQ 上与角色对话一次即可自动绑定
    </div>

    <n-empty v-else-if="!recentBlocks.length" size="small" description="暂无会话(真实对话自动生成,+训练手动建)" />

    <!-- ===== real 真实对话模式 ===== -->
    <template v-else-if="activeSource === 'real' && activeBlockId">
      <!-- 真实对话流(内滚动容器,贴底自动跟随) -->
      <div ref="streamEl" class="m-stream">
        <n-empty v-if="!messages.length" size="small" description="该段落暂无消息" />
        <div v-for="m in messages" :key="m.mid"
             :style="{ display:'flex', justifyContent: m.sender === 'user' ? 'flex-end' : 'flex-start', margin:'4px 0' }">
          <div class="m-bubble"
               :style="{ background: m.sender === 'user' ? '#DCF8C6' : (m.sender === 'system' ? '#f0f0f0' : '#E8F1FF') }">
            <div class="m-meta">
              <span class="m-sender">{{ senderLabel(m) }} · {{ fmtTs(m.ts) }}</span>
              <n-tag v-if="m.score !== '' && m.score !== undefined && m.score !== null" size="tiny"
                     :type="Number(m.score) >= 85 ? 'success' : (Number(m.score) < 60 ? 'error' : 'default')">分 {{ m.score }}</n-tag>
              <n-tag v-if="m.status && m.status !== 'active'" size="tiny">{{ m.status }}</n-tag>
            </div>
            <div class="m-content">{{ m.content }}</div>
            <div v-if="m.score_note" class="m-note">批注:{{ m.score_note }}</div>
            <div v-if="m.corrected" class="m-corrected">纠正回复(正样本 {{ m.corrected_score ?? 100 }}分):{{ m.corrected }}</div>
            <n-space v-if="m.status !== 'deleted'" :size="6" align="center" style="margin-top:4px">
              <n-button v-if="m.sender === 'ai' || m.sender === 'proxy'" size="small" type="primary" ghost
                        @click="openScore(m.mid, m.score_base, m.score_note, m.corrected, m.corrected_score)">改分</n-button>
              <n-popconfirm @positive-click="del(m.mid)">
                <template #trigger><n-button size="small" type="error" ghost>删除</n-button></template>
                删除(不可恢复;ai 回复删前存为负样本)?
              </n-popconfirm>
            </n-space>
          </div>
        </div>
      </div>

      <!-- 评分总览 + 正反样例(折叠置底,低频) -->
      <n-collapse v-if="activeOid" :default-expanded-names="[]">
        <n-collapse-item title="评分总览" name="health">
          <n-space vertical size="small">
            <n-space :size="8" align="center">
              <n-tag v-if="health" size="small"
                     :type="(health.avg_score || 0) >= 70 ? 'success' : ((health.avg_score || 0) >= 50 ? 'warning' : 'error')">
                均分 {{ health?.avg_score ?? '—' }} / {{ health?.count ?? 0 }} 条
              </n-tag>
              <span v-if="health && (health.avg_score || 0) < 60 && health.count > 0" style="color:#d03050; font-size:12px">
                ⚠ 人设可能跑偏
              </span>
            </n-space>
            <!-- PC Bar 图改文字计数(窄屏省略图表库引用) -->
            <div class="m-hint">正样本 {{ health?.positive || 0 }} · 中性 {{ health?.neutral || 0 }} · 负样本 {{ health?.negative || 0 }}</div>
            <n-space :size="8" align="center">
              <n-button size="large" type="primary" ghost :loading="inferring" @click="dryRun">反推人设</n-button>
              <n-popconfirm v-if="inferToken" @positive-click="applyInfer">
                <template #trigger><n-button size="large" type="warning">确认落库</n-button></template>
                确认应用反推 diff 到人设?
              </n-popconfirm>
            </n-space>
            <details v-if="inferDiff">
              <summary class="m-summary">反推 diff 预览</summary>
              <pre class="m-pre">{{ JSON.stringify(inferDiff, null, 2) }}</pre>
            </details>
            <n-popconfirm @positive-click="clearAll">
              <template #trigger><n-button size="small" type="error" ghost block>清空全部历史</n-button></template>
              清空当前用户的全部会话历史?物理删不可恢复。
            </n-popconfirm>
          </n-space>
        </n-collapse-item>
        <n-collapse-item title="正反样例" name="samples">
          <n-space vertical size="small">
            <div>
              <n-tag type="success" size="small">正样本({{ posSamples.length }})</n-tag>
              <div v-for="s in posSamples" :key="s.mid + s.source" class="m-sample pos">[{{ s.score }}]{{ sourceTag(s) }} {{ s.text }}</div>
            </div>
            <div>
              <n-tag type="error" size="small">负样本({{ negSamples.length }})</n-tag>
              <div v-for="s in negSamples" :key="s.mid + s.source" class="m-sample neg">[{{ s.score }}]{{ sourceTag(s) }} {{ s.text }}</div>
            </div>
          </n-space>
        </n-collapse-item>
      </n-collapse>
    </template>

    <!-- ===== training 训练样本模式 ===== -->
    <template v-else-if="activeSource === 'training' && activeBlockId">
      <!-- 抽取为记忆工具栏 -->
      <n-button size="large" type="warning" ghost block :loading="extracting" @click="extractRp">抽取当前会话为记忆</n-button>
      <div class="m-hint">把本会话训练样本抽成长期记忆(过滤 system + 防幻觉,用"{{ userAlias || '用户' }}"称呼)</div>

      <!-- 训练样本流 -->
      <div ref="streamEl" class="m-stream">
        <n-empty v-if="!messages.length" size="small" description="该训练会话暂无样本,从下方录入第一条开始" />
        <div v-for="m in messages" :key="m.mid"
             :style="{ display:'flex', justifyContent: m.role === 'user' ? 'flex-end' : (m.role === 'system' ? 'center' : 'flex-start'), margin:'4px 0' }">
          <div class="m-bubble"
               :style="{ background: m.role === 'user' ? '#DCF8C6' : (m.role === 'system' ? '#f0f0f0' : '#E8F1FF') }">
            <div class="m-meta">
              <n-tag size="tiny" :type="m.role === 'assistant' ? 'info' : (m.role === 'system' ? 'warning' : 'success')">{{ senderLabel(m) }}</n-tag>
              <n-tag v-if="m.score !== '' && m.score !== undefined && m.score !== null" size="tiny"
                     :type="Number(m.score) >= 85 ? 'success' : (Number(m.score) < 60 ? 'error' : 'default')">分 {{ m.score }}</n-tag>
              <n-button v-if="m.role === 'assistant'" size="tiny" text type="primary" @click="openRpScore(m.mid, m.score)">改分</n-button>
              <n-popconfirm @positive-click="delRp(m.mid)">
                <template #trigger><n-button size="tiny" text type="error">删除</n-button></template>
                删除(→neg)?
              </n-popconfirm>
            </div>
            <div class="m-content">{{ m.content }}</div>
          </div>
        </div>
      </div>

      <!-- 录入区(上下堆叠:角色选择→内容→分数→追加) -->
      <div class="m-inputbar">
        <n-select v-model:value="role" :options="roleOptions" size="large" />
        <n-input v-model:value="rpContent" type="textarea" placeholder="输入内容(手机端点「追加」生效)..."
                 :autosize="{ minRows: 2, maxRows: 6 }" />
        <n-space v-if="role === 'assistant'" :size="8" align="center">
          <span class="m-label">角色回复分数(可空)</span>
          <n-input-number v-model:value="rpScoreBase" :min="0" :max="100" size="large"
                          style="width:140px" clearable placeholder="可空" />
        </n-space>
        <n-button type="primary" size="large" block @click="addRp">追加</n-button>
        <div class="m-hint">选"角色"时可填分数:≥85 作反推正样本(加强人设),&lt;60 作负样本(纠正人设)。录入铁律:user 行只写真用户会说的话(防幻觉)。</div>
      </div>
    </template>

    <!-- 空状态 -->
    <n-empty v-else size="small" description="点击右上「切换会话」选择一个会话段落(真实/训练)" />

    <!-- 会话段选择弹窗(替代 PC 左栏:切换/新建训练/删除段) -->
    <n-modal v-model:show="blockPickerShow" preset="card" title="选择会话段" style="width:94vw; max-width:520px">
      <n-space vertical size="small">
        <n-button size="medium" type="primary" ghost block @click="newRpSession">+ 新建训练会话</n-button>
        <div class="m-picker-list">
          <n-empty v-if="!recentBlocks.length" size="small" description="暂无会话(真实对话自动生成,+训练手动建)" />
          <div v-for="b in recentBlocks" :key="b.source + ':' + b.block_id"
               class="m-block-item" :class="{ active: b.block_id === activeBlockId }"
               @click="pickBlock(b)">
            <div class="m-meta" style="justify-content:space-between">
              <span class="m-label" style="font-weight:600">{{ fmtTs(b.start_ts) }}</span>
              <n-space :size="4" align="center">
                <n-tag size="tiny" :type="b.source === 'training' ? 'warning' : 'success'">
                  {{ b.source === 'training' ? '训练' : '真实' }}
                </n-tag>
                <n-tag v-if="b.status === 'open'" size="tiny" type="success">进行中</n-tag>
              </n-space>
            </div>
            <div class="m-block-sub">
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
      </n-space>
    </n-modal>

    <!-- real 改分弹窗(含 note + 纠正回复) -->
    <n-modal v-model:show="scoreModalShow" preset="dialog" title="改分">
      <n-space vertical size="small">
        <span class="m-hint">覆盖 score_base,保留历史 mood_bias 重算 score</span>
        <n-input-number v-model:value="scoreModalBase" :min="0" :max="100" size="large" style="width:100%" />
        <span class="m-hint">批注(说明为什么这个分,可选)</span>
        <n-input v-model:value="scoreModalNote" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }"
                 placeholder="例:语气自然但稍微跑题" />
        <span class="m-hint">纠正回复(更符合人设的理想回复,可选)</span>
        <n-input v-model:value="scoreModalCorrected" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }"
                 placeholder="例:换成角色口吻的理想说法。将作为正样本(最高权威)进人设反推;原回复保留不动" />
        <n-space align="center" :size="8">
          <span class="m-hint">纠正分数(纠正版有多理想,默认 100)</span>
          <n-input-number v-model:value="scoreModalCorrectedScore" :min="0" :max="100" size="small" style="width:110px" />
        </n-space>
        <span class="m-hint">用法:原回复打低分(负样本,应避免)+ 填纠正回复(正样本,应学习),双样本驱动反推;QQ 已发的消息不重发</span>
      </n-space>
      <template #action>
        <n-button size="large" @click="scoreModalShow = false">取消</n-button>
        <n-button size="large" type="primary" @click="applyScore">确定</n-button>
      </template>
    </n-modal>

    <!-- training 改分弹窗 -->
    <n-modal v-model:show="rpScoreShow" preset="dialog" title="改 roleplay 评分">
      <n-space vertical size="small">
        <span class="m-hint">覆盖该角色回复分数(联动反推样本队列:高分正样本/低分负样本)</span>
        <n-input-number v-model:value="rpScoreVal" :min="0" :max="100" size="large" style="width:100%" />
      </n-space>
      <template #action>
        <n-button size="large" @click="rpScoreShow = false">取消</n-button>
        <n-button size="large" type="primary" @click="applyRpScore">确定</n-button>
      </template>
    </n-modal>
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
.m-blockbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 6px;
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 8px 10px;
  background: #fafafa;
}
.m-stream {
  max-height: 62vh;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  padding-right: 2px;
}
.m-bubble {
  max-width: 85%;
  padding: 8px 12px;
  border-radius: 10px;
  color: #222;
}
.m-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 2px;
}
.m-sender {
  font-size: 11px;
  color: #888;
}
.m-content {
  word-break: break-all;
  white-space: pre-wrap;
}
.m-note {
  font-size: 11px;
  color: #888;
  font-style: italic;
  margin-top: 2px;
}
.m-corrected {
  font-size: 11px;
  color: #2a7de1;
  background: #f0f7ff;
  border-radius: 4px;
  padding: 3px 6px;
  margin-top: 3px;
  word-break: break-all;
}
.m-summary {
  cursor: pointer;
  font-size: 12px;
  color: #666;
}
.m-pre {
  background: #f5f5f5;
  padding: 8px;
  max-height: 180px;
  overflow: auto;
  font-size: 11px;
  margin: 4px 0;
  white-space: pre-wrap;
  word-break: break-all;
}
.m-sample {
  margin: 2px 0;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 12px;
  word-break: break-all;
}
.m-sample.pos {
  background: #f6ffed;
}
.m-sample.neg {
  background: #fff2f0;
}
.m-inputbar {
  display: flex;
  flex-direction: column;
  gap: 8px;
  border-top: 1px solid #efeff5;
  padding-top: 10px;
}
.m-picker-list {
  max-height: 60vh;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}
.m-block-item {
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 6px;
  cursor: pointer;
}
.m-block-item.active {
  background: #e8f1ff;
  border-color: #b6d4ff;
}
.m-block-sub {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: #999;
  margin-top: 2px;
}
.m-label {
  font-size: 13px;
}
.m-hint {
  font-size: 11px;
  color: #999;
}
</style>
