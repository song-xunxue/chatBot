<script setup lang="ts">
/**
 * 人设管理：列表 / 新建 / 编辑 / 删除 / 导入 persona_*.json（rest_persona）
 * 作者: 李文煜
 */
import { ref, h, onMounted } from 'vue'
import {
  NDataTable, NButton, NSpace, NModal, NForm, NFormItem, NInput, NUpload,
  useMessage, useDialog, type DataTableColumns,
} from 'naive-ui'
import { listPersonas, createPersona, updatePersona, deletePersona, importPersona } from '@/api'

interface Persona { id: string; name: string; description: string; creator_notes?: string }

const message = useMessage()
const dialog = useDialog()
const list = ref<Persona[]>([])
const loading = ref(false)
const showModal = ref(false)
const editing = ref<Persona | null>(null)
const form = ref({ name: '', description: '', creator_notes: '' })

async function load() {
  loading.value = true
  try {
    list.value = await listPersonas()
  } catch (e: any) {
    message.error('加载失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}
onMounted(load)

function openCreate() {
  editing.value = null
  form.value = { name: '', description: '', creator_notes: '' }
  showModal.value = true
}
function openEdit(p: Persona) {
  editing.value = p
  form.value = { name: p.name, description: p.description || '', creator_notes: p.creator_notes || '' }
  showModal.value = true
}
async function save() {
  try {
    if (editing.value) await updatePersona(editing.value.id, { ...form.value, id: editing.value.id })
    else await createPersona(form.value)
    message.success('已保存')
    showModal.value = false
    load()
  } catch (e: any) {
    message.error('保存失败: ' + (e.message || e))
  }
}
function remove(p: Persona) {
  dialog.warning({
    title: '删除人设', content: `确定删除「${p.name}」？`, positiveText: '删除', negativeText: '取消',
    onPositiveClick: async () => {
      await deletePersona(p.id)
      message.success('已删除')
      load()
    },
  })
}
async function onImport(file: File) {
  try {
    await importPersona(file)
    message.success('导入成功')
    load()
  } catch (e: any) {
    message.error('导入失败: ' + (e.message || e))
  }
}

const columns: DataTableColumns<Persona> = [
  { title: 'ID', key: 'id', width: 160 },
  { title: '名称', key: 'name' },
  { title: '描述', key: 'description', ellipsis: { tooltip: true } },
  {
    title: '操作', key: 'actions', width: 160,
    render: (p) => h('div', { style: 'display:flex;gap:8px' }, [
      h(NButton, { size: 'small', onClick: () => openEdit(p) }, () => '编辑'),
      h(NButton, { size: 'small', type: 'error', ghost: true, onClick: () => remove(p) }, () => '删除'),
    ]),
  },
]
</script>

<template>
  <n-space vertical size="large">
    <n-space>
      <n-button type="primary" @click="openCreate">新建人设</n-button>
      <n-upload :show-file-list="false" accept=".json"
                :custom-request="(opt: any) => { if (opt.file?.file) onImport(opt.file.file) }">
        <n-button>导入 persona_*.json</n-button>
      </n-upload>
      <n-button @click="load" :loading="loading">刷新</n-button>
    </n-space>
    <n-data-table :columns="columns" :data="list" :loading="loading" :bordered="false" />
    <n-modal v-model:show="showModal" preset="card" :title="editing ? '编辑人设' : '新建人设'" style="width: 480px">
      <n-form label-placement="top">
        <n-form-item label="名称"><n-input v-model:value="form.name" /></n-form-item>
        <n-form-item label="描述"><n-input v-model:value="form.description" type="textarea" /></n-form-item>
        <n-form-item label="创作备注 creator_notes"><n-input v-model:value="form.creator_notes" type="textarea" /></n-form-item>
        <n-space justify="end">
          <n-button @click="showModal = false">取消</n-button>
          <n-button type="primary" @click="save">保存</n-button>
        </n-space>
      </n-form>
    </n-modal>
  </n-space>
</template>
