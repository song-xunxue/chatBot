<script setup lang="ts">
/**
 * 代人代答页(V2.0 M8):代答开关 + pending 队列 + 单条/批量代答 + 跳过。
 * 代答模式开启时,用户消息进 pending 队列(不进 LLM),管理员在此代答 → 真实下发 QQ。
 * 作者: 李文煜
 */
import { ref, reactive } from 'vue'
import {
  NSpace, NInput, NButton, NSwitch, NTag, NPopconfirm, NEmpty, NCard, useMessage,
} from 'naive-ui'
import {
  getTakeoverStatus, toggleTakeover, listTakeoverQueue,
  answerTakeover, answerTakeoverBatch, skipTakeover,
} from '@/api'

const message = useMessage()
const oid = ref('default')
const enabled = ref(false)
const queueLength = ref(0)
const queue = ref<any[]>([])
// 每条 pending 的代答输入(pid -> answer),reactive 支持动态 key v-model
const answers = reactive<Record<string, string>>({})

function fmtTs(ts: any): string {
  const n = Number(ts)
  if (!n) return '—'
  const d = new Date(n); const p = (x: number) => String(x).padStart(2, '0')
  return `${d.getMonth() + 1}/${d.getDate()} ${p(d.getHours())}:${p(d.getMinutes())}`
}

async function load() {
  if (!oid.value) return
  try {
    const s = await getTakeoverStatus(oid.value)
    enabled.value = s.enabled
    queueLength.value = s.queue_length
    const q = await listTakeoverQueue(oid.value)
    queue.value = q.queue || []
  } catch (e: any) { message.error('' + e) }
}

async function onToggle(v: boolean) {
  try {
    await toggleTakeover(oid.value, v)
    enabled.value = v
    message.success(v ? '代答模式已开启(用户消息入队,不自动回复)' : '代答模式已关闭(恢复自动回复)')
  } catch (e: any) { message.error('' + e); enabled.value = !v }
}

async function submitOne(p: any) {
  const ans = (answers[p.pid] || '').trim()
  if (!ans) { message.warning('请输入代答内容'); return }
  try {
    const r = await answerTakeover(oid.value, { pid: p.pid, answer: ans })
    message.success(`已代答(下发:${r.delivered ? r.mode : '失败,可重试'})`)
    answers[p.pid] = ''
    await load()
  } catch (e: any) { message.error('' + e) }
}

async function submitBatch() {
  const items = queue.value
    .map((p) => ({ pid: p.pid, answer: (answers[p.pid] || '').trim() }))
    .filter((it) => it.answer)
  if (!items.length) { message.warning('请至少填写一条代答'); return }
  try {
    const r = await answerTakeoverBatch(oid.value, items)
    message.success(`批量代答完成(${r.success}/${items.length} 成功${r.truncated ? ',超限已截断' : ''})`)
    items.forEach((it) => { answers[it.pid] = '' })
    await load()
  } catch (e: any) { message.error('' + e) }
}

async function skip(p: any) {
  try {
    await skipTakeover(oid.value, p.pid)
    message.success('已跳过')
    await load()
  } catch (e: any) { message.error('' + e) }
}
</script>

<template>
  <n-space vertical size="large">
    <n-space align="center">
      <n-input v-model:value="oid" placeholder="object_id" style="width:220px" @keyup.enter="load" />
      <n-button type="primary" @click="load">查询</n-button>
      <span style="color:#999;font-size:12px">代答模式开启时,用户消息入 pending 队列(不进 LLM 自动回复)</span>
    </n-space>

    <n-card title="代答模式">
      <n-space align="center">
        <n-switch :value="enabled" @update:value="onToggle" />
        <n-tag :type="enabled ? 'warning' : 'default'">{{ enabled ? '代答中' : '自动回复' }}</n-tag>
        <n-tag size="small">队列 {{ queueLength }} 条</n-tag>
      </n-space>
    </n-card>

    <n-empty v-if="!queue.length" description="队列为空(代答模式开启后,用户消息会出现在此)" />

    <n-card v-else title="待答队列(FIFO,队首在前)">
      <n-space vertical>
        <div v-for="p in queue" :key="p.pid" style="border:1px solid #eee;border-radius:6px;padding:10px">
          <div style="font-size:12px;color:#888;margin-bottom:4px">
            {{ p.pid }} · {{ fmtTs(p.created_ts) }}
            <n-tag v-if="p.msg_id" size="tiny" type="info">有 msg_id(可被动回复)</n-tag>
          </div>
          <div style="background:#f6ffed;padding:6px 10px;border-radius:4px;margin-bottom:6px;word-break:break-all">
            {{ p.user_text }}
          </div>
          <n-space align="center">
            <n-input v-model:value="answers[p.pid]" placeholder="输入代答回复..." style="width:380px"
                     @keyup.enter="submitOne(p)" />
            <n-button type="primary" size="small" @click="submitOne(p)">代答</n-button>
            <n-popconfirm @positive-click="skip(p)">
              <template #trigger><n-button size="small" quaternary>跳过</n-button></template>
              跳过该条(不答)?
            </n-popconfirm>
          </n-space>
        </div>
        <n-button type="info" @click="submitBatch">批量提交已填写的代答</n-button>
      </n-space>
    </n-card>
  </n-space>
</template>
