<script setup lang="ts">
/**
 * 记忆查看（V1.2 美化）：统计 + 类别筛选(预选) + 时间格式化 + 彩色类别标签 + 卡片式 + 手动遗忘。
 * 作者: 李文煜
 */
import { ref, computed } from 'vue'
import { NCard, NSpace, NInput, NButton, NStatistic, NGrid, NGi, NTag, NEmpty, NSelect, NPopconfirm, useMessage } from 'naive-ui'
import { getMemory, getMemoryStats, forgetOneMemory } from '@/api'

const message = useMessage()
const oid = ref('default')
const stats = ref<any>({})
const data = ref<any>({})
const loaded = ref(false)
const catFilter = ref<string | null>(null)   // V1.2 长期记忆类别筛选（预选）

const catOptions = [
  { label: '全部类别', value: '' },
  { label: '事实 fact', value: 'fact' },
  { label: '偏好 preference', value: 'preference' },
  { label: '关系 relationship', value: 'relationship' },
  { label: '事件 event', value: 'event' },
  { label: '性格 personality', value: 'personality' },
]

async function load() {
  if (!oid.value) return
  try {
    stats.value = await getMemoryStats(oid.value)
    data.value = await getMemory(oid.value, 'all')
    loaded.value = true
  } catch (e: any) { message.error('' + e) }
}
function fmtTs(ts: number): string {
  if (!ts) return '—'
  const d = new Date(ts); const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function catColor(cat: string): 'success' | 'warning' | 'info' | 'error' | 'default' {
  return ({ fact: 'info', preference: 'warning', relationship: 'success', event: 'error', personality: 'default' } as any)[cat] || 'default'
}
async function forget(mid: string) {
  try { await forgetOneMemory(oid.value, mid); message.success('已遗忘'); load() }
  catch (e: any) { message.error('' + e) }
}
// V1.2 长期记忆按类别筛选
const ltFiltered = computed(() => {
  const list = data.value.long_term || []
  if (!catFilter.value) return list
  return list.filter((m: any) => m.category === catFilter.value)
})
</script>

<template>
  <n-space vertical size="large">
    <n-space align="center">
      <n-input v-model:value="oid" placeholder="object_id" style="width: 240px" @keyup.enter="load" />
      <n-button type="primary" @click="load">查看记忆</n-button>
    </n-space>

    <n-grid v-if="loaded" :cols="4" :x-gap="12">
      <n-gi><n-card size="small"><n-statistic label="长期(全部)" :value="stats.long_term_total" /></n-card></n-gi>
      <n-gi><n-card size="small"><n-statistic label="长期(活跃)" :value="stats.long_term_active" /></n-card></n-gi>
      <n-gi><n-card size="small"><n-statistic label="长期(已遗忘)" :value="stats.long_term_forgotten" /></n-card></n-gi>
      <n-gi><n-card size="small"><n-statistic label="情节摘要" :value="stats.episodic_count" /></n-card></n-gi>
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
          </n-space>
          <n-space>
            <span style="font-size:11px;color:#aaa">{{ fmtTs(m.created_ts) }}</span>
            <n-popconfirm @positive-click="forget(m.id)"><template #trigger><n-button size="tiny" type="error" ghost>遗忘</n-button></template>确认遗忘这条？</n-popconfirm>
          </n-space>
        </n-space>
        <div style="margin-top:6px">{{ m.content }}</div>
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
        <n-card v-for="(c, i) in data.core" :key="i" size="small">{{ c.content || JSON.stringify(c) }}</n-card>
      </n-space>
      <n-empty v-else description="无" />
    </n-card>
  </n-space>
</template>
