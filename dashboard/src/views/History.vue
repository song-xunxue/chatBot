<script setup lang="ts">
/**
 * 对话历史（V1.2）：聊天框式气泡展示（user 右/assistant 左，像代人聊天）+
 * 5分钟窗分组 + 时间格式化 + 修改(预选角色)/删除。
 * 作者: 李文煜
 */
import { ref, computed } from 'vue'
import {
  NSpace, NInput, NInputNumber, NButton, NSelect, NPopconfirm, NEmpty,
  useMessage,
} from 'naive-ui'
import { getHistory, updateHistoryMsg, deleteHistoryMsg } from '@/api'

const message = useMessage()
const oid = ref('default')
const limit = ref(50)
const msgs = ref<any[]>([])
const editing = ref<Record<string, any>>({})

const roleOptions = [
  { label: '用户 (user)', value: 'user' },
  { label: '角色 (assistant)', value: 'assistant' },
  { label: '系统 (system)', value: 'system' },
]

async function load() {
  try {
    msgs.value = (await getHistory(oid.value, Number(limit.value))).messages
    editing.value = {}
  } catch (e: any) { message.error('' + e) }
}
function fmtTs(ts: number): string {
  if (!ts) return '—'
  const d = new Date(ts)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}
// 5分钟窗分组
const WINDOW_MS = 5 * 60 * 1000
const grouped = computed(() => {
  const groups: { head: string; items: any[] }[] = []
  let cur: { head: string; items: any[] } | null = null
  for (const m of msgs.value) {
    const last = cur && cur.items.length ? cur.items[cur.items.length - 1] : null
    const needNew = !cur || (m.ts && last && last.ts && m.ts - last.ts > WINDOW_MS)
    if (needNew) { cur = { head: fmtTs(m.ts), items: [] }; groups.push(cur) }
    cur!.items.push(m)
  }
  return groups
})
function startEdit(m: any) { editing.value[m.mid] = { role: m.role, content: m.content, ts: m.ts } }
function cancelEdit(mid: string) { delete editing.value[mid] }
async function saveEdit(m: any) {
  try { await updateHistoryMsg(oid.value, m.mid, editing.value[m.mid]); message.success('已保存'); delete editing.value[m.mid]; load() }
  catch (e: any) { message.error('' + e) }
}
async function del(m: any) {
  try { await deleteHistoryMsg(oid.value, m.mid); message.success('已删除'); load() }
  catch (e: any) { message.error('' + e) }
}
</script>

<template>
  <n-space vertical size="large">
    <n-space align="center">
      <n-input v-model:value="oid" placeholder="object_id" style="width: 220px" @keyup.enter="load" />
      <n-input-number v-model:value="limit" :min="1" :max="500" style="width: 120px" />
      <n-button type="primary" @click="load">查询</n-button>
      <span style="color:#999;font-size:12px">聊天框式 · 相邻 &gt;5 分钟自动分组</span>
    </n-space>

    <n-empty v-if="!msgs.length" description="输入 object_id 查询历史" />

    <div v-for="(g, gi) in grouped" :key="gi">
      <div style="text-align:center;margin:14px 0 8px;color:#999;font-size:12px">🕒 {{ g.head }}</div>
      <!-- 聊天框式气泡：user 右绿 / assistant 左蓝 / system 居中灰 -->
      <div v-for="m in g.items" :key="m.mid" :style="{ display:'flex', justifyContent: m.role==='system' ? 'center' : (m.role==='user' ? 'flex-end' : 'flex-start'), margin:'5px 0' }">
        <div v-if="editing[m.mid] === undefined" :style="{ maxWidth:'72%', padding:'8px 12px', borderRadius:'12px',
            background: m.role==='user' ? '#DCF8C6' : (m.role==='system' ? '#f0f0f0' : '#E8F1FF'), color:'#222', wordBreak:'break-all' }">
          <div style="font-size:11px;color:#888;margin-bottom:2px">{{ m.role==='user'?'用户':(m.role==='system'?'系统':'角色') }} · {{ fmtTs(m.ts) }}</div>
          <div>{{ m.content }}</div>
          <n-space style="margin-top:4px">
            <n-button size="tiny" @click="startEdit(m)">改</n-button>
            <n-popconfirm @positive-click="del(m)"><template #trigger><n-button size="tiny" type="error" ghost>删</n-button></template>确认删除？</n-popconfirm>
          </n-space>
        </div>
        <!-- 编辑态：预选角色 + 内容 + 保存 -->
        <div v-else style="maxWidth:72%;padding:8px 12px;border-radius:12px;background:#fffbe6;width:100%">
          <n-select v-model:value="editing[m.mid].role" :options="roleOptions" size="small" style="width:180px;margin-bottom:6px" />
          <n-input v-model:value="editing[m.mid].content" type="textarea" :autosize="{ minRows:2, maxRows:6 }" />
          <n-space style="margin-top:6px">
            <n-button size="small" type="primary" @click="saveEdit(m)">保存</n-button>
            <n-button size="small" @click="cancelEdit(m.mid)">取消</n-button>
          </n-space>
        </div>
      </div>
    </div>
  </n-space>
</template>
