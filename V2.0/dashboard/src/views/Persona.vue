<script setup lang="ts">
/**
 * 人设管理(V2.0 简化 2026-07-04):单人设模式(只有 1 个人设、以后也是),
 * 去掉新建/删除/导入/多人设切换,固定编辑当前唯一人设 + 模型绑定。
 * 底层 persona/store 多 pid 结构保留(pipeline 解析依赖);仅 UI/REST 简化(去 create/delete/import)。
 * 作者: 李文煜
 */
import { ref, onMounted, computed } from 'vue'
import { NButton, NSpace, NForm, NFormItem, NInput, NSelect, NSpin, NTag, NEmpty, useMessage } from 'naive-ui'
import { listPersonas, updatePersona, bindPersonaModel, getSystemConfig } from '@/api'

const message = useMessage()
const loading = ref(false)
const saving = ref(false)
const persona = ref<any>(null)   // 当前唯一人设(单人设)
const form = ref({ name: '', description: '', creator_notes: '', provider: 'deepseek', model: '' })
const providers = ref<{ name: string; configured: boolean }[]>([])

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
      name: form.value.name, description: form.value.description, creator_notes: form.value.creator_notes,
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
        <n-tag v-if="persona" size="small" :bordered="false">ID: {{ persona.id }}</n-tag>
        <span style="color:#999;font-size:12px">单人设模式(只编辑,不新建/删除)</span>
        <n-button @click="load" :loading="loading">刷新</n-button>
      </n-space>
      <n-form v-if="persona" label-placement="top" style="max-width:560px">
        <n-form-item label="名称"><n-input v-model:value="form.name" /></n-form-item>
        <n-form-item label="描述"><n-input v-model:value="form.description" type="textarea" /></n-form-item>
        <n-form-item label="创作备注 creator_notes"><n-input v-model:value="form.creator_notes" type="textarea" /></n-form-item>
        <n-form-item label="模型 provider"><n-select v-model:value="form.provider" :options="providerOptions" placeholder="选择已配置的 provider" /></n-form-item>
        <n-form-item label="模型 model"><n-input v-model:value="form.model" placeholder="具体模型号(可空)" /></n-form-item>
        <n-space>
          <n-button type="primary" :loading="saving" @click="save">保存</n-button>
        </n-space>
      </n-form>
      <n-empty v-else description="无人设" />
    </n-space>
  </n-spin>
</template>
