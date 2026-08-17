<script setup lang="ts">
/**
 * 人设管理(V2.0 简化 2026-07-04;2026-07-05 改造;2026-07-06 B-5 字段暴露+反推查看):
 * 单人设模式(只编辑) + 长文本弹窗大窗口编辑 + 暴露 personality/scenario/speech_style/catchphrase
 *   (这些字段反推会写,但原面板看不到 → 设计断层;现补暴露) +
 * 人设反推预览/应用(reverse_infer dry_run/apply,展示字段 diff 旧值→新值,给应用/放弃按钮)。
 * 作者: 李文煜
 */
import { ref, onMounted, computed } from 'vue'
import {
  NButton, NSpace, NForm, NFormItem, NInput, NSelect, NSpin, NEmpty, NModal, NGrid, NGi, NTag, useMessage,
} from 'naive-ui'
import {
  listPersonas, updatePersona, bindPersonaModel, getSystemConfig,
  reverseInferDryRun, reverseInferApply,
} from '@/api'
import { useObject } from '@/composables/useObject'

const message = useMessage()
const { oid, ensureOid } = useObject()
const loading = ref(false)
const saving = ref(false)
const persona = ref<any>(null)   // 当前唯一人设(单人设)
const form = ref({
  name: '', description: '', creator_notes: '', user_description: '', user_alias: '',
  personality: '', scenario: '', speech_style: '', catchphrase: '',
  provider: 'deepseek', model: '',
})
const providers = ref<{ name: string; configured: boolean }[]>([])

// —— 长文本字段定义(预览+展开编辑);speech_style/catchphrase 存 profile 嵌套,form 扁平化 ——
const LONG_FIELDS: { field: string; label: string; hint: string }[] = [
  { field: 'creator_notes', label: '创作备注(核心人设指令)', hint: '最核心的人设指令,决定 AI 行为准则(输出硬规矩写这里)' },
  { field: 'personality', label: '性格', hint: '人物性格(反推常改此字段 → 渲染【性格】段)' },
  { field: 'speech_style', label: '说话风格', hint: '语气/用词习惯(反推常改 → 渲染【人物画像】段)' },
  { field: 'description', label: '描述(背景设定)', hint: '背景故事 / 世界观设定' },
  { field: 'scenario', label: '场景示例', hint: '场景设定(反推可改 → 渲染【场景示例】段)' },
  { field: 'user_description', label: '关于用户(你)', hint: '对话另一方(你)的特征,让人设更熟悉你' },
  { field: 'user_alias', label: '对用户的称呼', hint: '角色怎么称呼对方(如"煜君");自动从对话学,这里可手动改,renderer/记忆用它代"用户"更拟人' },
  { field: 'catchphrase', label: '口头禅', hint: '标志性短语(渲染【人物画像】段)' },
]

// —— 长文本统一编辑弹窗 ——
const editShow = ref(false)
const editField = ref<string>('description')
const editLabel = ref('')
const editValue = ref('')

function openEdit(field: string) {
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
    const p = persona.value
    form.value = {
      name: p.name || '',
      description: p.description || '',
      creator_notes: p.creator_notes || '',
      user_description: p.user_description || '',
      user_alias: p.user_alias || '',
      personality: p.personality || '',                 // B-5a 顶层字段
      scenario: p.scenario || '',                       // B-5a 顶层字段
      speech_style: p.profile?.speech_style || '',      // B-5a profile 嵌套
      catchphrase: p.profile?.catchphrase || '',        // B-5a profile 嵌套
      provider: p.model?.provider || 'deepseek',
      model: p.model?.model || '',
    }
  } catch (e: any) { message.error('加载失败: ' + e) }
  finally { loading.value = false }
}

async function save() {
  if (!persona.value) return
  saving.value = true
  try {
    // 顶层字段 + profile 嵌套(speech_style/catchphrase;后端 update_persona 字段级合并,不覆盖其他 profile 字段)
    await updatePersona(persona.value.id, {
      name: form.value.name, description: form.value.description,
      creator_notes: form.value.creator_notes, user_description: form.value.user_description,
      user_alias: form.value.user_alias,
      personality: form.value.personality, scenario: form.value.scenario,
      profile: { speech_style: form.value.speech_style, catchphrase: form.value.catchphrase },
    })
    await bindPersonaModel(persona.value.id, { provider: form.value.provider, model: form.value.model })
    message.success('已保存')
    await load()
  } catch (e: any) { message.error('保存失败: ' + e) }
  finally { saving.value = false }
}

// ===== B-5b 人设反推:预览 diff + 应用 =====
const reverseLoading = ref(false)
const reverseShow = ref(false)
const reverseResult = ref<any>(null)
// diff 字段名 → 中文标签(反推白名单字段)
const fieldLabels: Record<string, string> = {
  personality: '性格', speech_style: '说话风格', catchphrase: '口头禅',
  scenario: '场景示例', description: '描述', age: '年龄', gender: '性别',
  occupation: '职业', appearance: '外貌', race: '种族',
  likes: '喜欢', dislikes: '厌恶', relationship: '关系', greeting: '开场白',
}

async function doReverseDryRun() {
  const object_id = await ensureOid()
  if (!object_id || object_id === 'default') {
    message.warning('无有效会话 object_id(先在 QQ 产生对话产生评分样本,再来反推)'); return
  }
  reverseLoading.value = true
  try {
    // fill_empty:只填空字段,不覆盖用户已填(安全);想强制覆盖改 'overwrite'
    const res: any = await reverseInferDryRun(object_id, { mode: 'fill_empty' })
    if (res.aborted_reason) {
      message.warning('反推未执行: ' + res.aborted_reason
        + (res.aborted_reason === 'no_samples' ? '(评分样本不足,先多对话并评分)' : ''))
      return
    }
    reverseResult.value = res
    reverseShow.value = true
  } catch (e: any) { message.error('反推预览失败: ' + e) }
  finally { reverseLoading.value = false }
}

async function doReverseApply() {
  if (!reverseResult.value?.confirm_token) return
  try {
    await reverseInferApply(oid.value, reverseResult.value.confirm_token)
    message.success('已应用反推,人设字段已更新')
    reverseShow.value = false
    reverseResult.value = null
    await load()   // 刷新显示反推后的字段值
  } catch (e: any) { message.error('反推应用失败: ' + e) }
}

onMounted(() => { load(); loadProviders() })
</script>

<template>
  <n-spin :show="loading">
    <n-space vertical size="large">
      <n-space align="center">
        <span style="font-weight:600">编辑人设</span>
        <span style="color:#999;font-size:12px">单人设模式</span>
        <n-button @click="load" :loading="loading">刷新</n-button>
      </n-space>
      <n-form v-if="persona" label-placement="top" style="max-width:720px">
        <!-- 名称:短输入限宽 -->
        <n-form-item label="名称">
          <n-input v-model:value="form.name" style="max-width:320px" />
        </n-form-item>
        <!-- 长文本字段:大预览(只读整宽 rows=3) + 展开编辑按钮 -->
        <n-form-item v-for="lf in LONG_FIELDS" :key="lf.field" :label="lf.label">
          <div style="width:100%">
            <div style="font-size:12px;color:#999;margin-bottom:6px">{{ lf.hint }}</div>
            <n-input :value="(form as any)[lf.field]" type="textarea" :rows="3" readonly
                     placeholder="(空)" style="width:100%" />
            <div style="text-align:right;margin-top:6px">
              <n-button size="small" @click="openEdit(lf.field)">展开编辑</n-button>
            </div>
          </div>
        </n-form-item>
        <!-- 模型 provider + model:一行两列 -->
        <n-grid :cols="2" :x-gap="16">
          <n-gi>
            <n-form-item label="模型 provider">
              <n-select v-model:value="form.provider" :options="providerOptions" placeholder="选择已配置的 provider" />
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="模型 model">
              <n-input v-model:value="form.model" placeholder="具体模型号(可空)" />
            </n-form-item>
          </n-gi>
        </n-grid>
        <n-space align="center">
          <n-button type="primary" :loading="saving" @click="save">保存</n-button>
          <!-- B-5b 人设反推入口 -->
          <n-button :loading="reverseLoading" @click="doReverseDryRun">人设反推(基于评分样本)</n-button>
          <span style="color:#999;font-size:12px">会话: {{ oid }}</span>
        </n-space>
      </n-form>
      <n-empty v-else description="无人设" />
    </n-space>
  </n-spin>

  <!-- 长文本大窗口编辑弹窗(统一服务所有长文本字段) -->
  <n-modal v-model:show="editShow" preset="card" :title="editLabel" style="width:760px;max-width:92vw">
    <n-space vertical :size="12">
      <n-input v-model:value="editValue" type="textarea" :rows="18" placeholder="请输入..." autofocus />
      <n-space justify="end">
        <n-button @click="editShow = false">取消</n-button>
        <n-button type="primary" @click="applyEdit">确定</n-button>
      </n-space>
    </n-space>
  </n-modal>

  <!-- B-5b 反推 diff 预览弹窗 -->
  <n-modal v-model:show="reverseShow" preset="card" title="人设反推预览(评分样本驱动)" style="width:820px;max-width:94vw">
    <n-space vertical :size="12" v-if="reverseResult">
      <div style="font-size:13px;color:#666">
        正样本 {{ reverseResult.positive_count || 0 }} 条 / 负样本 {{ reverseResult.negative_count || 0 }} 条
        <span style="color:#999;margin-left:8px">(token 10 分钟内有效,应用后即消费)</span>
      </div>
      <n-empty v-if="!reverseResult.diff || !Object.keys(reverseResult.diff).length"
               description="无字段需要变更(字段已填或样本不足)" />
      <div v-else>
        <div v-for="(d, field) in reverseResult.diff" :key="field"
             style="margin-bottom:14px;padding:10px;border:1px solid #eee;border-radius:6px">
          <n-space align="center" :size="8">
            <n-tag type="info">{{ fieldLabels[field as string] || (field as string) }}</n-tag>
            <span style="font-size:12px;color:#999">{{ field }}</span>
          </n-space>
          <div style="margin-top:8px;display:flex;gap:12px;font-size:13px">
            <div style="flex:1">
              <div style="color:#999;margin-bottom:4px">旧值</div>
              <div style="background:#fafafa;padding:6px 8px;border-radius:4px;white-space:pre-wrap;min-height:24px">{{ d.old || '(空)' }}</div>
            </div>
            <div style="display:flex;align-items:center;color:#999">→</div>
            <div style="flex:1">
              <div style="color:#999;margin-bottom:4px">新值</div>
              <div style="background:#f0f9eb;padding:6px 8px;border-radius:4px;white-space:pre-wrap">{{ d.new }}</div>
            </div>
          </div>
        </div>
      </div>
      <n-space justify="end">
        <n-button @click="reverseShow = false">放弃</n-button>
        <n-button type="primary" @click="doReverseApply">应用并保存</n-button>
      </n-space>
    </n-space>
  </n-modal>
</template>
