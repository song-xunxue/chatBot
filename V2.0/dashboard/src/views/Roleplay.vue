<script setup lang="ts">
/**
 * roleplay 训练样本(V2.0 改造 2026-07-05):重构为 IM 对话流(user 左 / assistant 左 / system 居中),
 * 底部录入区可选「作为用户说 / 作为角色说 / 系统旁白」追加到对话流末尾。
 * 一段连续对话(可两边随机添加),而非原先的独立卡片。体现完整会话语义。
 * roleplay 物理隔离,不进 LLM 上下文,作反推正样本来源。去 oid 输入框,启动自动加载全局 oid。
 * 作者: 李文煜
 */
import { ref, watch, onMounted, nextTick } from 'vue'
import {
  NSpace, NInput, NButton, NSelect, NTag, NPopconfirm, NEmpty, NModal, useMessage,
} from 'naive-ui'
import { addRoleplay, listRoleplay, updateRoleplay, deleteRoleplay } from '@/api'
import { useObject } from '@/composables/useObject'

const message = useMessage()
const { oid, reloadTick, ensureOid } = useObject()
watch(reloadTick, () => load())

const samples = ref<any[]>([])
const role = ref('user')   // 录入身份:user/assistant/system
const content = ref('')
const streamEl = ref<HTMLElement | null>(null)

const roleOptions = [
  { label: '作为用户说(user)', value: 'user' },
  { label: '作为角色说(assistant)', value: 'assistant' },
  { label: '系统旁白(system)', value: 'system' },
]

// 编辑弹窗
const editShow = ref(false)
const editMid = ref('')
const editContent = ref('')

async function load() {
  if (!oid.value || oid.value === 'default') return
  try {
    const r = await listRoleplay(oid.value)
    samples.value = r.messages || []
    await nextTick()
    if (streamEl.value) streamEl.value.scrollTop = streamEl.value.scrollHeight  // 录入后滚到底
  } catch (e: any) { message.error('' + e) }
}

async function add() {
  if (!content.value.trim()) { message.warning('请输入内容'); return }
  try {
    await addRoleplay(oid.value, { role: role.value, content: content.value.trim() })
    content.value = ''
    await load()
  } catch (e: any) { message.error('' + e) }
}

function openEdit(mid: string, c: string) {
  editMid.value = mid; editContent.value = c || ''; editShow.value = true
}
async function applyEdit() {
  if (!editMid.value) return
  try {
    await updateRoleplay(oid.value, editMid.value, editContent.value)
    message.success('已修改'); editShow.value = false; editMid.value = ''
    await load()
  } catch (e: any) { message.error('' + e) }
}
async function del(mid: string) {
  try { await deleteRoleplay(oid.value, mid); message.success('已删除(→neg)'); await load() }
  catch (e: any) { message.error('' + e) }
}

onMounted(async () => { await ensureOid(); await load() })
</script>

<template>
  <n-space vertical size="large" style="height:calc(100vh - 92px)">
    <n-space align="center" justify="space-between" style="flex-shrink:0">
      <span style="font-weight:600">训练样本(对话流)</span>
      <n-button size="small" @click="load">刷新</n-button>
    </n-space>
    <span style="color:#999;font-size:12px;flex-shrink:0">
      roleplay 物理隔离,不进 LLM 上下文,作反推正样本来源。下方可选择"用户/角色/系统"身份,把对话一条条追加进同一段会话。
    </span>

    <!-- 对话流(user 右绿 / assistant 左蓝 / system 居中灰) -->
    <div ref="streamEl" style="flex:1; overflow:auto; padding:8px; border:1px solid #efeff5; border-radius:8px; background:#fafafa; min-height:0">
      <n-empty v-if="!samples.length" description="暂无样本,从下方录入第一条开始构建对话" style="margin:40px auto" />
      <div v-for="s in samples" :key="s.mid"
           :style="{ display:'flex', justifyContent: s.role === 'user' ? 'flex-end' : (s.role === 'system' ? 'center' : 'flex-start'), margin:'4px 0' }">
        <div :style="{ maxWidth:'72%', padding:'6px 10px', borderRadius:'10px',
          background: s.role === 'user' ? '#DCF8C6' : (s.role === 'system' ? '#f0f0f0' : '#E8F1FF'), color:'#222' }">
          <div style="font-size:11px; color:#888; display:flex; align-items:center; gap:6px">
            <n-tag size="tiny" :type="s.role === 'assistant' ? 'info' : (s.role === 'system' ? 'warning' : 'success')">{{ s.role }}</n-tag>
            <n-tag v-if="s.status === 'edited'" size="tiny">edited</n-tag>
            <n-button size="tiny" text @click="openEdit(s.mid, s.content)">编辑</n-button>
            <n-popconfirm @positive-click="del(s.mid)">
              <template #trigger><n-button size="tiny" text type="error">删除</n-button></template>
              删除(→neg)?
            </n-popconfirm>
          </div>
          <div style="word-break:break-all; white-space:pre-wrap">{{ s.content }}</div>
        </div>
      </div>
    </div>

    <!-- 录入区(底部) -->
    <n-space align="center" :wrap="false" style="flex-shrink:0">
      <n-select v-model:value="role" :options="roleOptions" style="width:200px" />
      <n-input v-model:value="content" placeholder="输入内容,回车追加到对话流..." style="flex:1"
               @keyup.enter="add" />
      <n-button type="primary" @click="add">追加</n-button>
    </n-space>
  </n-space>

  <!-- 编辑弹窗 -->
  <n-modal v-model:show="editShow" preset="card" title="改写样本内容" style="width:640px;max-width:92vw">
    <n-space vertical :size="12">
      <n-input v-model:value="editContent" type="textarea" :rows="8" autofocus />
      <n-space justify="end">
        <n-button @click="editShow = false">取消</n-button>
        <n-button type="primary" @click="applyEdit">确定</n-button>
      </n-space>
    </n-space>
  </n-modal>
</template>
