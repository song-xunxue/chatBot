<script setup lang="ts">
/**
 * 人设管理(V2.0 简化 2026-07-04;2026-07-05 改造):
 * 单人设模式(只编辑,不新建/删除) + 长文本字段弹窗大窗口编辑 + 新增"关于用户"字段(描述对话另一方)。
 * 去掉人设 ID 标签(单人设场景无需标识符)。底层 persona/store 多 pid 结构保留(pipeline 解析依赖)。
 * 作者: 李文煜
 */
import { ref, onMounted, computed } from 'vue'
import { NButton, NSpace, NForm, NFormItem, NInput, NSelect, NSpin, NEmpty, NModal, useMessage } from 'naive-ui'
import { listPersonas, updatePersona, bindPersonaModel, getSystemConfig } from '@/api'

const message = useMessage()
const loading = ref(false)
const saving = ref(false)
const persona = ref<any>(null)   // 当前唯一人设(单人设)
const form = ref({
  name: '', description: '', creator_notes: '', user_description: '',
  provider: 'deepseek', model: '',
})
const providers = ref<{ name: string; configured: boolean }[]>([])

// —— 长文本字段定义(预览+展开编辑)——
const LONG_FIELDS: { field: 'description' | 'creator_notes' | 'user_description'; label: string; hint: string }[] = [
  { field: 'description', label: '描述(背景设定)', hint: '人设的背景故事 / 世界观设定' },
  { field: 'creator_notes', label: '创作备注(核心人设指令)', hint: '最核心的人设指令,决定 AI 的行为准则' },
  { field: 'user_description', label: '关于用户(你)', hint: '描述对话另一方(你)的特征,让人设更熟悉你' },
]

// —— 长文本统一编辑弹窗 ——
const editShow = ref(false)
const editField = ref<'description' | 'creator_notes' | 'user_description'>('description')
const editLabel = ref('')
const editValue = ref('')

function openEdit(field: 'description' | 'creator_notes' | 'user_description') {
  const meta = LONG_FIELDS.find((f) => f.field === field)!
  editField.value = field
  editLabel.value = meta.label
  editValue.value = (form.value as any)[field] || ''
  editShow.value = true
}
function applyEdit() {
  ;(form.value as any)[editField.value] = editValue.value
  editShow.value = false
}

async function loadProviders() {
  try {
    const cfg = await getSystemConfig()
    providers.value = cfg?.providers || []
  } catch {
    providers.value = []   // 拉取失败不阻塞,下拉为空
  }
}
// 下拉选项:已配置可选;未配置灰显禁用;当前值即使未配置也纳入(避免编辑丢失)
const providerOptions = computed(() => {
  const cur = form.value.provider
  const list = providers.value.map((p) => ({
    label: `${p.name}${p.configured ? '' : '(未配置)'}`, value: p.name, disabled: !p.configured,
  }))
  if (cur && !providers.value.some((p) => p.name === cur)) {
    list.unshift({ label: `${cur}(未配置)`, value: cur, disabled: false })
  }
  return list
})

async function load() {
  loading.value = true
  try {
    const list = await listPersonas()
    if (!list.length) { message.warning('无人设(预期应有默认人设,检查 lifespan seed)'); return }
    persona.value = list[0]   // 单人设:取第一个(唯一)
    form.value = {
      name: persona.value.name || '',
      description: persona.value.description || '',
      creator_notes: persona.value.creator_notes || '',
      user_description: persona.value.user_description || '',
      provider: persona.value.model?.provider || 'deepseek',
      model: persona.value.model?.model || '',
    }
  } catch (e: any) { message.error('加载失败: ' + e) }
  finally { loading.value = false }
}

async function save() {
  if (!persona.value) return
  saving.value = true
  try {
    await updatePersona(persona.value.id, {
      name: form.value.name, description: form.value.description,
      creator_notes: form.value.creator_notes, user_description: form.value.user_description,
    })
    await bindPersonaModel(persona.value.id, { provider: form.value.provider, model: form.value.model })
    message.success('已保存')
    await load()
  } catch (e: any) { message.error('保存失败: ' + e) }
  finally { saving.value = false }
}

onMounted(() => { load(); loadProviders() })
</script>

<template>
  <n-spin :show="loading">
    <n-space vertical size="large">
      <n-space align="center">
        <span style="font-weight:600">编辑人设</span>
        <span style="color:#999;font-size:12px">单人设模式(只编辑,不新建/删除)</span>
        <n-button @click="load" :loading="loading">刷新</n-button>
      </n-space>
      <n-form v-if="persona" label-placement="top" style="max-width:680px">
        <n-form-item label="名称"><n-input v-model:value="form.name" /></n-form-item>
        <!-- 长文本字段:紧凑预览(只读) + 展开编辑按钮 → 大窗口弹窗 -->
        <n-form-item v-for="lf in LONG_FIELDS" :key="lf.field" :label="lf.label">
          <n-space vertical style="width:100%" :size="6">
            <div style="font-size:12px;color:#999">{{ lf.hint }}</div>
            <n-space align="center" :wrap="false" style="width:100%">
              <n-input :value="(form as any)[lf.field]" type="textarea" :rows="2" readonly
                       placeholder="(空)" style="flex:1" />
              <n-button @click="openEdit(lf.field)">展开编辑</n-button>
            </n-space>
          </n-space>
        </n-form-item>
        <n-form-item label="模型 provider">
          <n-select v-model:value="form.provider" :options="providerOptions" placeholder="选择已配置的 provider" />
        </n-form-item>
        <n-form-item label="模型 model"><n-input v-model:value="form.model" placeholder="具体模型号(可空)" /></n-form-item>
        <n-space>
          <n-button type="primary" :loading="saving" @click="save">保存</n-button>
        </n-space>
      </n-form>
      <n-empty v-else description="无人设" />
    </n-space>
  </n-spin>

  <!-- 长文本大窗口编辑弹窗(统一服务三个长文本字段) -->
  <n-modal v-model:show="editShow" preset="card" :title="editLabel" style="width:760px;max-width:92vw">
    <n-space vertical :size="12">
      <n-input v-model:value="editValue" type="textarea" :rows="18" placeholder="请输入..." autofocus />
      <n-space justify="end">
        <n-button @click="editShow = false">取消</n-button>
        <n-button type="primary" @click="applyEdit">确定</n-button>
      </n-space>
    </n-space>
  </n-modal>
</template>
