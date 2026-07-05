<script setup lang="ts">
/**
 * roleplay 训练样本(V2.0 改造 2026-07-05 #2):多会话管理 + IM 对话流 + assistant 回复评分(联动反推)。
 * 左栏会话列表(每段 block=一个训练会话)+「+新建」;主区对话流(user右/assistant左/system居中);
 * 底部录入选身份+内容(角色时可填分数);assistant 消息内联改分。评分按阈值作反推正/负样本驱动人设进化。
 * roleplay 物理隔离不进 LLM 上下文。去 oid 输入框,启动自动加载全局 oid。
 * 作者: 李文煜
 */
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import {
  NSpace, NInput, NButton, NSelect, NTag, NPopconfirm, NEmpty, NModal, NInputNumber, useMessage,
} from 'naive-ui'
import {
  listRoleplaySessions, newRoleplaySession, addRoleplay, listRoleplay,
  updateRoleplay, setRoleplayScore, deleteRoleplay,
} from '@/api'
import { useObject } from '@/composables/useObject'

const message = useMessage()
const { oid, reloadTick, ensureOid } = useObject()
watch(reloadTick, () => loadSessions())

// —— 左栏会话列表 ——
const sessions = ref<any[]>([])
const activeBlockId = ref('')
const loadingSessions = ref(false)

// —— 主区对话流 ——
const messages = ref<any[]>([])
const streamEl = ref<HTMLElement | null>(null)

// —— 录入 ——
const role = ref('user')
const content = ref('')
const scoreBase = ref<number | null>(null)   // 录入时角色回复评分(可空)

const roleOptions = [
  { label: '作为用户说(user)', value: 'user' },
  { label: '作为角色说(assistant)', value: 'assistant' },
  { label: '系统旁白(system)', value: 'system' },
]

// —— 改分弹窗 ——
const scoreShow = ref(false)
const scoreMid = ref('')
const scoreVal = ref(80)

// —— 改内容弹窗 ——
const editShow = ref(false)
const editMid = ref('')
const editContent = ref('')

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

async function loadSessions() {
  if (!oid.value || oid.value === 'default') return
  loadingSessions.value = true
  try {
    sessions.value = await listRoleplaySessions(oid.value)
    // 无选中或已不在列表 → 自动选最近(第一个)
    if (sessions.value.length && !sessions.value.some((s) => s.block_id === activeBlockId.value)) {
      await selectSession(sessions.value[0])
    } else if (activeBlockId.value) {
      await loadMessages()
    }
  } catch (e: any) { message.error('' + e) }
  finally { loadingSessions.value = false }
}

async function selectSession(s: any) {
  activeBlockId.value = s.block_id
  messages.value = []
  await loadMessages()
}

async function loadMessages() {
  if (!oid.value || !activeBlockId.value) return
  try {
    const r = await listRoleplay(oid.value, { block_id: activeBlockId.value })
    messages.value = r.messages || []
    await nextTick()
    if (streamEl.value) streamEl.value.scrollTop = streamEl.value.scrollHeight
  } catch (e: any) { message.error('' + e) }
}

async function newSession() {
  if (!oid.value || oid.value === 'default') return
  try {
    const b = await newRoleplaySession(oid.value)
    message.success('已新建会话')
    await loadSessions()
    await selectSession(b)
  } catch (e: any) { message.error('' + e) }
}

async function add() {
  if (!content.value.trim()) { message.warning('请输入内容'); return }
  try {
    const body: any = { role: role.value, content: content.value.trim() }
    if (role.value === 'assistant' && scoreBase.value !== null) {
      body.score_base = scoreBase.value
    }
    await addRoleplay(oid.value, body)
    content.value = ''
    scoreBase.value = null
    await loadMessages()
    await loadSessions()   // 刷新会话 msg_count
  } catch (e: any) { message.error('' + e) }
}

function openScore(mid: string, score: any) {
  scoreMid.value = mid
  const b = Number(score)
  scoreVal.value = (!isNaN(b) && score !== '' && score !== undefined && score !== null) ? b : 80
  scoreShow.value = true
}
async function applyScore() {
  if (!scoreMid.value) return
  try {
    const r = await setRoleplayScore(oid.value, scoreMid.value, scoreVal.value)
    message.success(`已改分:score = ${r.score}`)
    scoreShow.value = false; scoreMid.value = ''
    await loadMessages()
  } catch (e: any) { message.error('' + e) }
}

function openEdit(mid: string, c: string) {
  editMid.value = mid; editContent.value = c || ''; editShow.value = true
}
async function applyEdit() {
  if (!editMid.value) return
  try {
    await updateRoleplay(oid.value, editMid.value, editContent.value)
    message.success('已修改'); editShow.value = false; editMid.value = ''
    await loadMessages()
  } catch (e: any) { message.error('' + e) }
}

async function del(mid: string) {
  try {
    await deleteRoleplay(oid.value, mid)
    message.success('已删除(→neg)')
    await loadMessages(); await loadSessions()
  } catch (e: any) { message.error('' + e) }
}

async function poll() {
  if (typeof document !== 'undefined' && document.hidden) return
  await loadSessions()
}
function startPoll() { stopPoll(); pollTimer = window.setInterval(poll, POLL_MS) }
function stopPoll() { if (pollTimer !== null) { clearInterval(pollTimer); pollTimer = null } }
function onVis() { document.hidden ? stopPoll() : (poll(), startPoll()) }

onMounted(async () => {
  await ensureOid()
  await loadSessions()
  startPoll()
  window.addEventListener('visibilitychange', onVis)
})
onUnmounted(() => { stopPoll(); window.removeEventListener('visibilitychange', onVis) })
</script>

<template>
  <div style="display:flex; height:calc(100vh - 92px)">
    <!-- 左栏:训练会话列表 -->
    <div style="width:220px; border-right:1px solid #efeff5; overflow:auto; padding:8px; flex-shrink:0">
      <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px">
        <span style="font-weight:600; font-size:13px">训练会话</span>
        <n-button size="tiny" type="primary" ghost @click="newSession">+新建</n-button>
      </div>
      <n-empty v-if="!sessions.length" size="small" description="暂无会话,点+新建开始" />
      <div v-for="s in sessions" :key="s.block_id"
           @click="selectSession(s)"
           :style="{ padding:'8px 10px', borderRadius:'8px', cursor:'pointer', marginBottom:'4px',
             background: s.block_id === activeBlockId ? '#e8f1ff' : 'transparent' }">
        <div style="display:flex; align-items:center; justify-content:space-between">
          <span style="font-weight:600; font-size:13px">{{ fmtTs(s.start_ts) }}</span>
          <n-tag size="tiny" :type="s.status === 'open' ? 'success' : 'default'">{{ s.status === 'open' ? '进行中' : '已结束' }}</n-tag>
        </div>
        <div style="font-size:11px; color:#999; margin-top:2px">{{ relTs(s.start_ts) }} · {{ s.msg_count }} 条</div>
      </div>
    </div>

    <!-- 主区:对话流 + 录入 -->
    <div style="flex:1; display:flex; flex-direction:column; overflow:hidden; padding-left:16px; min-width:0">
      <!-- 对话流 -->
      <div ref="streamEl" style="flex:1; overflow:auto; padding:8px; min-height:0">
        <n-empty v-if="!messages.length" description="该会话暂无样本,从下方录入第一条开始" style="margin:40px auto" />
        <div v-for="m in messages" :key="m.mid"
             :style="{ display:'flex', justifyContent: m.role === 'user' ? 'flex-end' : (m.role === 'system' ? 'center' : 'flex-start'), margin:'4px 0' }">
          <div :style="{ maxWidth:'72%', padding:'6px 10px', borderRadius:'10px',
            background: m.role === 'user' ? '#DCF8C6' : (m.role === 'system' ? '#f0f0f0' : '#E8F1FF'), color:'#222' }">
            <div style="font-size:11px; color:#888; display:flex; align-items:center; gap:6px; flex-wrap:wrap">
              <n-tag size="tiny" :type="m.role === 'assistant' ? 'info' : (m.role === 'system' ? 'warning' : 'success')">{{ m.role }}</n-tag>
              <n-tag v-if="m.score !== '' && m.score !== undefined && m.score !== null" size="tiny"
                     :type="Number(m.score) >= 85 ? 'success' : (Number(m.score) < 60 ? 'error' : 'default')">分 {{ m.score }}</n-tag>
              <n-tag v-if="m.status === 'edited'" size="tiny">edited</n-tag>
              <n-button v-if="m.role === 'assistant'" size="tiny" text type="primary" @click="openScore(m.mid, m.score)">改分</n-button>
              <n-button size="tiny" text @click="openEdit(m.mid, m.content)">编辑</n-button>
              <n-popconfirm @positive-click="del(m.mid)">
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
          <n-input v-model:value="content" placeholder="输入内容,回车追加到对话流..." style="flex:1" @keyup.enter="add" />
          <n-input-number v-if="role === 'assistant'" v-model:value="scoreBase" :min="0" :max="100"
                          placeholder="角色回复分数(可空)" style="width:150px" clearable />
          <n-button type="primary" @click="add">追加</n-button>
        </n-space>
        <div style="font-size:11px; color:#999; margin-top:4px">
          选"角色"时可填分数(0-100):≥85 作反推正样本(加强人设),&lt;60 作负样本(纠正人设),留空则不评分。
        </div>
      </div>
    </div>

    <!-- 改分弹窗 -->
    <n-modal v-model:show="scoreShow" preset="dialog" title="改 roleplay 评分">
      <n-space vertical>
        <span style="font-size:12px; color:#999">覆盖该角色回复的分数(联动反推样本队列:高分正样本/低分负样本)</span>
        <n-input-number v-model:value="scoreVal" :min="0" :max="100" />
      </n-space>
      <template #action>
        <n-button @click="scoreShow = false">取消</n-button>
        <n-button type="primary" @click="applyScore">确定</n-button>
      </template>
    </n-modal>

    <!-- 改内容弹窗 -->
    <n-modal v-model:show="editShow" preset="card" title="改写样本内容" style="width:640px;max-width:92vw">
      <n-space vertical :size="12">
        <n-input v-model:value="editContent" type="textarea" :rows="8" autofocus />
        <n-space justify="end">
          <n-button @click="editShow = false">取消</n-button>
          <n-button type="primary" @click="applyEdit">确定</n-button>
        </n-space>
      </n-space>
    </n-modal>
  </div>
</template>
