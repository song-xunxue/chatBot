<script setup lang="ts">
/**
 * 代人聊天 / 人格反推审核：列出 M4.4 persona_evolve 待审核提案，逐条忽略（rest_admin proposals）
 * 闭合"人格反推 → 人工确认"环（提案不自动改写人设）
 * 作者: 李文煜
 */
import { ref, onMounted } from 'vue'
import { NSpace, NButton, NCard, NTag, NEmpty, useMessage } from 'naive-ui'
import { getProposals, dismissProposal } from '@/api'

const message = useMessage()
const proposals = ref<any[]>([])

async function load() {
  try {
    proposals.value = (await getProposals()).proposals
  } catch (e: any) {
    message.error('' + e)
  }
}
onMounted(load)

async function dismiss(oid: string) {
  try {
    await dismissProposal(oid)
    message.success('已忽略')
    load()
  } catch (e: any) {
    message.error('' + e)
  }
}
</script>

<template>
  <n-space vertical size="large">
    <n-space>
      <n-button @click="load">刷新提案</n-button>
    </n-space>
    <n-empty v-if="!proposals.length" description="暂无待审核的人格进化提案" />
    <n-card v-for="p in proposals" :key="p.object_id" :title="`对象 ${p.object_id}`" size="small">
      <div v-for="(s, i) in p.samples" :key="i" style="margin: 4px 0">
        <n-tag size="small" type="warning">{{ s.reason }}</n-tag>
        <span style="margin-left: 8px">{{ s.text }}</span>
      </div>
      <template #footer>
        <n-button size="small" type="error" ghost @click="dismiss(p.object_id)">忽略提案</n-button>
      </template>
    </n-card>
  </n-space>
</template>
