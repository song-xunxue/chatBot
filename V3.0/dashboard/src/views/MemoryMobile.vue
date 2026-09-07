<script setup lang="ts">
/**
 * 移动端记忆查看(功能对等 PC Memory.vue,窄屏重排):
 * ① 统计 2x2(长期活跃/已遗忘/情节/核心) ② 三层记忆用 NTabs 切换(长期置默认,含类别筛选)
 * ③ 每条记忆:content + reason 斜体 + tags 圆角标 + importance/useful_score/tier 徽标 + locked/手动标
 * ④ 编辑弹窗(content/reason/category/importance/useful_score/tier/tags)
 * ⑤ 「+ 新增记忆」弹窗(source=manual,含 locked 锁定防遗忘) ⑥ 遗忘(NPopconfirm)/锁定切换
 * 逻辑与 PC 端完全一致(useObject 共享 oid;PC 无轮询,移动端同样不加)。
 * 窄屏取舍:统计 4 列改 2x2;三层卡片改 NTabs;类别筛选/弹窗内控件全宽;记忆条目卡片化(m-card);
 * 卡片操作按钮 size=large 平铺一行(触摸≥44px);弹窗 94vw + 内容区限高可滚动。
 * 作者: 李文煜
 */
import { ref, computed, watch, onMounted } from 'vue'
import {
  NTabs, NTabPane, NSpace, NInput, NInputNumber, NButton, NCard, NGrid, NGi, NStatistic,
  NTag, NEmpty, NSelect, NPopconfirm, NModal, NSlider, NDynamicTags, useMessage,
} from 'naive-ui'
import { getMemory, getMemoryStats, forgetOneMemory, lockMemory, updateMemory, createMemory } from '@/api'
import { useObject } from '@/composables/useObject'

const message = useMessage()
const { oid, reloadTick, ensureOid } = useObject()
watch(reloadTick, () => load())
const stats = ref<any>({})
const data = ref<any>({})
const loaded = ref(false)
const catFilter = ref<string | null>(null)

// 类别筛选选项(含"全部")
const catOptions = [
  { label: '全部类别', value: '' },
  { label: '事实 fact', value: 'fact' },
  { label: '偏好 preference', value: 'preference' },
  { label: '关系 relationship', value: 'relationship' },
  { label: '事件 event', value: 'event' },
  { label: '性格 personality', value: 'personality' },
]
const catEditOptions = catOptions.slice(1)   // 编辑/新增用(无"全部")
// tier 档位选项:-1=自动(由 useful_score 判)/0=T0 自然衰减 /1=T1 评分驱动 /2=T2 永不衰减
const tierOptions = [
  { label: '自动(按用进废退分判)', value: -1 },
  { label: 'T0 自然衰减', value: 0 },
  { label: 'T1 评分驱动', value: 1 },
  { label: 'T2 永不衰减', value: 2 },
]
const tierBadge: Record<number, { label: string; type: any }> = {
  [-1]: { label: '自动', type: 'default' },
  0: { label: 'T0', type: 'error' },
  1: { label: 'T1', type: 'warning' },
  2: { label: 'T2 永不', type: 'success' },
}

// —— 编辑记忆(字段与 PC 一致,不含 locked:锁定走卡片上的锁按钮)——
const editShow = ref(false)
const editMid = ref('')
const editContent = ref('')
const editCategory = ref('fact')
const editImportance = ref(0.5)
const editReason = ref('')
const editTags = ref<string[]>([])
const editUsefulScore = ref(0.5)
const editTier = ref(-1)

// —— 新增记忆(source=manual)——
const createShow = ref(false)
const cContent = ref('')
const cCategory = ref('fact')
const cImportance = ref(0.5)
const cReason = ref('')
const cTags = ref<string[]>([])
const cUsefulScore = ref(0.5)
const cTier = ref(-1)
const cLocked = ref(false)

async function load() {
  if (!oid.value || oid.value === 'default') return
  try {
    stats.value = await getMemoryStats(oid.value)
    data.value = await getMemory(oid.value, 'all')
    loaded.value = true
  } catch (e: any) { message.error('' + e) }
}
function fmtTs(ts: number): string {
  if (!ts) return '—'
  const d = new Date(ts); const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function catColor(cat: string): 'success' | 'warning' | 'info' | 'error' | 'default' {
  return ({ fact: 'info', preference: 'warning', relationship: 'success', event: 'error', personality: 'default' } as any)[cat] || 'default'
}
async function forget(mid: string) {
  try { await forgetOneMemory(oid.value, mid); message.success('已遗忘'); load() }
  catch (e: any) { message.error('' + e) }
}
async function toggleLock(m: any) {
  try { await lockMemory(oid.value, m.id, !m.locked); message.success(m.locked ? '已解锁' : '已锁定(防遗忘)'); load() }
  catch (e: any) { message.error('' + e) }
}
function openEdit(m: any) {
  editMid.value = m.id
  editContent.value = m.content || ''
  editCategory.value = m.category || 'fact'
  editImportance.value = Number(m.importance ?? 0.5)
  editReason.value = m.reason || ''
  editTags.value = Array.isArray(m.tags) ? m.tags : []
  editUsefulScore.value = Number(m.useful_score ?? m.importance ?? 0.5)
  editTier.value = Number(m.tier ?? -1)
  editShow.value = true
}
async function applyEdit() {
  if (!editMid.value) return
  try {
    await updateMemory(oid.value, editMid.value, {
      content: editContent.value, category: editCategory.value, importance: editImportance.value,
      reason: editReason.value, tags: editTags.value, useful_score: editUsefulScore.value, tier: editTier.value,
    })
    message.success('已修改')
    editShow.value = false; editMid.value = ''
    await load()
  } catch (e: any) { message.error('' + e) }
}
function openCreate() {
  cContent.value = ''; cCategory.value = 'fact'; cImportance.value = 0.5
  cReason.value = ''; cTags.value = []; cUsefulScore.value = 0.5; cTier.value = -1; cLocked.value = false
  createShow.value = true
}
async function applyCreate() {
  if (!cContent.value.trim()) { message.warning('请输入记忆内容'); return }
  try {
    await createMemory(oid.value, {
      content: cContent.value, category: cCategory.value, importance: cImportance.value,
      reason: cReason.value, tags: cTags.value, useful_score: cUsefulScore.value, tier: cTier.value, locked: cLocked.value,
    })
    message.success('已新增记忆')
    createShow.value = false
    await load()
  } catch (e: any) { message.error('' + e) }
}
// 长期记忆按类别筛选
const ltFiltered = computed(() => {
  const list = data.value.long_term || []
  if (!catFilter.value) return list
  return list.filter((m: any) => m.category === catFilter.value)
})

onMounted(async () => { await ensureOid(); await load() })
</script>

<template>
  <n-space vertical size="medium">
    <!-- 顶栏:标题 + 新增/刷新 -->
    <div class="m-topbar">
      <span class="m-title">记忆查看</span>
      <n-space :size="8">
        <n-button size="small" type="primary" ghost @click="openCreate">+ 新增记忆</n-button>
        <n-button size="small" quaternary @click="load">刷新</n-button>
      </n-space>
    </div>

    <!-- ① 统计(4 列改 2x2) -->
    <n-grid v-if="loaded" :cols="2" :x-gap="8" :y-gap="8">
      <n-gi><n-card size="small"><n-statistic label="长期(活跃)" :value="stats.long_term_active" /></n-card></n-gi>
      <n-gi><n-card size="small"><n-statistic label="长期(已遗忘)" :value="stats.long_term_forgotten" /></n-card></n-gi>
      <n-gi><n-card size="small"><n-statistic label="情节摘要" :value="stats.episodic" /></n-card></n-gi>
      <n-gi><n-card size="small"><n-statistic label="核心记忆" :value="stats.core" /></n-card></n-gi>
    </n-grid>

    <!-- ② 三层记忆(卡片改 NTabs,长期置默认) -->
    <n-tabs type="line" animated default-value="lt">
      <!-- 长期记忆 -->
      <n-tab-pane name="lt" :tab="`长期 ${stats.long_term_active ?? 0}`">
        <n-select
          v-model:value="catFilter"
          :options="catOptions"
          placeholder="全部类别"
          size="large"
          clearable
          style="margin-bottom:10px"
        />
        <n-empty v-if="!ltFiltered.length" size="small" description="无" />
        <div v-for="m in ltFiltered" :key="m.id" class="m-card">
          <div class="m-tags">
            <n-tag size="small" :type="catColor(m.category)">{{ m.category }}</n-tag>
            <n-tag size="small" type="default">重要 {{ Number(m.importance || 0).toFixed(2) }}</n-tag>
            <n-tag size="small" :type="(tierBadge[m.tier ?? -1] || tierBadge[-1]).type">
              {{ (tierBadge[m.tier ?? -1] || tierBadge[-1]).label }} · 用进 {{ Number(m.useful_score ?? 0).toFixed(2) }}
            </n-tag>
            <n-tag v-if="m.locked" size="small" type="warning">已锁定</n-tag>
            <n-tag v-if="m.source === 'manual'" size="small" type="info">手动</n-tag>
          </div>
          <div class="m-content">{{ m.content }}</div>
          <div v-if="m.reason" class="m-reason">理由:{{ m.reason }}</div>
          <n-space v-if="m.tags && m.tags.length" :size="4" style="margin-top:6px">
            <n-tag v-for="t in m.tags" :key="t" size="tiny" round>#{{ t }}</n-tag>
          </n-space>
          <div class="m-ts">{{ fmtTs(m.created_ts) }}</div>
          <div class="m-actions">
            <n-button size="large" type="primary" ghost style="flex:1" @click="openEdit(m)">编辑</n-button>
            <n-button size="large" quaternary style="flex:1" @click="toggleLock(m)">{{ m.locked ? '解锁' : '锁定' }}</n-button>
            <n-popconfirm @positive-click="forget(m.id)">
              <template #trigger><n-button size="large" type="error" ghost style="flex:1">遗忘</n-button></template>
              确认遗忘这条?
            </n-popconfirm>
          </div>
        </div>
      </n-tab-pane>

      <!-- 情节记忆 -->
      <n-tab-pane name="ep" :tab="`情节 ${stats.episodic ?? 0}`">
        <n-empty v-if="!(data.episodic || []).length" size="small" description="无" />
        <div v-for="(e, i) in (data.episodic || [])" :key="i" class="m-card">
          <div class="m-content">{{ e.summary }}</div>
          <div class="m-ts">{{ fmtTs(e.created_ts) }}</div>
        </div>
      </n-tab-pane>

      <!-- 核心记忆 -->
      <n-tab-pane name="core" :tab="`核心 ${stats.core ?? 0}`">
        <n-empty v-if="!(data.core || []).length" size="small" description="无" />
        <div v-for="(c, i) in (data.core || [])" :key="i" class="m-card">
          <div class="m-content">{{ c.content || JSON.stringify(c) }}</div>
        </div>
      </n-tab-pane>
    </n-tabs>

    <!-- ④ 编辑记忆弹窗(content 用角色第一人称;字段与 PC 一致) -->
    <n-modal v-model:show="editShow" preset="card" title="编辑记忆" style="width:94vw;max-width:560px">
      <div class="m-modal-body">
        <n-space vertical :size="12">
          <n-input
            v-model:value="editContent" type="textarea" :autosize="{ minRows: 4, maxRows: 8 }" autofocus
            placeholder="用角色第一人称记录,'我'指角色自己(区分角色与用户)。如'我叫清浔''用户喜欢动漫''用户希望被称为煜'"
          />
          <n-input
            v-model:value="editReason" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }"
            placeholder="理由:为什么这条值得记(可选,面板展示用)"
          />
          <div>
            <div class="m-label">类别</div>
            <n-select v-model:value="editCategory" :options="catEditOptions" size="large" />
          </div>
          <div>
            <div class="m-label">重要度(0~1)</div>
            <n-input-number v-model:value="editImportance" :min="0" :max="1" :step="0.1" size="large" style="width:100%" />
          </div>
          <div>
            <div class="m-label">用进退分:{{ editUsefulScore.toFixed(2) }}</div>
            <n-slider v-model:value="editUsefulScore" :min="0" :max="1" :step="0.05" />
          </div>
          <div>
            <div class="m-label">档位</div>
            <n-select v-model:value="editTier" :options="tierOptions" size="large" />
          </div>
          <div>
            <div class="m-label">标签(最多 5 个)</div>
            <n-dynamic-tags v-model:value="editTags" :max="5" />
          </div>
          <div class="m-actions">
            <n-button size="large" quaternary style="flex:1" @click="editShow = false">取消</n-button>
            <n-button size="large" type="primary" style="flex:1" @click="applyEdit">确定</n-button>
          </div>
        </n-space>
      </div>
    </n-modal>

    <!-- ⑤ 新增记忆弹窗(手动写入,source=manual,含锁定) -->
    <n-modal v-model:show="createShow" preset="card" title="新增记忆(手动)" style="width:94vw;max-width:560px">
      <div class="m-modal-body">
        <n-space vertical :size="12">
          <n-input
            v-model:value="cContent" type="textarea" :autosize="{ minRows: 4, maxRows: 8 }" autofocus
            placeholder="记忆内容(角色第一人称)。如'我叫清浔''煜君喜欢深夜聊天'"
          />
          <n-input
            v-model:value="cReason" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }"
            placeholder="理由:为什么这条值得记(可选)"
          />
          <div>
            <div class="m-label">类别</div>
            <n-select v-model:value="cCategory" :options="catEditOptions" size="large" />
          </div>
          <div>
            <div class="m-label">重要度(0~1)</div>
            <n-input-number v-model:value="cImportance" :min="0" :max="1" :step="0.1" size="large" style="width:100%" />
          </div>
          <div>
            <div class="m-label">用进退分:{{ cUsefulScore.toFixed(2) }}</div>
            <n-slider v-model:value="cUsefulScore" :min="0" :max="1" :step="0.05" />
          </div>
          <div>
            <div class="m-label">档位</div>
            <n-select v-model:value="cTier" :options="tierOptions" size="large" />
          </div>
          <div>
            <div class="m-label">标签(最多 5 个)</div>
            <n-dynamic-tags v-model:value="cTags" :max="5" />
          </div>
          <n-button size="large" block ghost :type="cLocked ? 'warning' : 'default'" @click="cLocked = !cLocked">
            {{ cLocked ? '已锁定(永不遗忘)' : '锁定防遗忘' }}
          </n-button>
          <div class="m-actions">
            <n-button size="large" quaternary style="flex:1" @click="createShow = false">取消</n-button>
            <n-button size="large" type="primary" style="flex:1" @click="applyCreate">新增</n-button>
          </div>
        </n-space>
      </div>
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
.m-card {
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 10px;
  margin-bottom: 8px;
}
.m-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  margin-bottom: 6px;
}
.m-content {
  white-space: pre-wrap;
  word-break: break-all;
}
.m-reason {
  margin-top: 4px;
  font-size: 12px;
  color: #888;
  font-style: italic;
}
.m-ts {
  font-size: 11px;
  color: #aaa;
  margin-top: 6px;
}
.m-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.m-label {
  font-size: 12px;
  color: #999;
  margin-bottom: 4px;
}
.m-modal-body {
  max-height: 72vh;
  overflow-y: auto;
}
</style>
