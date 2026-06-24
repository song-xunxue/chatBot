<script setup lang="ts">
/**
 * 代人聊天 A（V1.2）：单条录入（选角色，可连续多条同角色后再回复）+ 聊天框式气泡展示前后关系
 * + 触发反推（M12 两步预览）+ 折叠的人格反推提案
 * 作者: 李文煜
 */
import { ref, onMounted } from 'vue'
import {
  NSpace, NButton, NCard, NTag, NEmpty, NInput, NSelect, NCollapse, NCollapseItem, NPopconfirm,
  useMessage,
} from 'naive-ui'
import {
  listPersonas, getProposals, dismissProposal,
  listRoleplayMsgs, addRoleplaySingle, updateRoleplayMsg, deleteRoleplayMsg,
} from '@/api'

const message = useMessage()
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
onMounted(async () => { await loadPersonas(); await loadProposals() })

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
</script>

<template>
  <n-space vertical size="large">
    <n-card title="模拟训练工作台" size="small">
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

    <n-collapse>
      <n-collapse-item title="人格反推提案（删除负样本，待 M12 反推合并）" name="prop">
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
