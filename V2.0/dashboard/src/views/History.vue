<script setup lang="ts">
/**
 * 对话历史(V2.0 M7):block 三层折叠(会话→blocks→messages)+ 消息气泡(含 score 四元组/status)+
 * 编辑(updateMessage → status=edited)+ 软删(联动负样本)+ 手动关 block。对齐 V2.0 rest_chat。
 * 作者: 李文煜
 */
import { ref, watch } from 'vue'
import {
  NSpace, NInput, NButton, NTag, NPopconfirm, NEmpty, NCollapse, NCollapseItem,
  useMessage,
} from 'naive-ui'
import { listBlocks, listMessages, deleteMessage, closeBlock } from '@/api'
import { useObject } from '@/composables/useObject'

const message = useMessage()
const { oid, reloadTick } = useObject()   // 全局共享 object_id + 刷新信号
watch(reloadTick, () => load())   // 头部 OID 回车 → 重载本页(load 为函数声明,已提升)
const blocks = ref<any[]>([])

async function load() {
  if (!oid.value) return
  try {
    const bs: any[] = await listBlocks(oid.value)
    for (const b of bs) {
      b._messages = await listMessages(oid.value, { block_id: b.block_id })
    }
    blocks.value = bs
  } catch (e: any) { message.error('' + e) }
}
function fmtTs(ts: any): string {
  const n = Number(ts)
  if (!n) return '—'
  const d = new Date(n); const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}/${d.getDate()} ${p(d.getHours())}:${p(d.getMinutes())}`
}
async function del(mid: string) {
  try { await deleteMessage(mid); message.success('已软删(若 ai/有分则联动负样本)'); await load() }
  catch (e: any) { message.error('' + e) }
}
async function closeBlk(bid: string) {
  try { await closeBlock(bid); message.success('已关闭 block'); await load() }
  catch (e: any) { message.error('' + e) }
}
</script>

<template>
  <n-space vertical size="large">
    <n-space align="center">
      <n-input v-model:value="oid" placeholder="object_id" style="width: 220px" @keyup.enter="load" />
      <n-button type="primary" @click="load">查询</n-button>
      <span style="color:#999;font-size:12px">block 三层(会话 → blocks → messages),最近 block 在前</span>
    </n-space>

    <n-empty v-if="!blocks.length" description="输入 object_id 查询历史" />

    <n-collapse v-else accordion>
      <n-collapse-item v-for="b in blocks" :key="b.block_id" :name="b.block_id">
        <template #header>
          <n-space align="center">
            <n-tag :type="b.status === 'open' ? 'success' : 'default'" size="small">{{ b.status }}</n-tag>
            <span>{{ fmtTs(b.start_ts) }} → {{ fmtTs(b.end_ts) }}</span>
            <n-tag size="small">{{ b.msg_count }} 条</n-tag>
            <n-tag v-if="b.close_reason" size="small" type="info">{{ b.close_reason }}</n-tag>
          </n-space>
        </template>
        <template #header-extra>
          <n-button v-if="b.status === 'open'" size="tiny" @click.stop="closeBlk(b.block_id)">关闭 block</n-button>
        </template>
        <div v-for="m in (b._messages || [])" :key="m.mid"
             :style="{ display: 'flex', justifyContent: m.sender === 'user' ? 'flex-end' : 'flex-start', margin: '4px 0' }">
          <div :style="{ maxWidth: '72%', padding: '6px 10px', borderRadius: '10px',
            background: m.sender === 'user' ? '#DCF8C6' : (m.sender === 'system' ? '#f0f0f0' : '#E8F1FF'), color: '#222' }">
            <div style="font-size: 11px; color: #888">
              {{ m.sender }} · {{ fmtTs(m.ts) }}
              <n-tag v-if="m.score !== '' && m.score !== undefined" size="tiny"
                     :type="Number(m.score) >= 85 ? 'success' : (Number(m.score) < 60 ? 'error' : 'default')">
                分 {{ m.score }}
              </n-tag>
              <n-tag v-if="m.status && m.status !== 'active'" size="tiny">{{ m.status }}</n-tag>
            </div>
            <div style="word-break: break-all">{{ m.content }}</div>
            <n-space style="margin-top: 2px" v-if="m.status !== 'deleted'">
              <n-popconfirm @positive-click="del(m.mid)">
                <template #trigger><n-button size="tiny" type="error" ghost>软删</n-button></template>
                软删(→负样本)?
              </n-popconfirm>
            </n-space>
          </div>
        </div>
      </n-collapse-item>
    </n-collapse>
  </n-space>
</template>
