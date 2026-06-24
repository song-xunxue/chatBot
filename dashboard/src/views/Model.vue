<script setup lang="ts">
/**
 * 模型配置：LLM provider 列表(是否配 key/可用) + 人设模型绑定（rest_admin /models + rest_persona /model）
 * 作者: 李文煜
 */
import { ref, h, onMounted } from 'vue'
import {
  NCard, NDataTable, NTag, NSpace, NSelect, NInput, NButton,
  useMessage, type DataTableColumns,
} from 'naive-ui'
import { getModels, listPersonas, bindPersonaModel } from '@/api'

const message = useMessage()
const data = ref<{ providers: any[]; default: string }>({ providers: [], default: '' })
const personas = ref<any[]>([])
const selPersona = ref<string | null>(null)
const provider = ref('glm')
const model = ref('')

async function load() {
  data.value = await getModels()
  personas.value = await listPersonas()
}
onMounted(load)

async function bind() {
  if (!selPersona.value) {
    message.warning('请先选择人设')
    return
  }
  try {
    await bindPersonaModel(selPersona.value, { provider: provider.value, model: model.value })
    message.success('已绑定')
  } catch (e: any) {
    message.error('' + e)
  }
}

const personaOpts = () => personas.value.map((p) => ({ label: p.name || p.id, value: p.id }))

const cols: DataTableColumns<any> = [
  { title: 'Provider', key: 'name' },
  {
    title: '已配置 Key', key: 'configured',
    render: (p) => h(NTag, { size: 'small', type: p.configured ? 'success' : 'default' }, () => (p.configured ? '是' : '否')),
  },
  {
    title: '可用(已配 key)', key: 'available',
    render: (p) => h(NTag, { size: 'small', type: p.available ? 'success' : 'warning' }, () => (p.available ? '是' : '否')),
  },
]
</script>

<template>
  <n-space vertical size="large">
    <n-card title="LLM Provider" size="small">
      <n-data-table :columns="cols" :data="data.providers" :bordered="false" />
    </n-card>
    <n-card title="人设模型绑定" size="small">
      <n-space align="center">
        <n-select v-model:value="selPersona" :options="personaOpts()" placeholder="选择人设" style="width: 200px" />
        <n-input v-model:value="provider" placeholder="provider（glm/deepseek/siliconflow）" style="width: 220px" />
        <n-input v-model:value="model" placeholder="模型名（可空用默认）" style="width: 200px" />
        <n-button type="primary" @click="bind">绑定</n-button>
      </n-space>
    </n-card>
  </n-space>
</template>
