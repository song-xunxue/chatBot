<script setup lang="ts">
/**
 * 代人聊天与反推（V1.2）：
 *   1) 代人聊天 A 模拟训练工作台（对象选择 + 单条录入 + 聊天框式气泡展示前后关系）
 *   2) 反推人设区（触发 reverseInfer 预览 diff → applyReverseInfer 落库合并）
 *   3) 代人聊天 B 实时接管区（对象选择 + 开关 + 待答列表轮询 + 选中代答）
 *   附：人格反推提案折叠区
 * 作者: 李文煜
 */
import { ref, onMounted, onUnmounted } from 'vue'
import {
  NSpace, NButton, NCard, NTag, NEmpty, NInput, NSelect, NSwitch, NCollapse, NCollapseItem, NPopconfirm,
  useMessage,
} from 'naive-ui'
import {
  listPersonas, getProposals, dismissProposal,
  listRoleplayMsgs, addRoleplaySingle, updateRoleplayMsg, deleteRoleplayMsg,
  reverseInfer, applyReverseInfer,
  takeoverToggle, takeoverStatus, takeoverPending, takeoverAnswer,
} from '@/api'

const message = useMessage()

// —— 共用对象选择 ——
const oid = ref<string | null>(null)
const msgs = ref<any[]>([])
const proposals = ref<any[]>([])
const role = ref('user')
const content = ref('')
const editing = ref<Record<string, string>>({})
const personaOptions = ref<{ label: string; value: string }[]>([])

const roleOptions = [
  { label: '用户 (user)', value: 'user' },
  { label: '角色 (assistant)', value: 'assistant' },
  { label: '系统 (system)', value: 'system' },
]

// —— 反推人设区状态 ——
const inferMode = ref<'fill_empty' | 'overwrite'>('fill_empty')
const inferModeOptions = [
  { label: '仅填空字段 (fill_empty)', value: 'fill_empty' },
  { label: '全覆盖 (overwrite)', value: 'overwrite' },
]
const inferLoading = ref(false)
const inferApplyLoading = ref(false)
const inferResult = ref<any>(null) // { diff, confirm_token, positive_count, negative_count, aborted_reason? }

// —— 代人聊天 B 实时接管区状态 ——
const tOid = ref<string | null>(null)
const tEnabled = ref(false)
const tActivePending = ref<string | null>(null)
const tEnabledLoading = ref(false)
const pending = ref<any[]>([])
const selPending = ref<any | null>(null)
const answerText = ref('')
const answerLoading = ref(false)
let pollTimer: number | null = null

async function loadPersonas() {
  const list = await listPersonas()
  personaOptions.value = list.map((p: any) => ({ label: `${p.name} (${p.id})`, value: p.id }))
}
async function loadMsgs() {
  if (!oid.value) return
  try { msgs.value = (await listRoleplayMsgs(oid.value)).messages } catch (e: any) { message.error('' + e) }
}
async function loadProposals() {
  try { proposals.value = (await getProposals()).proposals } catch (e: any) { message.error('' + e) }
}
onMounted(async () => {
  await loadPersonas()
  await loadProposals()
  startPolling()
})
onUnmounted(() => { stopPolling() })

async function addOne() {
  if (!oid.value) { message.warning('请先选择对象'); return }
  if (!content.value.trim()) { message.warning('内容不能为空'); return }
  try {
    await addRoleplaySingle(oid.value, { role: role.value, content: content.value })
    content.value = ''
    loadMsgs()
  } catch (e: any) { message.error('' + e) }
}
function startEdit(m: any) { editing.value[m.mid] = m.content }
async function saveEdit(m: any) {
  try { await updateRoleplayMsg(oid.value!, m.mid, { content: editing.value[m.mid] }); message.success('已改'); delete editing.value[m.mid]; loadMsgs() }
  catch (e: any) { message.error('' + e) }
}
async function del(m: any) {
  try { await deleteRoleplayMsg(oid.value!, m.mid); message.success('已删（记负样本）'); loadMsgs() }
  catch (e: any) { message.error('' + e) }
}
async function dismiss(oid2: string) {
  try { await dismissProposal(oid2); message.success('已忽略'); loadProposals() }
  catch (e: any) { message.error('' + e) }
}

// —— 反推人设 ——
async function runInfer() {
  if (!oid.value) { message.warning('请先选择对象'); return }
  inferLoading.value = true
  inferResult.value = null
  try {
    const res = await reverseInfer(oid.value, inferMode.value)
    inferResult.value = res
    if (res.aborted_reason) {
      message.warning('反推中止：' + res.aborted_reason)
    } else {
      message.success(`反推完成：正样本 ${res.positive_count ?? 0} / 负样本 ${res.negative_count ?? 0}`)
    }
  } catch (e: any) { message.error('' + e) } finally { inferLoading.value = false }
}
async function applyInfer() {
  if (!inferResult.value?.confirm_token) { message.warning('无 confirm_token'); return }
  inferApplyLoading.value = true
  try {
    const res = await applyReverseInfer(oid.value!, inferResult.value.confirm_token)
    if (res.aborted_reason) { message.error('应用失败：' + res.aborted_reason); return }
    message.success('已合并到人设')
    inferResult.value = null
  } catch (e: any) { message.error('' + e) } finally { inferApplyLoading.value = false }
}

// —— 代人聊天 B 接管 ——
async function onTOidChange() {
  if (!tOid.value) { tEnabled.value = false; tActivePending.value = null; return }
  await loadTStatus()
}
async function loadTStatus() {
  if (!tOid.value) return
  try {
    const res = await takeoverStatus(tOid.value)
    tEnabled.value = !!res.enabled
    tActivePending.value = res.active_pending ?? null
  } catch (e: any) { message.error('' + e) }
}
async function onTSwitch(enabled: boolean) {
  if (!tOid.value) { message.warning('请先选择对象'); return }
  tEnabledLoading.value = true
  try {
    await takeoverToggle(tOid.value, enabled)
    tEnabled.value = enabled
    message.success(enabled ? '已开启代人接管' : '已关闭代人接管')
  } catch (e: any) {
    message.error('' + e)
    await loadTStatus() // 回滚开关显示
  } finally { tEnabledLoading.value = false }
}
function startPolling() {
  if (pollTimer) return
  pollTimer = window.setInterval(refreshPending, 3000)
}
function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}
async function refreshPending() {
  try {
    pending.value = (await takeoverPending()).requests ?? []
    // 选中项若已不在列表，清空
    if (selPending.value && !pending.value.some((p) => p.pending_id === selPending.value.pending_id)) {
      selPending.value = null
      answerText.value = ''
    }
  } catch { /* 静默，轮询不弹错 */ }
}
function pickPending(p: any) {
  selPending.value = p
  answerText.value = ''
}
async function submitAnswer() {
  if (!selPending.value) { message.warning('请先选中一条待答'); return }
  if (!answerText.value.trim()) { message.warning('代答内容不能为空'); return }
  answerLoading.value = true
  try {
    const res = await takeoverAnswer(selPending.value.object_id, selPending.value.pending_id, answerText.value)
    message.success(`已代答（发出 ${res.sent ?? 0} 客户端）`)
    selPending.value = null
    answerText.value = ''
    await refreshPending()
  } catch (e: any) {
    // 410 pending 失效
    const detail = e?.response?.data?.detail || '' + e
    message.error(/410|expired|invalid/i.test(detail) ? '该待答已过期，请重新选择' : detail)
    selPending.value = null
    answerText.value = ''
    await refreshPending()
  } finally { answerLoading.value = false }
}
</script>

<template>
  <n-space vertical size="large">
    <!-- 1) 代人聊天 A 模拟训练工作台 -->
    <n-card title="① 代人聊天 A · 模拟训练工作台" size="small">
      <n-space vertical>
        <n-space align="center">
          <span>聊天对象：</span>
          <n-select v-model:value="oid" :options="personaOptions" placeholder="选择对象（需已绑定）" style="width: 320px" @update:value="loadMsgs" />
          <n-button @click="loadMsgs" :disabled="!oid">刷新对话</n-button>
        </n-space>
        <n-space vertical v-if="oid">
          <n-space align="center">
            <span>发言方：</span>
            <n-select v-model:value="role" :options="roleOptions" style="width: 200px" />
          </n-space>
          <n-input v-model:value="content" type="textarea" placeholder="输入这一条的内容（可连续添加多条同一方，再换另一方回复）" :autosize="{ minRows: 2 }" />
          <n-button type="primary" @click="addOne">添加这条</n-button>
        </n-space>
      </n-space>
    </n-card>

    <!-- V1.2 聊天框式气泡展示前后关系 -->
    <n-card v-if="oid" title="对话（聊天框式，可改/删）" size="small">
      <n-empty v-if="!msgs.length" description="暂无对话，在上方逐条添加" />
      <div v-for="m in msgs" :key="m.mid" :style="{ display:'flex', justifyContent: m.role==='user' ? 'flex-end' : 'flex-start', margin:'6px 0' }">
        <div :style="{ maxWidth:'70%', padding:'8px 12px', borderRadius:'12px',
          background: m.role==='user' ? '#DCF8C6' : (m.role==='system' ? '#f0f0f0' : '#E8F1FF'),
          color:'#222', wordBreak:'break-all' }">
          <div style="font-size:11px;color:#888;margin-bottom:2px">{{ m.role === 'user' ? '用户' : (m.role === 'system' ? '系统' : '角色') }}</div>
          <div v-if="editing[m.mid] === undefined">{{ m.content }}</div>
          <div v-else>
            <n-input v-model:value="editing[m.mid]" type="textarea" :autosize="{ minRows:1, maxRows:4 }" />
            <n-space style="margin-top:4px">
              <n-button size="tiny" type="primary" @click="saveEdit(m)">保存</n-button>
              <n-button size="tiny" @click="delete editing[m.mid]">取消</n-button>
            </n-space>
          </div>
          <n-space style="margin-top:4px" v-if="editing[m.mid] === undefined">
            <n-button size="tiny" @click="startEdit(m)">改</n-button>
            <n-popconfirm @positive-click="del(m)"><template #trigger><n-button size="tiny" type="error" ghost>删</n-button></template>删除并记为负样本？</n-popconfirm>
          </n-space>
        </div>
      </div>
    </n-card>

    <!-- 2) 反推人设区 -->
    <n-card title="② 反推人设（预览 diff → 应用合并）" size="small">
      <n-space vertical>
        <n-space align="center">
          <span>反推对象：</span>
          <n-select v-model:value="oid" :options="personaOptions" placeholder="选择对象" style="width: 320px" />
        </n-space>
        <n-space align="center">
          <span>合并模式：</span>
          <n-select v-model:value="inferMode" :options="inferModeOptions" style="width: 260px" />
          <n-button type="primary" :loading="inferLoading" :disabled="!oid" @click="runInfer">触发反推</n-button>
        </n-space>
        <template v-if="inferResult">
          <div v-if="inferResult.aborted_reason" style="color:#d03050">
            反推中止：{{ inferResult.aborted_reason }}
            <span style="color:#888;font-size:12px">（如：无正样本 / 无可用 provider）</span>
          </div>
          <template v-else>
            <div style="font-size:13px;color:#666">
              正样本 {{ inferResult.positive_count ?? 0 }} / 负样本 {{ inferResult.negative_count ?? 0 }} · 可合并字段如下：
            </div>
            <n-empty v-if="!inferResult.diff || !Object.keys(inferResult.diff).length" description="无差异需合并" />
            <div v-for="(d, field) in inferResult.diff" :key="field" style="margin:6px 0;padding:8px;border:1px solid #eee;border-radius:6px">
              <n-space align="center">
                <n-tag size="small" type="info">{{ field }}</n-tag>
                <n-tag size="small" :type="inferMode === 'overwrite' ? 'warning' : 'success'">{{ d.action }}</n-tag>
              </n-space>
              <div style="margin-top:4px;font-size:13px;wordBreak:break-all">
                <span style="color:#999;text-decoration:line-through">{{ d.old ?? '（空）' }}</span>
                <span style="margin:0 6px;color:#888">→</span>
                <span style="color:#18a058">{{ d.new ?? '（空）' }}</span>
              </div>
            </div>
            <n-button type="primary" :loading="inferApplyLoading" @click="applyInfer">应用合并</n-button>
          </template>
        </template>
      </n-space>
    </n-card>

    <!-- 3) 代人聊天 B 实时接管区 -->
    <n-card title="③ 代人聊天 B · 实时接管" size="small">
      <n-space vertical>
        <n-space align="center">
          <span>接管对象：</span>
          <n-select v-model:value="tOid" :options="personaOptions" placeholder="选择对象" style="width: 320px" @update:value="onTOidChange" />
          <span>代人开关：</span>
          <n-switch :value="tEnabled" :loading="tEnabledLoading" @update:value="onTSwitch" />
          <span v-if="tEnabled && tActivePending" style="color:#f0a020;font-size:12px">当前 active pending：{{ tActivePending }}</span>
        </n-space>

        <div>
          <div style="font-weight:600;margin-bottom:6px">待答列表（每 3 秒自动刷新）</div>
          <n-empty v-if="!pending.length" description="暂无待答请求" />
          <div v-for="p in pending" :key="p.pending_id"
            :style="{ padding:'8px', margin:'4px 0', borderRadius:'6px', cursor:'pointer', border:'1px solid',
              borderColor: selPending?.pending_id === p.pending_id ? '#18a058' : '#eee',
              background: selPending?.pending_id === p.pending_id ? '#f3fff7' : '#fff' }"
            @click="pickPending(p)">
            <n-space align="center">
              <n-tag size="small" type="info">{{ p.object_id }}</n-tag>
              <n-tag size="small">{{ p.pending_id }}</n-tag>
              <span style="font-size:12px;color:#999">{{ p.created_ts }}</span>
            </n-space>
            <div style="margin-top:4px;wordBreak:break-all">{{ p.user_text }}</div>
          </div>
        </div>

        <div v-if="selPending">
          <div style="font-size:13px;color:#666;margin-bottom:4px">
            代答对象 {{ selPending.object_id }} · 待答 {{ selPending.pending_id }}
          </div>
          <n-input v-model:value="answerText" type="textarea" placeholder="输入代答内容" :autosize="{ minRows: 2 }" />
          <n-space style="margin-top:6px">
            <n-button type="primary" :loading="answerLoading" @click="submitAnswer">提交代答</n-button>
            <n-button @click="selPending = null; answerText = ''">取消选择</n-button>
          </n-space>
        </div>
      </n-space>
    </n-card>

    <!-- 附：人格反推提案折叠区 -->
    <n-collapse>
      <n-collapse-item title="人格反推提案（删除负样本，待反推合并）" name="prop">
        <n-empty v-if="!proposals.length" description="暂无提案" />
        <n-card v-for="p in proposals" :key="p.object_id" :title="`对象 ${p.object_id}`" size="small" style="margin-bottom:8px">
          <div v-for="(s, i) in p.samples" :key="i" style="margin:4px 0">
            <n-tag size="small" type="warning">{{ s.reason }}</n-tag>
            <span style="margin-left:8px">{{ s.text }}</span>
          </div>
          <template #footer>
            <n-button size="small" type="error" ghost @click="dismiss(p.object_id)">忽略</n-button>
          </template>
        </n-card>
      </n-collapse-item>
    </n-collapse>
  </n-space>
</template>
