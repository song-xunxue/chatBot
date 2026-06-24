<script setup lang="ts">
/**
 * 对话历史（V1.2）：ts 格式化 + 5分钟窗分组展示 + 修改/删除
 * 展示分组（不改存储）：相邻消息 ts 差 >5min 开新组，组首显示时间分隔条。
 * 作者: 李文煜
 */
import { ref, computed } from 'vue'
import {
  NSpace, NInput, NInputNumber, NButton, NTag, NSelect, NPopconfirm, NEmpty,
  useMessage,
} from 'naive-ui'
import { getHistory, updateHistoryMsg, deleteHistoryMsg } from '@/api'

const message = useMessage()
const oid = ref('default')
const limit = ref(50)
const msgs = ref<any[]>([])
const editing = ref<Record<string, any>>({})   // mid -> {role,content,ts}

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

// V1.2-1：5分钟窗分组（相邻 ts 差 >5min 开新组，ts 为 0 视为同组）
const WINDOW_MS = 5 * 60 * 1000
const grouped = computed(() => {
  const groups: { head: string; items: any[] }[] = []
  let cur: { head: string; items: any[] } | null = null
  for (const m of msgs.value) {
    const last = cur && cur.items.length ? cur.items[cur.items.length - 1] : null
    const needNew = !cur || (m.ts && last && last.ts && m.ts - last.ts > WINDOW_MS)
    if (needNew) {
      cur = { head: fmtTs(m.ts), items: [] }
      groups.push(cur)
    }
    cur!.items.push(m)
  }
  return groups
})

function startEdit(m: any) {
  editing.value[m.mid] = { role: m.role, content: m.content, ts: m.ts }
}
function cancelEdit(mid: string) { delete editing.value[mid] }
async function saveEdit(m: any) {
  try {
    await updateHistoryMsg(oid.value, m.mid, editing.value[m.mid])
    message.success('已保存')
    delete editing.value[m.mid]
    load()
  } catch (e: any) { message.error('' + e) }
}
async function del(m: any) {
  try {
    await deleteHistoryMsg(oid.value, m.mid)
    message.success('已删除')
    load()
  } catch (e: any) { message.error('' + e) }
}
</script>

<template>
  <n-space vertical size="large">
    <n-space align="center">
      <n-input v-model:value="oid" placeholder="object_id" style="width: 220px" @keyup.enter="load" />
      <n-input-number v-model:value="limit" :min="1" :max="500" style="width: 120px" />
      <n-button type="primary" @click="load">查询</n-button>
      <span style="color:#999;font-size:12px">相邻消息间隔 &gt;5 分钟自动分组</span>
    </n-space>

    <n-empty v-if="!msgs.length" description="输入 object_id 查询历史" />

    <div v-for="(g, gi) in grouped" :key="gi">
      <!-- 组时间分隔条 -->
      <div style="text-align:center;margin:14px 0 6px;color:#999;font-size:12px;border-bottom:1px dashed #eee;padding-bottom:4px">
        🕒 {{ g.head }}
      </div>
      <div v-for="m in g.items" :key="m.mid" style="display:flex;align-items:flex-start;gap:8px;padding:6px 4px;border-bottom:1px solid #f5f5f5">
        <!-- 展示态 -->
        <template v-if="editing[m.mid] === undefined">
          <n-tag size="small" :type="m.role === 'user' ? 'info' : (m.role === 'assistant' ? 'success' : 'default')" style="flex:0 0 auto;min-width:70px;text-align:center">{{ m.role }}</n-tag>
          <div style="flex:1;word-break:break-all">{{ m.content }}</div>
          <div style="flex:0 0 auto;color:#aaa;font-size:11px;width:120px;text-align:right">{{ fmtTs(m.ts) }}</div>
          <n-button size="tiny" @click="startEdit(m)" style="flex:0 0 auto">改</n-button>
          <n-popconfirm @positive-click="del(m)">
            <template #trigger><n-button size="tiny" type="error" ghost>删</n-button></template>
            确认删除这条消息？
          </n-popconfirm>
        </template>
        <!-- 编辑态 -->
        <template v-else style="flex-direction:column">
          <div style="display:flex;flex-direction:column;gap:6px;width:100%">
            <n-select v-model:value="editing[m.mid].role" :options="roleOptions" size="small" style="width:180px" />
            <n-input v-model:value="editing[m.mid].content" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" />
            <n-space>
              <n-button size="small" type="primary" @click="saveEdit(m)">保存</n-button>
              <n-button size="small" @click="cancelEdit(m.mid)">取消</n-button>
            </n-space>
          </div>
        </template>
      </div>
    </div>
  </n-space>
</template>
