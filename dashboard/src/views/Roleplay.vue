<script setup lang="ts">
/**
 * 代人聊天 A：面板模拟训练工作台（V1.1 M11）
 * 选对象 → 录 user/assistant 对话 → 列表增改删（自主编辑改善）→ 积累供反推
 * + 折叠的 persona_evolve 提案区（M4.4 删除负样本，待 M12 反推）
 * 作者: 李文煜
 */
import { ref, onMounted } from 'vue'
import {
  NSpace, NButton, NCard, NTag, NEmpty, NInput, NSelect, NCollapse, NCollapseItem,
  useMessage,
} from 'naive-ui'
import {
  listPersonas, getProposals, dismissProposal,
  listRoleplayMsgs, addRoleplayMsg, updateRoleplayMsg, deleteRoleplayMsg,
} from '@/api'

const message = useMessage()
const oid = ref<string | null>(null)
const msgs = ref<any[]>([])
const proposals = ref<any[]>([])
const userText = ref('')
const assistantText = ref('')
const editing = ref<Record<string, string>>({})   // mid -> 编辑内容
const personaOptions = ref<{ label: string; value: string }[]>([])

async function loadPersonas() {
  const list = await listPersonas()
  personaOptions.value = list.map((p: any) => ({ label: `${p.name} (${p.id})`, value: p.id }))
}
async function loadMsgs() {
  if (!oid.value) return
  try {
    msgs.value = (await listRoleplayMsgs(oid.value)).messages
  } catch (e: any) {
    message.error('' + e)
  }
}
async function loadProposals() {
  try {
    proposals.value = (await getProposals()).proposals
  } catch (e: any) {
    message.error('' + e)
  }
}
onMounted(async () => {
  await loadPersonas()
  await loadProposals()
})

async function addPair() {
  if (!oid.value) { message.warning('请先选择对象'); return }
  if (!userText.value.trim() || !assistantText.value.trim()) {
    message.warning('用户消息和角色回复都要填'); return
  }
  try {
    await addRoleplayMsg(oid.value, { user_text: userText.value, assistant_text: assistantText.value })
    message.success('已录入')
    userText.value = ''
    assistantText.value = ''
    loadMsgs()
  } catch (e: any) {
    message.error('' + e)
  }
}
async function saveEdit(mid: string) {
  try {
    await updateRoleplayMsg(oid.value!, mid, { content: editing.value[mid] })
    message.success('已改')
    delete editing.value[mid]
    loadMsgs()
  } catch (e: any) {
    message.error('' + e)
  }
}
async function del(mid: string) {
  try {
    await deleteRoleplayMsg(oid.value!, mid)
    message.success('已删（记为负样本）')
    loadMsgs()
  } catch (e: any) {
    message.error('' + e)
  }
}
async function dismiss(oid2: string) {
  try {
    await dismissProposal(oid2)
    message.success('已忽略')
    loadProposals()
  } catch (e: any) {
    message.error('' + e)
  }
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
          <n-input v-model:value="userText" type="textarea" placeholder="用户说什么" :autosize="{ minRows: 2 }" />
          <n-input v-model:value="assistantText" type="textarea" placeholder="角色该回什么" :autosize="{ minRows: 2 }" />
          <n-button type="primary" @click="addPair">录入这对对话</n-button>
        </n-space>
      </n-space>
    </n-card>

    <n-card v-if="oid" title="已录对话（可改/删，删除记为负样本）" size="small">
      <n-empty v-if="!msgs.length" description="暂无对话，在上方录入" />
      <div v-for="m in msgs" :key="m.mid" style="margin: 6px 0; padding: 6px; border-bottom: 1px solid #eee">
        <n-tag size="small" :type="m.role === 'user' ? 'info' : 'success'">{{ m.role === 'user' ? '用户' : '角色' }}</n-tag>
        <span v-if="editing[m.mid] === undefined" style="margin-left: 8px">{{ m.content }}</span>
        <n-space style="margin-top: 4px">
          <n-input v-if="editing[m.mid] !== undefined" v-model:value="editing[m.mid]" size="small" style="width: 400px" />
          <n-button v-if="editing[m.mid] === undefined" size="tiny" @click="editing[m.mid] = m.content">改</n-button>
          <n-button v-else size="tiny" type="primary" @click="saveEdit(m.mid)">保存</n-button>
          <n-button size="tiny" type="error" ghost @click="del(m.mid)">删</n-button>
        </n-space>
      </div>
    </n-card>

    <n-collapse>
      <n-collapse-item title="人格反推提案（删除负样本，待 M12 反推合并）" name="prop">
        <n-empty v-if="!proposals.length" description="暂无提案" />
        <n-card v-for="p in proposals" :key="p.object_id" :title="`对象 ${p.object_id}`" size="small" style="margin-bottom: 8px">
          <div v-for="(s, i) in p.samples" :key="i" style="margin: 4px 0">
            <n-tag size="small" type="warning">{{ s.reason }}</n-tag>
            <span style="margin-left: 8px">{{ s.text }}</span>
          </div>
          <template #footer>
            <n-button size="small" type="error" ghost @click="dismiss(p.object_id)">忽略</n-button>
          </template>
        </n-card>
      </n-collapse-item>
    </n-collapse>
  </n-space>
</template>
