<script setup lang="ts">
/**
 * 插件管理：列表 + 全局开关 + 按对象启用/参数配置（rest_plugin）
 * 作者: 李文煜
 */
import { ref, h, onMounted } from 'vue'
import {
  NDataTable, NButton, NSpace, NInput, NSwitch, NTag, NCard,
  useMessage, type DataTableColumns,
} from 'naive-ui'
import { listPlugins, enablePlugin, disablePlugin, getObjectPlugins, setObjectPlugin } from '@/api'

const message = useMessage()
const plugins = ref<any[]>([])
const loading = ref(false)
const oid = ref('default')
const objPlugins = ref<any[]>([])

async function load() {
  loading.value = true
  try {
    plugins.value = await listPlugins()
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function toggle(p: any) {
  try {
    if (p.global_enabled) await disablePlugin(p.name)
    else await enablePlugin(p.name)
    message.success(p.global_enabled ? '已禁用' : '已启用')
    load()
    if (oid.value) loadObj()
  } catch (e: any) {
    message.error('' + e)
  }
}
async function loadObj() {
  if (!oid.value) return
  try {
    objPlugins.value = await getObjectPlugins(oid.value)
  } catch (e: any) {
    message.error('' + e)
  }
}
async function toggleObj(p: any) {
  try {
    await setObjectPlugin(oid.value, p.name, { enabled: !p.enabled })
    message.success('已更新')
    loadObj()
  } catch (e: any) {
    message.error('' + e)
  }
}

const cols: DataTableColumns<any> = [
  { title: '插件', key: 'name' },
  { title: '版本', key: 'version', width: 80 },
  {
    title: '全局开关', key: 'global_enabled',
    render: (p) => h(NSwitch, { value: p.global_enabled, onUpdateValue: () => toggle(p) }),
  },
  {
    title: '默认', key: 'default_enabled',
    render: (p) => h(NTag, { size: 'small', type: p.default_enabled ? 'success' : 'default' }, () => (p.default_enabled ? '开' : '关')),
  },
  { title: '钩子', key: 'hooks', render: (p) => (p.hooks || []).map((x: any) => x.name).join(', ') },
]
const objCols: DataTableColumns<any> = [
  { title: '插件', key: 'name' },
  {
    title: '启用(该对象)', key: 'enabled',
    render: (p) => h(NSwitch, { value: p.enabled, onUpdateValue: () => toggleObj(p) }),
  },
  { title: '参数', key: 'params', ellipsis: { tooltip: true }, render: (p) => JSON.stringify(p.params) },
]
</script>

<template>
  <n-space vertical size="large">
    <n-space>
      <n-button @click="load" :loading="loading">刷新插件</n-button>
    </n-space>
    <n-data-table :columns="cols" :data="plugins" :loading="loading" :bordered="false" />
    <n-card title="按对象配置" size="small">
      <n-space align="center">
        <n-input v-model:value="oid" placeholder="object_id" style="width: 240px" />
        <n-button @click="loadObj">查询</n-button>
      </n-space>
      <n-data-table :columns="objCols" :data="objPlugins" :bordered="false" style="margin-top: 12px" />
    </n-card>
  </n-space>
</template>
