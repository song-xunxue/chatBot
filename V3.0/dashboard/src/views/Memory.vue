<script setup lang="ts">
/**
 * 记忆查看(V2.0 改造 2026-07-05;2026-07-06 加编辑;2026-08-13 加三要素+用进废退):
 * 去 object_id 输入框,启动自动加载全局 oid(单人设/单用户场景)。
 * 统计(core/episodic/long_term_active/forgotten)+ 类别筛选 + 彩色标签 + 手动遗忘/锁定 + 编辑记忆。
 * 2026-08-13:展示 reason(理由)/tags(标签)/useful_score(用进废退分)/tier(档位);
 *   编辑可改 reason/tags/useful_score/tier;顶部「+ 新增记忆」手动写入(source=manual)。
 * 作者: 李文煜
 */
import { ref, computed, watch, onMounted } from 'vue'
import {
  NCard, NSpace, NButton, NStatistic, NGrid, NGi, NTag, NEmpty, NSelect, NPopconfirm,
  NModal, NInput, NInputNumber, NSlider, NDynamicTags, useMessage,
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

// —— 编辑记忆 ——
const editShow = ref(false)
const editMid = ref('')
const editContent = ref('')
const editCategory = ref('fact')
const editImportance = ref(0.5)
const editReason = ref('')
const editTags = ref<string[]>([])
const editUsefulScore = ref(0.5)
const editTier = ref(-1)

// —— 新增记忆 ——
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
const ltFiltered = computed(() => {
  const list = data.value.long_term || []
  if (!catFilter.value) return list
  return list.filter((m: any) => m.category === catFilter.value)
})

onMounted(async () => { await ensureOid(); await load() })
</script>

<template>
  <n-space vertical size="large">
    <n-space align="center" justify="space-between">
      <span style="font-weight:600">记忆查看</span>
      <n-space>
        <n-button size="small" type="primary" ghost @click="openCreate">+ 新增记忆</n-button>
        <n-button size="small" @click="load">刷新</n-button>
      </n-space>
    </n-space>

    <n-grid v-if="loaded" :cols="4" :x-gap="12">
      <n-gi><n-card size="small"><n-statistic label="长期(活跃)" :value="stats.long_term_active" /></n-card></n-gi>
      <n-gi><n-card size="small"><n-statistic label="长期(已遗忘)" :value="stats.long_term_forgotten" /></n-card></n-gi>
      <n-gi><n-card size="small"><n-statistic label="情节摘要" :value="stats.episodic" /></n-card></n-gi>
      <n-gi><n-card size="small"><n-statistic label="核心记忆" :value="stats.core" /></n-card></n-gi>
    </n-grid>

    <n-card title="长期记忆 Long-term" size="small">
      <n-space align="center" style="margin-bottom:10px">
        <span style="font-size:13px;color:#666">筛选类别：</span>
        <n-select v-model:value="catFilter" :options="catOptions" placeholder="全部类别" style="width:180px" clearable />
      </n-space>
      <n-empty v-if="!ltFiltered.length" description="无" />
      <n-card v-for="m in ltFiltered" :key="m.id" size="small" style="margin-bottom:8px">
        <n-space justify="space-between" align="center">
          <n-space align="center">
            <n-tag size="small" :type="catColor(m.category)">{{ m.category }}</n-tag>
            <n-tag size="small" type="default">重要 {{ Number(m.importance || 0).toFixed(2) }}</n-tag>
            <n-tag size="small" :type="(tierBadge[m.tier ?? -1] || tierBadge[-1]).type">
              {{ (tierBadge[m.tier ?? -1] || tierBadge[-1]).label }} · 用进 {{ Number(m.useful_score ?? 0).toFixed(2) }}
            </n-tag>
            <n-tag v-if="m.locked" size="small" type="warning">已锁定</n-tag>
            <n-tag v-if="m.source === 'manual'" size="small" type="info">手动</n-tag>
          </n-space>
          <n-space>
            <span style="font-size:11px;color:#aaa">{{ fmtTs(m.created_ts) }}</span>
            <n-button size="tiny" @click="openEdit(m)">编辑</n-button>
            <n-button size="tiny" @click="toggleLock(m)">{{ m.locked ? '解锁' : '锁定' }}</n-button>
            <n-popconfirm @positive-click="forget(m.id)"><template #trigger><n-button size="tiny" type="error" ghost>遗忘</n-button></template>确认遗忘这条？</n-popconfirm>
          </n-space>
        </n-space>
        <div style="margin-top:6px;white-space:pre-wrap">{{ m.content }}</div>
        <div v-if="m.reason" style="margin-top:4px;font-size:12px;color:#888;font-style:italic">理由:{{ m.reason }}</div>
        <n-space v-if="m.tags && m.tags.length" :size="4" style="margin-top:6px">
          <n-tag v-for="t in m.tags" :key="t" size="tiny" round>#{{ t }}</n-tag>
        </n-space>
      </n-card>
    </n-card>

    <n-card title="情节记忆 Episodic" size="small">
      <n-empty v-if="!(data.episodic || []).length" description="无" />
      <n-card v-for="(e, i) in (data.episodic || [])" :key="i" size="small" style="margin-bottom:8px">
        <div>{{ e.summary }}</div>
        <div style="font-size:11px;color:#aaa;margin-top:4px">{{ fmtTs(e.created_ts) }}</div>
      </n-card>
    </n-card>

    <n-card title="核心记忆 Core" size="small">
      <n-space v-if="(data.core || []).length" vertical>
        <n-card v-for="(c, i) in (data.core || [])" :key="i" size="small">{{ c.content || JSON.stringify(c) }}</n-card>
      </n-space>
      <n-empty v-else description="无" />
    </n-card>

    <!-- 编辑记忆弹窗(content 用角色第一人称) -->
    <n-modal v-model:show="editShow" preset="card" title="编辑记忆" style="width:620px;max-width:92vw">
      <n-space vertical :size="12">
        <n-input v-model:value="editContent" type="textarea" :rows="4" autofocus
                 placeholder="用角色第一人称记录,'我'指角色自己(区分角色与用户)。如'我叫清浔''用户喜欢动漫''用户希望被称为煜'" />
        <n-input v-model:value="editReason" type="textarea" :rows="2"
                 placeholder="理由:为什么这条值得记(可选,面板展示用)" />
        <n-space align="center" :wrap="false">
          <n-select v-model:value="editCategory" :options="catEditOptions" style="width:180px" />
          <n-space align="center" :size="6">
            <span style="font-size:12px;color:#999">重要度</span>
            <n-input-number v-model:value="editImportance" :min="0" :max="1" :step="0.1" style="width:110px" />
          </n-space>
        </n-space>
        <n-space align="center" :wrap="false">
          <n-space align="center" :size="6">
            <span style="font-size:12px;color:#999">用进退分</span>
            <n-slider v-model:value="editUsefulScore" :min="0" :max="1" :step="0.05" style="width:160px" />
            <span style="font-size:12px;width:32px">{{ editUsefulScore.toFixed(2) }}</span>
          </n-space>
          <n-select v-model:value="editTier" :options="tierOptions" style="width:200px" />
        </n-space>
        <div>
          <div style="font-size:12px;color:#999;margin-bottom:4px">标签</div>
          <n-dynamic-tags v-model:value="editTags" :max="5" />
        </div>
        <n-space justify="end">
          <n-button @click="editShow = false">取消</n-button>
          <n-button type="primary" @click="applyEdit">确定</n-button>
        </n-space>
      </n-space>
    </n-modal>

    <!-- 新增记忆弹窗(手动写入,source=manual) -->
    <n-modal v-model:show="createShow" preset="card" title="新增记忆(手动)" style="width:620px;max-width:92vw">
      <n-space vertical :size="12">
        <n-input v-model:value="cContent" type="textarea" :rows="4" autofocus
                 placeholder="记忆内容(角色第一人称)。如'我叫清浔''煜君喜欢深夜聊天'" />
        <n-input v-model:value="cReason" type="textarea" :rows="2"
                 placeholder="理由:为什么这条值得记(可选)" />
        <n-space align="center" :wrap="false">
          <n-select v-model:value="cCategory" :options="catEditOptions" style="width:180px" />
          <n-space align="center" :size="6">
            <span style="font-size:12px;color:#999">重要度</span>
            <n-input-number v-model:value="cImportance" :min="0" :max="1" :step="0.1" style="width:110px" />
          </n-space>
        </n-space>
        <n-space align="center" :wrap="false">
          <n-space align="center" :size="6">
            <span style="font-size:12px;color:#999">用进退分</span>
            <n-slider v-model:value="cUsefulScore" :min="0" :max="1" :step="0.05" style="width:160px" />
            <span style="font-size:12px;width:32px">{{ cUsefulScore.toFixed(2) }}</span>
          </n-space>
          <n-select v-model:value="cTier" :options="tierOptions" style="width:200px" />
        </n-space>
        <div>
          <div style="font-size:12px;color:#999;margin-bottom:4px">标签</div>
          <n-dynamic-tags v-model:value="cTags" :max="5" />
        </div>
        <n-space align="center">
          <n-button size="small" :type="cLocked ? 'warning' : 'default'" @click="cLocked = !cLocked">
            {{ cLocked ? '已锁定(永不遗忘)' : '锁定防遗忘' }}
          </n-button>
        </n-space>
        <n-space justify="end">
          <n-button @click="createShow = false">取消</n-button>
          <n-button type="primary" @click="applyCreate">新增</n-button>
        </n-space>
      </n-space>
    </n-modal>
  </n-space>
</template>
