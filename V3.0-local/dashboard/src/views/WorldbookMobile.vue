<script setup lang="ts">
/**
 * 移动端世界书页(功能对等 PC Worldbook.vue,窄屏重排,2026-10-26):
 * 顶栏(标题 + 新建/刷新) → 统计横滚 chip(总数/常驻/今日注入/平均 token)
 * → 来源+状态过滤 chip 横滚 → 条目卡片列表(标题/来源/mode/keys/命中/上次命中/启停 switch,
 * 点卡片开编辑弹窗;触摸目标≥44px) → 新建/编辑共用弹窗(94vw,内容限高可滚动,
 * 编辑附只读来源/命中/ref) → 弹窗内物理删除(n-popconfirm)。「重建自动条目」按钮
 * 放顶栏下方(popconfirm 二次确认 + disabled 防重复)。
 * 数据与 API 同 PC;全局维度不依赖 oid。
 * 日期: 2026-10-26
 *
 * 变更说明:
 *   1. 新建页面:对接 /api/v1/worldbook/* 六个端点(entries CRUD + stats + rebuild)
 */
import { ref, computed, watch, onMounted } from 'vue'
import {
  NButton, NEmpty, NInput, NInputNumber, NSelect, NSlider, NSwitch,
  NRadio, NRadioGroup, NDynamicTags, NModal, NPopconfirm, NSpin, useMessage,
} from 'naive-ui'
import {
  getWorldbookEntries, createWorldbookEntry, updateWorldbookEntry,
  deleteWorldbookEntry, getWorldbookStats, rebuildWorldbook,
} from '@/api'
import { useObject } from '@/composables/useObject'

const message = useMessage()
const { reloadTick } = useObject()   // 头部刷新信号(本页不依赖 oid)

// —— 条目类型(后端契约字段,同 PC)——
interface WbEntry {
  id: string
  title: string
  content: string
  keys: string[]
  key_regex?: string
  secondary_keys?: string[]
  mode: 'trigger' | 'always'
  order: number
  position: string
  probability: number
  cooldown_minutes: number
  token_estimate: number
  enabled: boolean
  source: string
  source_ref?: string
  weight: number
  hits: number
  last_hit_at: number      // 毫秒,0=从未命中
  last_injected_at: number
  created_ts: number
  updated_ts: number
}

// —— 来源/状态过滤选项(空串=不过滤)——
const SOURCE_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'manual', label: '手动' },
  { value: 'memory', label: '记忆' },
  { value: 'summary', label: '摘要' },
  { value: 'diary', label: '日记' },
  { value: 'dream', label: '梦境' },
  { value: 'roleplay', label: '扮演' },
]
const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'yes', label: '启用' },
  { value: 'no', label: '停用' },
]
const SOURCE_LABELS: Record<string, string> = {
  manual: '手动', memory: '记忆', summary: '摘要', diary: '日记', dream: '梦境', roleplay: '扮演',
}
function sourceLabel(s: string): string { return SOURCE_LABELS[s] || s }
function sourceClass(s: string): string {
  return s === 'manual' ? 'chip-accent' : (s === 'diary' || s === 'dream') ? 'chip-warm' : ''
}

// 注入位置五个锚点(同 PC)
const POSITION_OPTIONS = [
  { label: '人设之前', value: 'before_persona' },
  { label: '人设之后', value: 'after_persona' },
  { label: '记忆之前', value: 'before_memories' },
  { label: '记忆之后', value: 'after_memories' },
  { label: '提示词末尾', value: 'tail' },
]

// 毫秒时间戳 → 相对时间(0=从未;不足一分钟=刚刚)
function relTime(ts: number): string {
  const n = Number(ts)
  if (!n) return '从未'
  const diff = Date.now() - n
  if (diff < 60000) return '刚刚'
  const m = Math.floor(diff / 60000)
  if (m < 60) return `${m} 分钟前`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} 小时前`
  const d = Math.floor(h / 24)
  if (d < 30) return `${d} 天前`
  const mo = Math.floor(d / 30)
  if (mo < 12) return `${mo} 个月前`
  return `${Math.floor(mo / 12)} 年前`
}

// —— 统计 + 列表加载 ——
const stats = ref<any>({})
const entries = ref<WbEntry[]>([])
const loading = ref(false)
const sourceFilter = ref('')
const statusFilter = ref('')   // ''|'yes'|'no' → enabled 布尔

async function loadStats() {
  try { stats.value = await getWorldbookStats() }
  catch (e: any) { message.error('统计加载失败: ' + e) }
}
async function loadEntries() {
  loading.value = true
  try {
    const params: { source?: string; enabled?: boolean; limit: number } = { limit: 300 }
    if (sourceFilter.value) params.source = sourceFilter.value
    if (statusFilter.value === 'yes') params.enabled = true
    else if (statusFilter.value === 'no') params.enabled = false
    const r = await getWorldbookEntries(params)
    entries.value = (r && r.items) || []
  } catch (e: any) { message.error('条目加载失败: ' + e) }
  finally { loading.value = false }
}
async function loadAll() {
  await Promise.all([loadStats(), loadEntries()])
}
watch([sourceFilter, statusFilter], () => loadEntries())
watch(reloadTick, () => loadAll())
onMounted(loadAll)

const avgTokens = computed(() => Math.round(Number(stats.value.avg_tokens || 0)))

// —— 行内启停开关(即时生效:PUT enabled,本地翻转不全量刷新)——
async function toggleEnabled(e: WbEntry) {
  try {
    await updateWorldbookEntry(e.id, { enabled: !e.enabled })
    e.enabled = !e.enabled
    message.success(e.enabled ? `已启用「${e.title}」` : `已停用「${e.title}」`)
    loadStats()
  } catch (err: any) { message.error('启停失败: ' + err) }
}

// —— 重建自动条目(1-3s;popconfirm 二次确认 + disabled 防重复)——
const rebuilding = ref(false)
async function rebuild() {
  rebuilding.value = true
  try {
    const r = await rebuildWorldbook({})
    message.success(`重建完成:新增 ${r?.created ?? 0} 条,停用 ${r?.disabled ?? 0} 条`)
    await loadAll()
  } catch (e: any) { message.error('重建失败: ' + e) }
  finally { rebuilding.value = false }
}

// —— 新建/编辑共用弹窗(editing=null 为新建;字段与 PC 完全一致)——
const showForm = ref(false)
const editing = ref<WbEntry | null>(null)
const fTitle = ref('')
const fContent = ref('')
const fKeys = ref<string[]>([])
const fSecondary = ref<string[]>([])
const fMode = ref<'trigger' | 'always'>('trigger')
const fPosition = ref('after_memories')
const fOrder = ref(100)
const fProbability = ref(1)
const fCooldown = ref(0)
const saving = ref(false)
const deleting = ref(false)

function openCreate() {
  editing.value = null
  fTitle.value = ''; fContent.value = ''
  fKeys.value = []; fSecondary.value = []
  fMode.value = 'trigger'; fPosition.value = 'after_memories'
  fOrder.value = 100; fProbability.value = 1; fCooldown.value = 0
  showForm.value = true
}
function openEdit(e: WbEntry) {
  editing.value = e
  fTitle.value = e.title || ''
  fContent.value = e.content || ''
  fKeys.value = Array.isArray(e.keys) ? e.keys : []
  fSecondary.value = Array.isArray(e.secondary_keys) ? e.secondary_keys : []
  fMode.value = e.mode === 'always' ? 'always' : 'trigger'
  fPosition.value = e.position || 'after_memories'
  fOrder.value = Number(e.order ?? 100)
  fProbability.value = Number(e.probability ?? 1)
  fCooldown.value = Number(e.cooldown_minutes ?? 0)
  showForm.value = true
}
async function applyForm() {
  if (!fTitle.value.trim() || !fContent.value.trim()) {
    message.warning('标题与内容不能为空'); return
  }
  saving.value = true
  try {
    const body = {
      title: fTitle.value.trim(),
      content: fContent.value.trim(),
      keys: fKeys.value,
      secondary_keys: fSecondary.value,
      mode: fMode.value,
      position: fPosition.value,
      order: fOrder.value ?? 0,
      probability: Number(fProbability.value ?? 1),
      cooldown_minutes: fCooldown.value ?? 0,
    }
    if (editing.value) {
      await updateWorldbookEntry(editing.value.id, body)
      message.success('已保存')
    } else {
      await createWorldbookEntry(body)
      message.success('已新建设定')
    }
    showForm.value = false
    await loadAll()
  } catch (e: any) { message.error('保存失败: ' + e) }
  finally { saving.value = false }
}
async function removeEntry() {
  if (!editing.value) return
  deleting.value = true
  try {
    await deleteWorldbookEntry(editing.value.id)
    message.success('已删除')
    showForm.value = false
    await loadAll()
  } catch (e: any) { message.error('删除失败: ' + e) }
  finally { deleting.value = false }
}
</script>

<template>
  <div class="m-wb">
    <!-- 顶栏:标题 + 新建/刷新(touch≥44px 用 size=large) -->
    <div class="m-topbar">
      <span class="m-title">世界书</span>
      <div class="m-topbar-actions">
        <n-button size="large" type="primary" ghost @click="openCreate">新建</n-button>
        <n-button size="large" quaternary :loading="loading" @click="loadAll">刷新</n-button>
      </div>
    </div>

    <!-- 重建自动条目(二次确认 + 防重复) -->
    <n-popconfirm @positive-click="rebuild">
      <template #trigger>
        <n-button size="large" block :disabled="rebuilding" :loading="rebuilding">重建自动条目</n-button>
      </template>
      从现有记忆/日记重建自动条目？可能需要 1-3 秒
    </n-popconfirm>

    <!-- 统计横滚 chip 行 -->
    <div class="stat-strip">
      <span class="chip">共 {{ stats.total ?? 0 }} 条</span>
      <span class="chip chip-warm">常驻 {{ stats.always ?? 0 }}</span>
      <span class="chip">今日注入 {{ stats.today_injections ?? 0 }}</span>
      <span class="chip">平均 {{ avgTokens }} token</span>
    </div>

    <!-- 过滤 chip 横滚:来源 + 状态 -->
    <div class="filter-strip">
      <span v-for="o in SOURCE_OPTIONS" :key="'s-' + o.value"
            class="chip f-chip" :class="{ 'chip-accent': sourceFilter === o.value }"
            @click="sourceFilter = o.value">{{ o.label }}</span>
      <span class="strip-sep"></span>
      <span v-for="o in STATUS_OPTIONS" :key="'e-' + o.value"
            class="chip f-chip" :class="{ 'chip-accent': statusFilter === o.value }"
            @click="statusFilter = o.value">{{ o.label }}</span>
    </div>

    <!-- 条目卡片列表(点卡片开编辑;switch 拦截冒泡) -->
    <n-spin :show="loading">
      <div v-if="!entries.length && !loading" class="empty-state">
        <span class="empty-icon">📖</span>
        <span>还没有世界书条目。点「新建」手写一条，或「重建自动条目」从记忆/日记生成</span>
      </div>
      <div v-for="e in entries" :key="e.id" class="card wb-card" :class="{ 'card-off': !e.enabled }" @click="openEdit(e)">
        <div class="wb-card-top">
          <span class="wb-title">{{ e.title }}</span>
          <!-- 启停开关:拦截冒泡,避免点开关误开编辑弹窗 -->
          <span class="switch-cell" @click.stop>
            <n-switch :value="!!e.enabled" @update:value="() => toggleEnabled(e)" />
          </span>
        </div>
        <div class="wb-chips">
          <span class="chip" :class="sourceClass(e.source)">{{ sourceLabel(e.source) }}</span>
          <span class="chip" :class="e.mode === 'always' ? 'chip-warm' : ''">
            {{ e.mode === 'always' ? '常驻' : '触发' }}
          </span>
          <span v-for="k in (e.keys || []).slice(0, 3)" :key="k" class="chip key-chip">{{ k }}</span>
          <span v-if="(e.keys || []).length > 3" class="chip">+{{ e.keys.length - 3 }}</span>
        </div>
        <div class="wb-meta">命中 {{ e.hits }} 次 · 上次 {{ relTime(e.last_hit_at) }}</div>
      </div>
    </n-spin>

    <!-- 新建/编辑共用弹窗(94vw;内容限高 72vh 可滚动;控件 size=large 保触摸目标) -->
    <n-modal v-model:show="showForm" preset="card" :title="editing ? '编辑条目' : '新建设定'"
             style="width:94vw;max-width:560px">
      <div class="m-modal-body">
        <div class="field">
          <div class="m-label">标题</div>
          <n-input v-model:value="fTitle" size="large" placeholder="条目名，如「她的故乡」「宠物猫团子」" />
        </div>
        <div class="field">
          <div class="m-label">内容（1-3 句，注入提示词的设定文本）</div>
          <n-input v-model:value="fContent" type="textarea" size="large" :autosize="{ minRows: 3, maxRows: 6 }"
                   placeholder="用 1-3 句话写下这条设定。如：她养了一只叫团子的白猫，提到猫时她会很开心。" />
        </div>
        <div class="field">
          <div class="m-label">主关键词（命中任一即触发）</div>
          <n-dynamic-tags v-model:value="fKeys" />
        </div>
        <div class="field">
          <div class="m-label">次要关键词（与主关键词同时命中增强召回，可选）</div>
          <n-dynamic-tags v-model:value="fSecondary" />
        </div>
        <div class="field">
          <div class="m-label">触发方式</div>
          <n-radio-group v-model:value="fMode">
            <n-radio value="trigger">触发（命中关键词才注入）</n-radio>
            <n-radio value="always">常驻（每轮都注入）</n-radio>
          </n-radio-group>
        </div>
        <div class="field">
          <div class="m-label">注入位置</div>
          <n-select v-model:value="fPosition" :options="POSITION_OPTIONS" size="large" />
        </div>
        <div class="field">
          <div class="m-label">顺序（order，小者先注入）</div>
          <n-input-number v-model:value="fOrder" :min="0" :step="10" size="large" style="width:100%" />
        </div>
        <div class="field">
          <div class="m-label">冷却（分钟，0=不冷却）</div>
          <n-input-number v-model:value="fCooldown" :min="0" :step="5" size="large" style="width:100%" />
        </div>
        <div class="field">
          <div class="m-label">注入概率：{{ Number(fProbability ?? 0).toFixed(2) }}</div>
          <n-slider v-model:value="fProbability" :min="0" :max="1" :step="0.05" />
        </div>
        <!-- 编辑态只读信息:来源 / 命中 / 参照 / token 估算 -->
        <div v-if="editing" class="ro-info">
          <span class="chip" :class="sourceClass(editing.source)">来源:{{ sourceLabel(editing.source) }}</span>
          <span class="chip">命中 {{ editing.hits }} 次</span>
          <span class="chip">约 {{ editing.token_estimate }} token</span>
          <span v-if="editing.source_ref" class="chip">ref:{{ editing.source_ref }}</span>
        </div>
        <n-popconfirm v-if="editing" @positive-click="removeEntry">
          <template #trigger>
            <n-button size="large" block type="error" ghost :disabled="deleting">删除该条目</n-button>
          </template>
          物理删除该条目，不可恢复？
        </n-popconfirm>
        <div class="m-actions">
          <n-button size="large" quaternary style="flex:1" @click="showForm = false">取消</n-button>
          <n-button size="large" type="primary" style="flex:1" :loading="saving" @click="applyForm">保存</n-button>
        </div>
      </div>
    </n-modal>
  </div>
</template>

<style scoped>
.m-wb {
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
.m-topbar-actions {
  display: flex;
  gap: var(--sp-2);
}
/* 统计横滚 chip(一行装不下时横向滑动) */
.stat-strip {
  display: flex;
  gap: var(--sp-2);
  overflow-x: auto;
  padding-bottom: 2px;
  flex-shrink: 0;
}
.stat-strip .chip {
  flex-shrink: 0;
}
/* 过滤 chip 横滚(来源 + 状态两段) */
.filter-strip {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  overflow-x: auto;
  padding-bottom: 2px;
  flex-shrink: 0;
}
.f-chip {
  cursor: pointer;
  flex-shrink: 0;
  user-select: none;
  /* chip 默认偏矮,补一点内边距保触摸目标 */
  padding: 6px 12px;
}
.strip-sep {
  width: 1px;
  height: 16px;
  background: var(--border);
  flex-shrink: 0;
}
/* 条目卡片:整卡可点开编辑,min-height 保触摸目标 */
.wb-card {
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  min-height: 44px;
}
.card-off .wb-title {
  color: var(--text-faint);
}
.wb-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
}
.wb-title {
  font-weight: 600;
  font-size: var(--f-md);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.switch-cell {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}
.wb-chips {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.key-chip { max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wb-meta {
  font-size: var(--f-xs);
  color: var(--text-dim);
}
/* 弹窗表单 */
.m-modal-body {
  max-height: 72vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.m-label {
  font-size: 12px;
  color: var(--text-dim);
}
.ro-info {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--r-sm);
  background: rgba(255, 255, 255, 0.03);
}
.m-actions {
  display: flex;
  gap: var(--sp-2);
  margin-top: var(--sp-1);
}
</style>
