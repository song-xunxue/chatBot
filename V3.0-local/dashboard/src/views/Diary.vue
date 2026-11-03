<script setup lang="ts">
/**
 * 日记页(桌面,2026-10-26 dream 插件出品:她睡着以后的梦境与日记):
 * 左栏日期列表(kind 标签 + tone 标签 + 摘要,激活行暖色竖条)+ 右栏详情三卡
 * (她的梦 / 她的日记 + key_events / 当天心情曲线,暖色调);
 * 页头"立即补做"/"写日常日记"手动生成 + "新增日记"手写(kind=manual)。
 * 2026-11-01 日记管理批次:列表 kind 标签(dream梦/journal日常/manual手写)、
 * 行内删除、详情编辑(编辑态表单)、重提炼记忆按钮。
 * 列表/详情不依赖 oid;404 显示空态而非报错。
 * 日期: 2026-10-26

2026-11-01
变更说明:
  1. 日记管理:kind 标签/删除/编辑(白名单字段表单)/手写新增/写日常日记按钮/重提炼记忆
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
const { oid, reloadTick } = useObject()   // 全局共享 object_id(补做传参) + 头部回车刷新信号
// oid 就绪守卫(与 DiaryMobile 对齐):default 占位会话不做梦,后端同口径 400
const oidReady = computed(() => !!oid.value && oid.value !== 'default')

// tone → 文案/配色映射(positive 暖色甜梦 / negative 红色噩梦 / neutral 灰色平静)
function toneLabel(t: string): string {
  return t === 'positive' ? '甜梦' : t === 'negative' ? '噩梦' : '平静'
}
function toneClass(t: string): string {
  return t === 'positive' ? 'chip-warm' : t === 'negative' ? 'chip-danger' : ''
}

// kind → 文案/配色(2026-11-01:dream 梦 / journal 日常日记 / manual 手写;存量无 kind 视为 dream)
function kindOf(e: any): string {
  return (e?.kind || 'dream') as string
}
function kindLabel(k: string): string {
  return k === 'journal' ? '日常' : k === 'manual' ? '手写' : '梦'
}
function kindClass(k: string): string {
  return k === 'journal' ? 'chip-info' : k === 'manual' ? 'chip-plain' : 'chip-warm'
}

// —— 左栏:日期列表(倒序,最近 30 天)——
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

// —— 删除单日(2026-11-01):行内小按钮,NPopconfirm 二次确认,后端连记忆一起删 ——
const deleting = ref(false)
async function removeDiary(date: string) {
  deleting.value = true
  try {
    await deleteDiary(date)
    message.success(`已删除 ${date} 的日记(对应事件记忆一并清理)`)
    if (selectedDate.value === date) { selectedDate.value = ''; detail.value = null }
    await loadList()
  } catch (e: any) { message.error('删除失败:' + e) }
  finally { deleting.value = false }
}

// —— 右栏:单日详情 ——
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
    // 404(详情被删/日期越界)不算错误,右栏空态提示;其余弹错
    if (e?.response?.status === 404) notFound.value = true
    else message.error('' + e)
  } finally { loadingDetail.value = false }
}

// 右栏空态文案:列表有货但未选中 → 引导;完全没日记 → 提示开 dream 插件
const emptyText = computed(() => entries.value.length
  ? '点左侧日期，查看那天的梦与日记'
  : '还没有日记。要么她还没做过梦，要么你还没开启 dream 插件（面板 → 插件 → 做梦与日记）')

// —— 立即补做(给今天手动跑一次 dream,LLM 生成耗时较长)——
const running = ref(false)
async function runToday() {
  if (!oidReady.value) {
    message.error('先在头部选择真实 QQ 会话再补做(default 占位会话不做梦)')
    return
  }
  running.value = true
  try {
    const entry = await runDiary({ object_id: oid.value, kind: 'dream' })
    message.success(`已生成 ${entry?.date || ''} 的梦与日记`)
    await loadList()
    if (entry?.date) await select(entry.date)   // 刷新后选中新写的一天
  } catch {
    message.error('生成失败(无素材或 LLM 不可用)')
  } finally { running.value = false }
}

// —— 写日常日记(2026-11-01:kind=journal,总结今天而不是做梦)——
const journaling = ref(false)
async function runJournalToday() {
  if (!oidReady.value) {
    message.error('先在头部选择真实 QQ 会话再写日常日记')
    return
  }
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

// —— 编辑模式(2026-11-01):详情卡变表单,保存走 PUT(默认重提炼记忆)——
const editing = ref(false)
const saving = ref(false)
const editDiary = ref('')
const editDream = ref('')
const editEvents = ref('')   // key_events 逗号分隔
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
    const body: Record<string, any> = { diary: editDiary.value.trim(), regen_memory: true }
    if (editDream.value.trim() || detail.value?.dream) body.dream = editDream.value.trim()
    body.key_events = events
    const entry = await updateDiary(selectedDate.value, body)
    detail.value = entry
    editing.value = false
    message.success('已保存(事件记忆已同步重提炼)')
    await loadList()
  } catch (e: any) { message.error('保存失败:' + e) }
  finally { saving.value = false }
}

// —— 重提炼记忆(2026-11-01):编辑漏勾/想重跑时的兜底按钮 ——
const regening = ref(false)
async function regenMemory() {
  regening.value = true
  try {
    await regenDiaryMemory(selectedDate.value)
    message.success('已从这篇日记重新提炼事件记忆')
  } catch (e: any) { message.error('重提炼失败:' + e) }
  finally { regening.value = false }
}

// —— 手写新增(2026-11-01:kind=manual,同日期已有会覆盖)——
const showCreate = ref(false)
const creating = ref(false)
const createDate = ref('')
const createText = ref('')
async function submitCreate() {
  if (!createDate.value) { message.error('先选日期'); return }
  if (!createText.value.trim()) { message.error('日记正文不能为空'); return }
  creating.value = true
  try {
    const r = await createDiary({ date: createDate.value, diary: createText.value.trim() })
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

// 今天 → YYYY-MM-DD(新增日记的日期默认值)
function todayStr(): string {
  const d = new Date()
  const p = (x: number) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

// 当天 mood 曲线(canvas 不解析 CSS 变量,暖色线用字面色值,与 --warm 同源)
const curve = computed<any[]>(() => (detail.value?.mood_curve as any[]) || [])
const lineData = computed(() => ({
  labels: curve.value.map((p) => fmtClock(p.ts)),
  datasets: [{ label: 'mood', borderColor: '#f2a3b3', backgroundColor: 'rgba(242,163,179,0.15)',
               data: curve.value.map((p) => p.value), tension: 0.3 }],
}))
const lineOptions = { responsive: true, scales: { x: darkChartScales.x, y: { ...darkChartScales.y, min: 0, max: 1 } }, plugins: { legend: { display: false } } }

watch(reloadTick, () => loadList())   // 头部 OID 回车 → 重载列表
onMounted(loadList)
</script>

<template>
  <div class="diary-page">
    <!-- 页头:标题 + 说明 + 右侧按钮组(补做梦/写日常日记/新增手写,生成中置灰防重复) -->
    <div class="page-header page-header-center">
      <div>
        <h1 class="page-title">日记</h1>
        <div class="page-subtitle">她睡着以后，会做梦，也会写日记</div>
      </div>
      <div class="header-actions">
        <n-popconfirm @positive-click="runToday">
          <template #trigger>
            <button class="btn btn-primary" :disabled="running || !oidReady">{{ running ? '生成中…' : '立即补做' }}</button>
          </template>
          给今天手动生成一次梦与日记？（需当天有对话素材且 LLM 可用）
        </n-popconfirm>
        <n-popconfirm @positive-click="runJournalToday">
          <template #trigger>
            <button class="btn" :disabled="journaling || !oidReady">{{ journaling ? '写日记中…' : '写日常日记' }}</button>
          </template>
          让她总结今天的聊天写一篇日常日记？（每晚 {{ '' }}22 点后她也会自己写）
        </n-popconfirm>
        <button class="btn" @click="showCreate = true; createDate = todayStr()">新增日记</button>
      </div>
    </div>

    <div class="diary-body">
      <!-- 左栏:日期列表(激活行暖色竖条点缀;kind+tone 双标签;行内删除) -->
      <div class="diary-side">
        <div class="side-head">
          <span>最近的日记（{{ entries.length }}）</span>
          <n-button size="tiny" quaternary :loading="loadingList" @click="loadList">刷新</n-button>
        </div>
        <n-empty v-if="!entries.length && !loadingList" size="small" description="还没有日记" />
        <div v-for="e in entries" :key="e.date"
             class="list-row diary-row" :class="{ active: e.date === selectedDate }"
             @click="select(e.date); editing = false">
          <div class="row-main">
            <div class="row-top">
              <span class="row-date">{{ e.date }}</span>
              <span class="row-chips">
                <span class="chip" :class="kindClass(kindOf(e))">{{ kindLabel(kindOf(e)) }}</span>
                <span v-if="kindOf(e) === 'dream'" class="chip" :class="toneClass(e.tone)">{{ toneLabel(e.tone) }}</span>
                <n-popconfirm @positive-click="removeDiary(e.date)">
                  <template #trigger>
                    <button class="row-del" title="删除这一天的日记" @click.stop>✕</button>
                  </template>
                  删除 {{ e.date }} 的日记？对应的事件记忆会一并清理，不可恢复。
                </n-popconfirm>
              </span>
            </div>
            <div v-if="e.excerpt" class="row-excerpt">{{ e.excerpt }}</div>
          </div>
        </div>
      </div>

      <!-- 右栏:详情三卡(编辑态替换为表单) -->
      <div class="diary-main">
        <n-spin :show="loadingDetail">
          <div v-if="notFound" class="empty-state">
            <span class="empty-icon">🌙</span>
            <span>这一天的日记不存在</span>
          </div>
          <div v-else-if="!detail" class="empty-state">
            <span class="empty-icon">🌙</span>
            <span>{{ emptyText }}</span>
          </div>
          <!-- 编辑态:白名单字段表单(diary 必填/dream 选填/key_events 顿号分隔) -->
          <div v-else-if="editing" class="detail-cards">
            <div class="card">
              <div class="card-head">
                <span class="section-title">编辑 {{ selectedDate }}（{{ kindLabel(kindOf(detail)) }}）</span>
                <span class="write-at">保存后自动重新提炼事件记忆</span>
              </div>
              <label class="field-label">日记正文</label>
              <textarea v-model="editDiary" class="edit-area" rows="7" placeholder="日记正文（不能为空）"></textarea>
              <label class="field-label">她的梦（仅梦日记有，可留空）</label>
              <textarea v-model="editDream" class="edit-area" rows="3" placeholder="梦境内容（可留空）"></textarea>
              <label class="field-label">关键事件（用顿号或逗号分隔）</label>
              <input v-model="editEvents" class="edit-input" placeholder="事件一、事件二" />
              <div class="edit-actions">
                <button class="btn btn-primary" :disabled="saving" @click="saveEdit">{{ saving ? '保存中…' : '保存' }}</button>
                <button class="btn" @click="editing = false">取消</button>
              </div>
            </div>
          </div>
          <div v-else class="detail-cards">
            <!-- 工具条:编辑 + 重提炼记忆 -->
            <div class="detail-toolbar">
              <button class="btn btn-sm" @click="startEdit">编辑</button>
              <n-popconfirm @positive-click="regenMemory">
                <template #trigger>
                  <button class="btn btn-sm" :disabled="regening">{{ regening ? '提炼中…' : '重新提炼记忆' }}</button>
                </template>
                从这篇日记重新提炼事件记忆？（先清掉该日旧记忆再写入）
              </n-popconfirm>
              <span class="write-at">编辑与删除都在左侧列表行操作</span>
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

            <!-- 日记卡(正文 + key_events 一排 chip) -->
            <div class="card">
              <div class="card-head">
                <span class="section-title">她的日记</span>
                <span class="chip" :class="kindClass(kindOf(detail))">{{ kindLabel(kindOf(detail)) }}</span>
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
      </div>
    </div>

    <!-- 手写新增遮罩:日期+正文(同日期已有会覆盖,提交后提示) -->
    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <div class="modal-card">
        <div class="card-head">
          <span class="section-title">新增一篇日记（手写）</span>
        </div>
        <label class="field-label">日期</label>
        <input v-model="createDate" type="date" class="edit-input" />
        <label class="field-label">日记正文（以她的口吻写也可以）</label>
        <textarea v-model="createText" class="edit-area" rows="8" placeholder="这一天……"></textarea>
        <div class="edit-actions">
          <button class="btn btn-primary" :disabled="creating" @click="submitCreate">{{ creating ? '保存中…' : '保存' }}</button>
          <button class="btn" @click="showCreate = false">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 整页占满内容区(顶栏 52 + 上下 padding 20*2,同 History.vue 的 calc 口径) */
.diary-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 92px);
}
/* tokens 的 page-header 按 baseline 对齐,本页右侧是按钮需垂直居中 */
.page-header-center {
  align-items: center;
  flex-shrink: 0;
}
.diary-body {
  flex: 1;
  min-height: 0;
  display: flex;
}
/* 左栏:固定宽日期列表 */
.diary-side {
  width: 230px;
  flex-shrink: 0;
  overflow: auto;
  padding: 8px;
  border-right: 1px solid var(--border);
}
.side-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}
/* 日期行(复用 tokens 的 .list-row;激活态换暖色系 + 左侧 2px 暖色竖条) */
.diary-row {
  cursor: pointer;
  flex-direction: column;
  align-items: stretch;
  position: relative;
  padding-left: 14px;
}
.diary-row.active {
  background: var(--warm-dim);
  border-color: rgba(242, 163, 179, 0.3);
}
.diary-row.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 2px;
  border-radius: 1px;
  background: var(--warm);
}
.row-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.row-date {
  font-size: 13px;
  font-weight: 600;
}
.diary-row.active .row-date {
  color: var(--warm);
}
.row-excerpt {
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* 右栏:详情滚动区 */
.diary-main {
  flex: 1;
  min-width: 0;
  overflow: auto;
  padding-left: 16px;
}
.detail-cards {
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
/* 页头按钮组(2026-11-01:补做梦/写日常日记/新增手写三个入口) */
.header-actions {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
/* 列表行 kind+tone 标签组与行内删除按钮 */
.row-chips {
  display: flex;
  align-items: center;
  gap: 4px;
}
.chip-info {
  background: rgba(96, 165, 250, 0.15);
  color: #93c5fd;
}
.chip-plain {
  background: var(--dim);
  color: var(--text-dim);
}
.row-del {
  border: none;
  background: transparent;
  color: var(--text-faint);
  font-size: 11px;
  line-height: 1;
  padding: 2px 4px;
  border-radius: 4px;
  cursor: pointer;
}
.row-del:hover {
  color: var(--danger, #f87171);
  background: rgba(248, 113, 113, 0.12);
}
/* 详情工具条(编辑/重提炼) */
.detail-toolbar {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
.btn-sm {
  padding: 4px 12px;
  font-size: var(--f-sm);
}
/* 编辑态表单(手写新增遮罩共用) */
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
  font-size: var(--f-md);
  font-family: inherit;
  line-height: 1.6;
}
.edit-area {
  resize: vertical;
}
.edit-area:focus,
.edit-input:focus {
  outline: none;
  border-color: var(--warm);
}
.edit-actions {
  display: flex;
  gap: var(--sp-2);
  margin-top: var(--sp-3);
}
/* 手写新增遮罩 */
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.modal-card {
  width: min(520px, 90vw);
  background: var(--bg-card, #1e1e24);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: var(--sp-4);
  max-height: 80vh;
  overflow: auto;
}
</style>
