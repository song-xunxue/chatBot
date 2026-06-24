<script setup lang="ts">
/**
 * 对话历史：按 object_id 查看历史消息（rest_admin /history/{oid}）
 * 作者: 李文煜
 */
import { ref, h } from 'vue'
import {
  NSpace, NInput, NInputNumber, NButton, NDataTable, NTag,
  useMessage, type DataTableColumns,
} from 'naive-ui'
import { getHistory } from '@/api'

const message = useMessage()
const oid = ref('default')
const limit = ref(50)
const msgs = ref<any[]>([])

async function load() {
  try {
    const d = await getHistory(oid.value, Number(limit.value))
    msgs.value = d.messages
  } catch (e: any) {
    message.error('' + e)
  }
}

const cols: DataTableColumns<any> = [
  {
    title: '角色', key: 'role', width: 90,
    render: (m) => h(NTag, { size: 'small', type: m.role === 'user' ? 'info' : 'success' }, () => m.role),
  },
  { title: '内容', key: 'content', ellipsis: { tooltip: true } },
  { title: '时间', key: 'ts', width: 140 },
]
</script>

<template>
  <n-space vertical size="large">
    <n-space align="center">
      <n-input v-model:value="oid" placeholder="object_id" style="width: 220px" @keyup.enter="load" />
      <n-input-number v-model:value="limit" :min="1" :max="500" style="width: 120px" />
      <n-button type="primary" @click="load">查询</n-button>
    </n-space>
    <n-data-table :columns="cols" :data="msgs" :bordered="false" />
  </n-space>
</template>
