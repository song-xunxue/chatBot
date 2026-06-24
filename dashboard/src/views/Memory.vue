<script setup lang="ts">
/**
 * 记忆查看：统计 + 长期/情节/核心 三层 + 手动遗忘单条（rest_memory）
 * 作者: 李文煜
 */
import { ref, h } from 'vue'
import {
  NCard, NSpace, NInput, NButton, NDataTable, NStatistic, NGrid, NGi, NTag, NEmpty,
  useMessage, type DataTableColumns,
} from 'naive-ui'
import { getMemory, getMemoryStats, forgetOneMemory } from '@/api'

const message = useMessage()
const oid = ref('default')
const stats = ref<any>({})
const data = ref<any>({})
const loaded = ref(false)

async function load() {
  if (!oid.value) return
  try {
    stats.value = await getMemoryStats(oid.value)
    data.value = await getMemory(oid.value, 'all')
    loaded.value = true
  } catch (e: any) {
    message.error('' + e)
  }
}
async function forget(mid: string) {
  try {
    await forgetOneMemory(oid.value, mid)
    message.success('已遗忘')
    load()
  } catch (e: any) {
    message.error('' + e)
  }
}

const ltCols: DataTableColumns<any> = [
  { title: '内容', key: 'content', ellipsis: { tooltip: true } },
  { title: '类别', key: 'category', width: 100, render: (m) => h(NTag, { size: 'small' }, () => m.category) },
  { title: '重要', key: 'importance', width: 80 },
  {
    title: '操作', key: 'op', width: 80,
    render: (m) => h(NButton, { size: 'small', type: 'error', quaternary: true, onClick: () => forget(m.id) }, () => '遗忘'),
  },
]
const epCols: DataTableColumns<any> = [
  { title: '摘要', key: 'summary', ellipsis: { tooltip: true } },
  { title: '时间', key: 'created_ts', width: 160 },
]
</script>

<template>
  <n-space vertical size="large">
    <n-space align="center">
      <n-input v-model:value="oid" placeholder="object_id" style="width: 240px" />
      <n-button type="primary" @click="load">查看记忆</n-button>
    </n-space>

    <n-grid v-if="loaded" :cols="4" :x-gap="12">
      <n-gi><n-card size="small"><n-statistic label="长期(全部)" :value="stats.long_term_total" /></n-card></n-gi>
      <n-gi><n-card size="small"><n-statistic label="长期(活跃)" :value="stats.long_term_active" /></n-card></n-gi>
      <n-gi><n-card size="small"><n-statistic label="长期(已遗忘)" :value="stats.long_term_forgotten" /></n-card></n-gi>
      <n-gi><n-card size="small"><n-statistic label="情节摘要" :value="stats.episodic_count" /></n-card></n-gi>
    </n-grid>

    <n-card title="长期记忆 Long-term" size="small">
      <n-data-table v-if="(data.long_term || []).length" :columns="ltCols" :data="data.long_term || []" :bordered="false" />
      <n-empty v-else description="无" />
    </n-card>
    <n-card title="情节记忆 Episodic" size="small">
      <n-data-table v-if="(data.episodic || []).length" :columns="epCols" :data="data.episodic || []" :bordered="false" />
      <n-empty v-else description="无" />
    </n-card>
    <n-card title="核心记忆 Core" size="small">
      <n-space v-if="(data.core || []).length" vertical>
        <n-card v-for="(c, i) in data.core" :key="i" size="small">{{ c.content || JSON.stringify(c) }}</n-card>
      </n-space>
      <n-empty v-else description="无" />
    </n-card>
  </n-space>
</template>
