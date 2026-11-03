<script setup lang="ts">
/**
 * 移动端日记页(功能对等 PC Diary.vue,窄屏重排,2026-10-26):
 * 顶栏(标题 + 刷新)→"立即补做"大按钮(touch ≥44px)→ 日期横向滚动 chip 行(当前项暖色)
 * → 她的梦 / 她的日记(key_events 换行 flex wrap)/ 当天心情曲线 三卡堆叠(间距 --sp-3)。
 * 数据与 API 同 PC;oid 由 useObject.ensureOid 自动取(仅补做时传给后端,移动端无头部输入框);
 * 详情 404 → 空态提示而非报错。
 * 日期: 2026-10-26

2026-11-01
变更说明:
  1. 日记管理批次对齐 PC:日期 chip 带 kind 标签/详情工具条(编辑/重提炼/删除)/
     写日常日记按钮/手写新增遮罩(kind=manual)
 */
import { ref, computed, watch, onMounted } from 'vue'
import { Line } from 'vue-chartjs'
import { Chart as ChartJS, Title, Tooltip, Legend, LineElement, PointElement, CategoryScale, LinearScale } from 'chart.js'
import { NButton, NEmpty, NPopconfirm, NSpin, useMessage } from 'naive-ui'
import { getDiaryList, getDiary, runDiary, updateDiary, deleteDiary, createDiary, regenDiaryMemory } from '@/api'
import { useObject } from '@/composables/useObject'
import { darkChartScales } from '@/styles/darkChart'

ChartJS.register(Title, Tooltip, Legend, LineElement, PointElement, CategoryScale, LinearScale)

const message = useMessage()
const { oid, reloadTick, ensureOid } = useObject()   // oid 自动取最近会话(补做传参)+ 刷新信号

// tone → 文案/配色映射(positive 暖色甜梦 / negative 红色噩梦 / neutral 灰色平静)
function toneLabel(t: string): string {
  return t === 'positive' ? '甜梦' : t === 'negative' ? '噩梦' : '平静'
}
function toneClass(t: string): string {
  return t === 'positive' ? 'chip-warm' : t === 'negative' ? 'chip-danger' : ''
}

// kind → 短文案(2026-11-01:dream 梦/journal 日常/manual 手写;chip 窄屏用单字/双字)
function kindOf(e: any): string {
  return (e?.kind || 'dream') as string
}
function kindLabel(k: string): string {
  return k === 'journal' ? '日常' : k === 'manual' ? '手写' : '梦'
}

// —— 日期列表(倒序,最近 30 天)——
interface DiaryItem { date: string; tone: string; kind?: string; excerpt?: string }
const entries = ref<DiaryItem[]>([])
const selectedDate = ref('')
const loadingList = ref(false)

async function loadList() {
  loadingList.value = true
  try {
    const r = await getDiaryList(30)
    entries.value = (r && r.items) || []
    if (entries.value.length && !entries.value.some((e) => e.date === selectedDate.value)) {
      await select(entries.value[0].date)   // 默认选中最近一天
    } else if (!entries.value.length) {
      selectedDate.value = ''
      detail.value = null
      notFound.value = false
    }
  } catch (e: any) { message.error('' + e) }
  finally { loadingList.value = false }
}

// —— 单日详情 ——
const detail = ref<any>(null)
const notFound = ref(false)
const loadingDetail = ref(false)

async function select(date: string) {
  selectedDate.value = date
  detail.value = null
  notFound.value = false
  loadingDetail.value = true
  try {
    detail.value = await getDiary(date)
  } catch (e: any) {
    // 404(详情被删/日期越界)不算错误,空态提示;其余弹错
    if (e?.response?.status === 404) notFound.value = true
    else message.error('' + e)
  } finally { loadingDetail.value = false }
}

// —— 立即补做(给今天手动跑一次 dream;oid 未绑真实会话时禁用,同 MoodMobile 惯例)——
const running = ref(false)
const oidReady = computed(() => !!oid.value && oid.value !== 'default')
async function runToday() {
  running.value = true
  try {
    const entry = await runDiary({ object_id: oid.value, kind: 'dream' })
    message.success(`已生成 ${entry?.date || ''} 的梦与日记`)
    await loadList()
    if (entry?.date) await select(entry.date)
  } catch {
    message.error('生成失败(无素材或 LLM 不可用)')
  } finally { running.value = false }
}

// —— 写日常日记(2026-11-01:kind=journal 总结今天)——
const journaling = ref(false)
async function runJournalToday() {
  journaling.value = true
  try {
    const entry = await runDiary({ object_id: oid.value, kind: 'journal' })
    message.success(`已写好 ${entry?.date || ''} 的日常日记`)
    await loadList()
    if (entry?.date) await select(entry.date)
  } catch {
    message.error('生成失败(无素材或 LLM 不可用)')
  } finally { journaling.value = false }
}

// —— 删除(2026-11-01:详情工具条,后端连记忆一起清)——
const deleting = ref(false)
async function removeDiary() {
  deleting.value = true
  try {
    await deleteDiary(selectedDate.value)
    message.success(`已删除 ${selectedDate.value} 的日记(事件记忆一并清理)`)
    selectedDate.value = ''
    detail.value = null
    await loadList()
  } catch (e: any) { message.error('删除失败:' + e) }
  finally { deleting.value = false }
}

// —— 编辑模式(2026-11-01:保存走 PUT,默认重提炼记忆)——
const editing = ref(false)
const saving = ref(false)
const editDiary = ref('')
const editDream = ref('')
const editEvents = ref('')
function startEdit() {
  editDiary.value = detail.value?.diary || ''
  editDream.value = detail.value?.dream || ''
  editEvents.value = (detail.value?.key_events || []).join('、')
  editing.value = true
}
async function saveEdit() {
  if (!editDiary.value.trim()) { message.error('日记正文不能为空'); return }
  saving.value = true
  try {
    const events = editEvents.value.split(/[、,，]/).map((s) => s.trim()).filter(Boolean)
    const body: Record<string, any> = { diary: editDiary.value.trim(), regen_memory: true, key_events: events }
    if (editDream.value.trim() || detail.value?.dream) body.dream = editDream.value.trim()
    detail.value = await updateDiary(selectedDate.value, body)
    editing.value = false
    message.success('已保存(事件记忆已同步重提炼)')
    await loadList()
  } catch (e: any) { message.error('保存失败:' + e) }
  finally { saving.value = false }
}

// —— 重提炼记忆(2026-11-01 兜底按钮)——
const regening = ref(false)
async function regenMemory() {
  regening.value = true
  try {
    await regenDiaryMemory(selectedDate.value)
    message.success('已从这篇日记重新提炼事件记忆')
  } catch (e: any) { message.error('重提炼失败:' + e) }
  finally { regening.value = false }
}

// —— 手写新增(2026-11-01 遮罩,同日期已有覆盖)——
const showCreate = ref(false)
const creating = ref(false)
const createDate = ref('')
const createText = ref('')
function todayStr(): string {
  const d = new Date()
  const p = (x: number) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}
async function submitCreate() {
  if (!createDate.value) { message.error('先选日期'); return }
  if (!createText.value.trim()) { message.error('日记正文不能为空'); return }
  creating.value = true
  try {
    const r = await createDiary({ date: createDate.value, diary: createText.value.trim(), object_id: oid.value || undefined })
    message.success(r?.overwritten ? `已覆盖 ${createDate.value} 原有日记` : `已新增 ${createDate.value} 的手写日记`)
    showCreate.value = false
    createText.value = ''
    await loadList()
    await select(createDate.value)
  } catch (e: any) { message.error('新增失败:' + e) }
  finally { creating.value = false }
}

// 毫秒时间戳 → HH:mm(mood 曲线横轴 / 日记写入时刻)
function fmtClock(ts: any): string {
  const n = Number(ts)
  if (!n) return '—'
  const d = new Date(n)
  const p = (x: number) => String(x).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}`
}

// 当天 mood 曲线(canvas 不解析 CSS 变量,暖色线用字面色值,与 --warm 同源)
const curve = computed<any[]>(() => (detail.value?.mood_curve as any[]) || [])
const lineData = computed(() => ({
  labels: curve.value.map((p) => fmtClock(p.ts)),
  datasets: [{ label: 'mood', borderColor: '#f2a3b3', backgroundColor: 'rgba(242,163,179,0.15)',
               data: curve.value.map((p) => p.value), tension: 0.3 }],
}))
const lineOptions = { responsive: true, scales: { x: darkChartScales.x, y: { ...darkChartScales.y, min: 0, max: 1 } }, plugins: { legend: { display: false } } }

// 顶栏刷新:列表 + 详情全量重载
async function loadAll() {
  await loadList()
  if (selectedDate.value) await select(selectedDate.value)
}

watch(reloadTick, () => loadAll())
onMounted(async () => {
  await ensureOid()
  await loadAll()
})
</script>

<template>
  <div class="m-diary">
    <!-- 顶栏:标题 + 新增手写 + 刷新 -->
    <div class="m-topbar">
      <span class="m-title">日记</span>
      <div class="m-top-actions">
        <n-button size="small" quaternary @click="showCreate = true; createDate = todayStr()">新增</n-button>
        <n-button size="small" quaternary :loading="loadingList || loadingDetail" @click="loadAll">刷新</n-button>
      </div>
    </div>

    <!-- 立即补做(做梦)+ 写日常日记;LLM 生成耗时,oid 未绑定真实会话时禁用 -->
    <div class="m-actions">
      <n-popconfirm @positive-click="runToday">
        <template #trigger>
          <n-button type="primary" size="large" :disabled="running || !oidReady" :loading="running" style="flex: 1">
            立即补做
          </n-button>
        </template>
        给今天手动生成一次梦与日记？
      </n-popconfirm>
      <n-popconfirm @positive-click="runJournalToday">
        <template #trigger>
          <n-button size="large" :disabled="journaling || !oidReady" :loading="journaling" style="flex: 1">
            写日常日记
          </n-button>
        </template>
        让她总结今天的聊天写一篇日常日记？
      </n-popconfirm>
    </div>

    <!-- 空态:一天日记都没有 -->
    <div v-if="!entries.length && !loadingList" class="empty-state">
      <span class="empty-icon">🌙</span>
      <span>还没有日记。要么她还没做过梦，要么你还没开启 dream 插件（面板 → 插件 → 做梦与日记）</span>
    </div>

    <template v-else>
      <!-- 日期横向滚动 chip 行(当前项暖色高亮;带 kind 短标签) -->
      <div class="date-strip">
        <span v-for="e in entries" :key="e.date"
              class="chip date-chip" :class="{ 'chip-warm': e.date === selectedDate }"
              @click="select(e.date); editing = false">
          {{ e.date.slice(5) }}·{{ kindLabel(kindOf(e)) }}
        </span>
      </div>

      <!-- 详情:梦 / 日记 / 曲线 三卡堆叠(编辑态替换为表单) -->
      <n-spin :show="loadingDetail">
        <div v-if="notFound" class="empty-state">
          <span class="empty-icon">🌙</span>
          <span>这一天的日记不存在</span>
        </div>
        <!-- 编辑态表单(diary 必填/dream 选填/key_events 顿号分隔) -->
        <div v-else-if="editing && detail" class="cards">
          <div class="card">
            <div class="card-head">
              <span class="section-title">编辑 {{ selectedDate }}（{{ kindLabel(kindOf(detail)) }}）</span>
            </div>
            <label class="field-label">日记正文</label>
            <textarea v-model="editDiary" class="edit-area" rows="7"></textarea>
            <label v-if="detail.dream !== undefined" class="field-label">她的梦（可留空）</label>
            <textarea v-if="detail.dream !== undefined" v-model="editDream" class="edit-area" rows="3"></textarea>
            <label class="field-label">关键事件（顿号或逗号分隔）</label>
            <input v-model="editEvents" class="edit-input" />
            <div class="edit-actions">
              <n-button type="primary" :loading="saving" @click="saveEdit">保存</n-button>
              <n-button quaternary @click="editing = false">取消</n-button>
            </div>
          </div>
        </div>
        <div v-else-if="detail" class="cards">
          <!-- 工具条:编辑 / 重提炼 / 删除 -->
          <div class="detail-toolbar">
            <n-button size="tiny" @click="startEdit">编辑</n-button>
            <n-popconfirm @positive-click="regenMemory">
              <template #trigger>
                <n-button size="tiny" :loading="regening">重新提炼记忆</n-button>
              </template>
              从这篇日记重新提炼事件记忆？
            </n-popconfirm>
            <n-popconfirm @positive-click="removeDiary">
              <template #trigger>
                <n-button size="tiny" type="error" ghost :loading="deleting">删除</n-button>
              </template>
              删除 {{ selectedDate }} 的日记？事件记忆一并清理，不可恢复。
            </n-popconfirm>
          </div>
          <!-- 梦境卡(journal/manual 无 dream 字段不渲染) -->
          <div v-if="detail.dream !== undefined" class="card">
            <div class="card-head">
              <span class="section-title">她的梦</span>
              <span class="chip" :class="toneClass(detail.dream_tone || 'neutral')">
                {{ toneLabel(detail.dream_tone || 'neutral') }}
              </span>
            </div>
            <p class="prose">{{ detail.dream || '（这一夜没有梦）' }}</p>
          </div>

          <!-- 日记卡(正文 + kind 标签 + key_events 换行 chip 排) -->
          <div class="card">
            <div class="card-head">
              <span class="section-title">她的日记</span>
              <span class="chip">{{ kindLabel(kindOf(detail)) }}</span>
              <span v-if="detail.created_ts" class="write-at">写于 {{ fmtClock(detail.created_ts) }}</span>
            </div>
            <p class="prose">{{ detail.diary || '（这一天没有落笔）' }}</p>
            <div v-if="detail.key_events && detail.key_events.length" class="events">
              <span v-for="(k, i) in detail.key_events" :key="i" class="chip">{{ k }}</span>
            </div>
          </div>

          <!-- 当天心情曲线卡 -->
          <div class="card">
            <div class="card-head"><span class="section-title">当天心情</span></div>
            <Line v-if="curve.length" :data="lineData" :options="lineOptions" />
            <n-empty v-else size="small" description="当天无心情记录" />
          </div>
        </div>
      </n-spin>

      <!-- 手写新增遮罩 -->
      <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
        <div class="modal-card">
          <div class="card-head"><span class="section-title">新增一篇日记（手写）</span></div>
          <label class="field-label">日期</label>
          <input v-model="createDate" type="date" class="edit-input" />
          <label class="field-label">日记正文</label>
          <textarea v-model="createText" class="edit-area" rows="8" placeholder="这一天……"></textarea>
          <div class="edit-actions">
            <n-button type="primary" :loading="creating" @click="submitCreate">保存</n-button>
            <n-button quaternary @click="showCreate = false">取消</n-button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.m-diary {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.m-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.m-title {
  font-weight: 600;
  font-size: 16px;
}
/* 日期 chip 横向滚动条(一行装不下全部日期) */
.date-strip {
  display: flex;
  gap: var(--sp-2);
  overflow-x: auto;
  padding-bottom: 2px;
  flex-shrink: 0;
}
.date-chip {
  cursor: pointer;
  flex-shrink: 0;
  user-select: none;
}
.cards {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
}
/* 卡内首行小节标题去掉 tokens 默认的上边距 */
.card-head .section-title {
  margin-top: 0;
}
/* 梦/日记正文:保留换行、舒适行高 */
.prose {
  margin: var(--sp-2) 0 0;
  color: var(--text);
  font-size: var(--f-md);
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
.write-at {
  font-size: var(--f-xs);
  color: var(--text-faint);
}
.events {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
  margin-top: var(--sp-3);
}
/* 顶栏按钮组与动作行(2026-11-01 管理批次) */
.m-top-actions {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
.m-actions {
  display: flex;
  gap: var(--sp-2);
}
/* 详情工具条(编辑/重提炼/删除) */
.detail-toolbar {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex-wrap: wrap;
}
/* 编辑态表单与手写遮罩(与 PC 同源) */
.field-label {
  display: block;
  margin: var(--sp-2) 0 4px;
  font-size: var(--f-xs);
  color: var(--text-dim);
}
.edit-area,
.edit-input {
  width: 100%;
  box-sizing: border-box;
  background: var(--dim, rgba(255, 255, 255, 0.04));
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  color: var(--text);
  font-size: 15px;
  font-family: inherit;
  line-height: 1.6;
}
.edit-area {
  resize: vertical;
}
.edit-actions {
  display: flex;
  gap: var(--sp-2);
  margin-top: var(--sp-3);
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
  padding: 16px;
}
.modal-card {
  width: min(480px, 100%);
  background: var(--bg-card, #1e1e24);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: var(--sp-4);
  max-height: 80vh;
  overflow: auto;
}
</style>
