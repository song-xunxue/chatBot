<script setup lang="ts">
/**
 * roleplay 训练样本页(V2.0 M8):录/批量录/列/改/删(→neg)。
 * roleplay 物理隔离,不进 LLM 上下文,作反推正样本来源。
 * 作者: 李文煜
 */
import { ref, reactive, watch } from 'vue'
import {
  NSpace, NInput, NButton, NSelect, NTag, NPopconfirm, NEmpty, NCard, useMessage,
} from 'naive-ui'
import { addRoleplay, addRoleplayBatch, listRoleplay, updateRoleplay, deleteRoleplay } from '@/api'
import { useObject } from '@/composables/useObject'

const message = useMessage()
const { oid, reloadTick } = useObject()   // 全局共享 object_id + 刷新信号
watch(reloadTick, () => load())   // 头部 OID 回车 → 重载本页
const samples = ref<any[]>([])
const role = ref('user')
const content = ref('')
const batchText = ref('')
const editing = reactive<Record<string, string>>({})

const roleOptions = [
  { label: 'user(用户)', value: 'user' },
  { label: 'assistant(角色)', value: 'assistant' },
  { label: 'system(系统)', value: 'system' },
]

async function load() {
  if (!oid.value) return
  try {
    const r = await listRoleplay(oid.value)
    samples.value = r.messages || []
  } catch (e: any) { message.error('' + e) }
}

async function add() {
  if (!content.value.trim()) { message.warning('请输入内容'); return }
  try {
    await addRoleplay(oid.value, { role: role.value, content: content.value.trim() })
    content.value = ''
    message.success('已录入')
    await load()
  } catch (e: any) { message.error('' + e) }
}

async function addBatch() {
  // 每行一条;行首 user:/assistant:/system: 指定角色,否则用当前选中 role
  const lines = batchText.value.split('\n').map((l) => l.trim()).filter(Boolean)
  if (!lines.length) { message.warning('请输入批量内容(每行一条)'); return }
  const items = lines.map((line) => {
    const m = line.match(/^(user|assistant|system):\s*(.*)$/)
    return m ? { role: m[1], content: m[2] } : { role: role.value, content: line }
  })
  try {
    const r = await addRoleplayBatch(oid.value, items)
    batchText.value = ''
    message.success(`批量录入 ${r.count} 条`)
    await load()
  } catch (e: any) { message.error('' + e) }
}

async function save(mid: string) {
  const v = (editing[mid] || '').trim()
  if (!v) { message.warning('请输入改写内容'); return }
  try {
    await updateRoleplay(oid.value, mid, v)
    message.success('已修改')
    delete editing[mid]
    await load()
  } catch (e: any) { message.error('' + e) }
}

async function del(mid: string) {
  try {
    await deleteRoleplay(oid.value, mid)
    message.success('已删除(→neg 队列)')
    await load()
  } catch (e: any) { message.error('' + e) }
}
</script>

<template>
  <n-space vertical size="large">
    <n-space align="center">
      <n-input v-model:value="oid" placeholder="object_id" style="width:220px" @keyup.enter="load" />
      <n-button type="primary" @click="load">查询</n-button>
      <span style="color:#999;font-size:12px">roleplay 训练样本物理隔离,不进 LLM 上下文,作反推正样本来源</span>
    </n-space>

    <n-card title="录入训练样本">
      <n-space vertical>
        <n-space align="center">
          <n-select v-model:value="role" :options="roleOptions" style="width:180px" />
          <n-input v-model:value="content" placeholder="内容" style="width:400px" @keyup.enter="add" />
          <n-button type="primary" @click="add">录入</n-button>
        </n-space>
        <n-space align="center">
          <n-input v-model:value="batchText" type="textarea"
                   placeholder="批量录入(每行一条;行首 user:/assistant:/system: 指定角色,否则用当前选中角色)"
                   :rows="3" style="width:600px" />
          <n-button type="info" @click="addBatch">批量录入</n-button>
        </n-space>
      </n-space>
    </n-card>

    <n-card title="样本列表">
      <n-empty v-if="!samples.length" description="暂无样本" />
      <n-space v-else vertical>
        <div v-for="s in samples" :key="s.mid" style="border:1px solid #eee;border-radius:6px;padding:8px">
          <div style="font-size:12px;color:#888;margin-bottom:4px">
            <n-tag size="tiny"
                   :type="s.role === 'assistant' ? 'info' : (s.role === 'system' ? 'warning' : 'success')">
              {{ s.role }}
            </n-tag>
            <n-tag v-if="s.status === 'edited'" size="tiny">edited</n-tag>
            <span style="margin-left:4px">{{ s.mid }}</span>
          </div>
          <div style="word-break:break-all">{{ s.content }}</div>
          <n-space style="margin-top:4px" align="center">
            <n-input v-model:value="editing[s.mid]" placeholder="改写内容" style="width:400px" />
            <n-button size="small" @click="save(s.mid)">保存</n-button>
            <n-popconfirm @positive-click="del(s.mid)">
              <template #trigger><n-button size="small" type="error" ghost>删除(→neg)</n-button></template>
              删除该样本(写 neg 队列)?
            </n-popconfirm>
          </n-space>
        </div>
      </n-space>
    </n-card>
  </n-space>
</template>
