<script setup lang="ts">
/**
 * 评分健康页(M7):人设健康度(chart.js 正/负/中计数)+ 单条改分 +
 * 反推人设(dry_run 预览 → apply 落库)+ 正反样例列表。
 * 作者: 李文煜
 */
import { ref, computed } from 'vue'
import { Bar } from 'vue-chartjs'
import { Chart as ChartJS, Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale } from 'chart.js'
import { NSpace, NInput, NInputNumber, NButton, NCard, NTag, NPopconfirm, NEmpty, useMessage } from 'naive-ui'
import { getHealth, getSamples, reverseInferDryRun, reverseInferApply, setScore } from '@/api'

ChartJS.register(Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale)

const message = useMessage()
const oid = ref('default')
const health = ref<any>(null)
const posSamples = ref<any[]>([])
const negSamples = ref<any[]>([])
const loading = ref(false)
const inferDiff = ref<any>(null)
const inferToken = ref('')
const inferring = ref(false)
const scoreMid = ref('')
const scoreBase = ref(80)

const chartData = computed(() => ({
  labels: ['正样本', '中性', '负样本'],
  datasets: [{
    label: '计数',
    backgroundColor: ['#18a058', '#909399', '#d03050'],
    data: [health.value?.positive || 0, health.value?.neutral || 0, health.value?.negative || 0],
  }],
}))
const chartOptions = { responsive: true, plugins: { legend: { display: false } } }

async function load() {
  if (!oid.value) return
  loading.value = true
  try {
    health.value = await getHealth(oid.value)
    posSamples.value = await getSamples(oid.value, 'positive')
    negSamples.value = await getSamples(oid.value, 'negative')
    inferDiff.value = null
    inferToken.value = ''
  } catch (e: any) { message.error('' + e) }
  finally { loading.value = false }
}

async function dryRun() {
  inferring.value = true
  try {
    const r = await reverseInferDryRun(oid.value, { mode: 'fill_empty' })
    inferDiff.value = r.diff
    inferToken.value = r.confirm_token
    message.success(`反推预览完成(正 ${r.positive_count} / 负 ${r.negative_count})`)
  } catch (e: any) { message.error('' + e) }
  finally { inferring.value = false }
}

async function applyInfer() {
  try {
    await reverseInferApply(oid.value, inferToken.value)
    message.success('反推已落库')
    inferDiff.value = null
    inferToken.value = ''
  } catch (e: any) { message.error('' + e) }
}

async function applyScore() {
  if (!scoreMid.value) { message.warning('请输入消息 mid'); return }
  try {
    const r = await setScore(scoreMid.value, scoreBase.value)
    message.success(`已改分:score = ${r.score}`)
  } catch (e: any) { message.error('' + e) }
}
</script>

<template>
  <n-space vertical size="large">
    <n-space align="center">
      <n-input v-model:value="oid" placeholder="object_id" style="width:220px" @keyup.enter="load" />
      <n-button type="primary" :loading="loading" @click="load">查询</n-button>
    </n-space>

    <n-card title="人设健康度">
      <n-empty v-if="!health" description="输入 object_id 查询" />
      <n-space v-else vertical>
        <div>
          近 {{ health.count }} 条评分均分:
          <n-tag :type="(health.avg_score || 0) >= 70 ? 'success' : ((health.avg_score || 0) >= 50 ? 'warning' : 'error')">
            {{ health.avg_score ?? '—' }}
          </n-tag>
          <span v-if="(health.avg_score || 0) < 60 && health.count > 0" style="color:#d03050;margin-left:8px">
            ⚠ 人设可能跑偏,建议反推修正
          </span>
        </div>
        <Bar v-if="health.count > 0" :data="chartData" :options="chartOptions" />
      </n-space>
    </n-card>

    <n-card title="单条改分">
      <n-space align="center">
        <n-input v-model:value="scoreMid" placeholder="消息 mid" style="width:300px" />
        <n-input-number v-model:value="scoreBase" :min="0" :max="100" />
        <n-button type="primary" @click="applyScore">改分</n-button>
        <span style="color:#999;font-size:12px">覆盖 score_base,保留历史 mood_bias 重算 score</span>
      </n-space>
    </n-card>

    <n-card title="反推人设(评分样本 → 人设字段提炼)">
      <n-space>
        <n-button type="primary" :loading="inferring" @click="dryRun">生成反推预览</n-button>
        <n-popconfirm v-if="inferToken" @positive-click="applyInfer">
          <template #trigger><n-button type="warning">确认落库</n-button></template>
          确认应用反推 diff 到人设?
        </n-popconfirm>
      </n-space>
      <pre v-if="inferDiff"
           style="background:#f5f5f5;padding:12px;margin-top:12px;max-height:300px;overflow:auto;font-size:12px">{{ JSON.stringify(inferDiff, null, 2) }}</pre>
    </n-card>

    <n-card title="正反样例">
      <n-space vertical>
        <div>
          <n-tag type="success">正样本({{ posSamples.length }})</n-tag>
          <div v-for="s in posSamples" :key="s.mid"
               style="margin:4px 0;padding:4px 8px;background:#f6ffed;border-radius:4px">
            [{{ s.score }}] {{ s.text }}
          </div>
        </div>
        <div>
          <n-tag type="error">负样本({{ negSamples.length }})</n-tag>
          <div v-for="s in negSamples" :key="s.mid"
               style="margin:4px 0;padding:4px 8px;background:#fff2f0;border-radius:4px">
            [{{ s.score }}] {{ s.text }}
          </div>
        </div>
      </n-space>
    </n-card>
  </n-space>
</template>
