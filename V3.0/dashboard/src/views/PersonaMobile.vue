<script setup lang="ts">
/**
 * 移动端人设管理(功能对等 PC Persona.vue,窄屏重排):
 * ① 人设卡查看/编辑:名称 + 8 个长文本字段(creator_notes/personality/speech_style/description/
 *    scenario/user_description/user_alias/catchphrase)折叠收纳,展开后预览+统一弹窗大窗口编辑
 * ② 保存(PUT persona 嵌套 profile 字段级合并 + provider/model 绑定)
 * ③ 人设反推(dry_run 展示字段 diff 旧值→新值 + 应用/放弃;diff 上下堆叠替代 PC 左右分栏)
 * ④ provider/model 绑定为低频配置,折叠置底(参照 TakeoverMobile 的 TTS 折叠)
 * 人设为全局单人设,listPersonas/getSystemConfig 不依赖会话 oid(oid 仅反推入口校验,照 PC);
 * PC 端无轮询,本页同样不轮询。鉴权:router 守卫跳登录 + axios 拦截器注入 X-Access-Token。
 * 作者: 李文煜
 */
import { ref, onMounted, computed, watch } from 'vue'
import {
  NButton, NSpace, NInput, NSelect, NSpin, NEmpty, NModal, NTag,
  NCard, NCollapse, NCollapseItem, useMessage,
} from 'naive-ui'
import {
  listPersonas, updatePersona, bindPersonaModel, getSystemConfig,
  reverseInferDryRun, reverseInferApply,
} from '@/api'
import { useObject } from '@/composables/useObject'

const message = useMessage()
const { oid, reloadTick, ensureOid } = useObject()
watch(reloadTick, () => load())

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

// 人设为全局单人设,listPersonas 不依赖会话 oid(反推才需要,入口处校验),故不做 oid 拦截
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

onMounted(async () => {
  await ensureOid()
  await load()
  loadProviders()
})
</script>

<template>
  <n-spin :show="loading">
    <n-space vertical size="medium">
      <!-- 顶栏:标题 + 单人设标记 + 刷新 -->
      <div class="m-topbar">
        <div class="m-topbar-left">
          <span class="m-title">编辑人设</span>
          <n-tag size="small">单人设</n-tag>
        </div>
        <n-button size="small" quaternary :loading="loading" @click="load">刷新</n-button>
      </div>

      <template v-if="persona">
        <!-- 名称:短字段,直接编辑(全宽,textarea autosize 单行起步) -->
        <n-card title="名称">
          <n-input v-model:value="form.name" type="textarea" :autosize="{ minRows: 1, maxRows: 2 }" placeholder="人设名称" />
        </n-card>

        <!-- 长文本字段:折叠收纳(8 项,默认展开最核心的创作备注);展开后预览 + 弹窗编辑 -->
        <n-collapse :default-expanded-names="['creator_notes']">
          <n-collapse-item v-for="lf in LONG_FIELDS" :key="lf.field" :name="lf.field">
            <template #header>
              <span class="m-field-title">{{ lf.label }}</span>
              <n-tag size="tiny" :type="(form as any)[lf.field] ? 'success' : 'default'">
                {{ (form as any)[lf.field] ? '已填' : '空' }}
              </n-tag>
            </template>
            <div class="m-hint" style="margin-bottom:6px">{{ lf.hint }}</div>
            <n-input :value="(form as any)[lf.field]" type="textarea" :autosize="{ minRows: 2, maxRows: 8 }"
                     readonly placeholder="(空)" />
            <n-button size="large" block style="margin-top:8px" @click="openEdit(lf.field)">展开编辑</n-button>
          </n-collapse-item>
        </n-collapse>

        <!-- 模型绑定:低频配置折叠置底;PC 两列改上下堆叠 -->
        <n-collapse>
          <n-collapse-item title="模型绑定(provider / model)" name="model">
            <div class="m-label">模型 provider</div>
            <n-select v-model:value="form.provider" size="large" :options="providerOptions"
                      placeholder="选择已配置的 provider" />
            <div class="m-label" style="margin-top:12px">模型 model</div>
            <n-input v-model:value="form.model" type="textarea" :autosize="{ minRows: 1, maxRows: 2 }"
                     placeholder="具体模型号(可空)" />
          </n-collapse-item>
        </n-collapse>

        <!-- 操作区:保存(主) + 人设反推 -->
        <n-space vertical size="small">
          <n-button type="primary" size="large" block :loading="saving" @click="save">保存</n-button>
          <n-button size="large" block :loading="reverseLoading" @click="doReverseDryRun">人设反推(基于评分样本)</n-button>
          <div class="m-hint">反推会话: {{ oid || '—' }}</div>
        </n-space>
      </template>
      <n-empty v-else description="无人设" />
    </n-space>
  </n-spin>

  <!-- 长文本大窗口编辑弹窗(统一服务所有长文本字段,窄屏全宽可滚动) -->
  <n-modal v-model:show="editShow" preset="card" :title="editLabel" style="width:94vw"
           content-style="max-height:70vh;overflow-y:auto">
    <n-space vertical :size="12">
      <n-input v-model:value="editValue" type="textarea" :autosize="{ minRows: 8, maxRows: 12 }" placeholder="请输入..." autofocus />
      <n-space>
        <n-button size="large" style="flex:1" @click="editShow = false">取消</n-button>
        <n-button size="large" type="primary" style="flex:1" @click="applyEdit">确定</n-button>
      </n-space>
    </n-space>
  </n-modal>

  <!-- 人设反推 diff 预览弹窗(旧值→新值上下堆叠,替代 PC 左右分栏) -->
  <n-modal v-model:show="reverseShow" preset="card" title="人设反推预览(评分样本驱动)" style="width:94vw"
           content-style="max-height:70vh;overflow-y:auto">
    <n-space vertical :size="12" v-if="reverseResult">
      <div class="m-hint">
        正样本 {{ reverseResult.positive_count || 0 }} 条 / 负样本 {{ reverseResult.negative_count || 0 }} 条
        (token 10 分钟内有效,应用后即消费)
      </div>
      <n-empty v-if="!reverseResult.diff || !Object.keys(reverseResult.diff).length"
               description="无字段需要变更(字段已填或样本不足)" />
      <div v-else>
        <div v-for="(d, field) in reverseResult.diff" :key="field" class="m-diff-card">
          <n-space align="center" :size="8">
            <n-tag type="info" size="small">{{ fieldLabels[field as string] || (field as string) }}</n-tag>
            <span class="m-field-name">{{ field }}</span>
          </n-space>
          <div style="margin-top:8px">
            <div class="m-diff-label">旧值</div>
            <div class="m-old-val">{{ d.old || '(空)' }}</div>
          </div>
          <div class="m-arrow">↓ 变为</div>
          <div>
            <div class="m-diff-label">新值</div>
            <div class="m-new-val">{{ d.new }}</div>
          </div>
        </div>
      </div>
      <n-space>
        <n-button size="large" style="flex:1" @click="reverseShow = false">放弃</n-button>
        <n-button size="large" type="primary" style="flex:1" @click="doReverseApply">应用并保存</n-button>
      </n-space>
    </n-space>
  </n-modal>
</template>

<style scoped>
.m-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.m-topbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.m-title {
  font-weight: 600;
  font-size: 16px;
}
.m-field-title {
  font-size: 14px;
}
.m-label {
  font-size: 13px;
}
.m-hint {
  font-size: 11px;
  color: #999;
}
.m-field-name {
  font-size: 12px;
  color: #999;
}
.m-diff-card {
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 10px;
  margin-bottom: 14px;
}
.m-diff-label {
  font-size: 12px;
  color: #999;
  margin-bottom: 4px;
}
.m-old-val {
  background: #fafafa;
  padding: 6px 8px;
  border-radius: 4px;
  white-space: pre-wrap;
  word-break: break-all;
  min-height: 24px;
  font-size: 13px;
}
.m-new-val {
  background: #f0f9eb;
  padding: 6px 8px;
  border-radius: 4px;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 13px;
}
.m-arrow {
  text-align: center;
  color: #999;
  font-size: 12px;
  margin: 6px 0;
}
</style>
