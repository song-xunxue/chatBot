<script setup lang="ts">
/**
 * 移动端日记页(功能对等 PC Diary.vue,窄屏重排,2026-10-26):
 * 顶栏(标题 + 刷新)→"立即补做"大按钮(touch ≥44px)→ 日期横向滚动 chip 行(当前项暖色)
 * → 她的梦 / 她的日记(key_events 换行 flex wrap)/ 当天心情曲线 三卡堆叠(间距 --sp-3)。
 * 数据与 API 同 PC;oid 由 useObject.ensureOid 自动取(仅补做时传给后端,移动端无头部输入框);
 * 详情 404 → 空态提示而非报错。
 * 日期: 2026-10-26
 */
import { ref, computed, watch, onMounted } from 'vue'
import { Line } from 'vue-chartjs'
import { Chart as ChartJS, Title, Tooltip, Legend, LineElement, PointElement, CategoryScale, LinearScale } from 'chart.js'
import { NButton, NEmpty, NPopconfirm, NSpin, useMessage } from 'naive-ui'
import { getDiaryList, getDiary, runDiary } from '@/api'
import { useObject } from '@/composables/useObject'
import { darkChartScales } from '@/styles/darkChart'

ChartJS.register(Title, Tooltip, Legend, LineElement, PointElement, CategoryScale, LinearScale)

const message = useMessage()
const { oid, reloadTick, ensureOid } = useObject()   // oid 自动取最近会话(补做传参)+ 刷新信号

// tone → 文案/配色映射(positive 暖色甜梦 / negative 红色噩梦 / neutral 灰色平静)
function toneLabel(t: string): string {
  return t === 'positive' ? '甜梦' : t === 'negative' ? '噩梦' : '平静'
}
function toneClass(t: string): string {
  return t === 'positive' ? 'chip-warm' : t === 'negative' ? 'chip-danger' : ''
}

// —— 日期列表(倒序,最近 30 天)——
interface DiaryItem { date: string; tone: string; excerpt?: string }
const entries = ref<DiaryItem[]>([])
const selectedDate = ref('')
const loadingList = ref(false)

async function loadList() {
  loadingList.value = true
  try {
    const r = await getDiaryList(30)
    entries.value = (r && r.items) || []
    if (entries.value.length && !entries.value.some((e) => e.date === selectedDate.value)) {
      await select(entries.value[0].date)   // 默认选中最近一天
    } else if (!entries.value.length) {
      selectedDate.value = ''
      detail.value = null
      notFound.value = false
    }
  } catch (e: any) { message.error('' + e) }
  finally { loadingList.value = false }
}

// —— 单日详情 ——
const detail = ref<any>(null)
const notFound = ref(false)
const loadingDetail = ref(false)

async function select(date: string) {
  selectedDate.value = date
  detail.value = null
  notFound.value = false
  loadingDetail.value = true
  try {
    detail.value = await getDiary(date)
  } catch (e: any) {
    // 404(详情被删/日期越界)不算错误,空态提示;其余弹错
    if (e?.response?.status === 404) notFound.value = true
    else message.error('' + e)
  } finally { loadingDetail.value = false }
}

// —— 立即补做(给今天手动跑一次 dream;oid 未绑真实会话时禁用,同 MoodMobile 惯例)——
const running = ref(false)
const oidReady = computed(() => !!oid.value && oid.value !== 'default')
async function runToday() {
  running.value = true
  try {
    const entry = await runDiary({ object_id: oid.value })
    message.success(`已生成 ${entry?.date || ''} 的梦与日记`)
    await loadList()
    if (entry?.date) await select(entry.date)
  } catch {
    message.error('生成失败(无素材或 LLM 不可用)')
  } finally { running.value = false }
}

// 毫秒时间戳 → HH:mm(mood 曲线横轴 / 日记写入时刻)
function fmtClock(ts: any): string {
  const n = Number(ts)
  if (!n) return '—'
  const d = new Date(n)
  const p = (x: number) => String(x).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}`
}

// 当天 mood 曲线(canvas 不解析 CSS 变量,暖色线用字面色值,与 --warm 同源)
const curve = computed<any[]>(() => (detail.value?.mood_curve as any[]) || [])
const lineData = computed(() => ({
  labels: curve.value.map((p) => fmtClock(p.ts)),
  datasets: [{ label: 'mood', borderColor: '#f2a3b3', backgroundColor: 'rgba(242,163,179,0.15)',
               data: curve.value.map((p) => p.value), tension: 0.3 }],
}))
const lineOptions = { responsive: true, scales: { x: darkChartScales.x, y: { ...darkChartScales.y, min: 0, max: 1 } }, plugins: { legend: { display: false } } }

// 顶栏刷新:列表 + 详情全量重载
async function loadAll() {
  await loadList()
  if (selectedDate.value) await select(selectedDate.value)
}

watch(reloadTick, () => loadAll())
onMounted(async () => {
  await ensureOid()
  await loadAll()
})
</script>

<template>
  <div class="m-diary">
    <!-- 顶栏:标题 + 刷新 -->
    <div class="m-topbar">
      <span class="m-title">日记</span>
      <n-button size="small" quaternary :loading="loadingList || loadingDetail" @click="loadAll">刷新</n-button>
    </div>

    <!-- 立即补做(大按钮;LLM 生成耗时,oid 未绑定真实会话时禁用) -->
    <n-popconfirm @positive-click="runToday">
      <template #trigger>
        <n-button type="primary" size="large" block :disabled="running || !oidReady" :loading="running">
          立即补做
        </n-button>
      </template>
      给今天手动生成一次梦与日记？（需当天有对话素材且 LLM 可用）
    </n-popconfirm>

    <!-- 空态:一天日记都没有 -->
    <div v-if="!entries.length && !loadingList" class="empty-state">
      <span class="empty-icon">🌙</span>
      <span>还没有日记。要么她还没做过梦，要么你还没开启 dream 插件（面板 → 插件 → 做梦与日记）</span>
    </div>

    <template v-else>
      <!-- 日期横向滚动 chip 行(当前项暖色高亮) -->
      <div class="date-strip">
        <span v-for="e in entries" :key="e.date"
              class="chip date-chip" :class="{ 'chip-warm': e.date === selectedDate }"
              @click="select(e.date)">
          {{ e.date }}
        </span>
      </div>

      <!-- 详情:梦 / 日记 / 曲线 三卡堆叠 -->
      <n-spin :show="loadingDetail">
        <div v-if="notFound" class="empty-state">
          <span class="empty-icon">🌙</span>
          <span>这一天的日记不存在</span>
        </div>
        <div v-else-if="detail" class="cards">
          <!-- 梦境卡 -->
          <div class="card">
            <div class="card-head">
              <span class="section-title">她的梦</span>
              <span class="chip" :class="toneClass(detail.dream_tone || 'neutral')">
                {{ toneLabel(detail.dream_tone || 'neutral') }}
              </span>
            </div>
            <p class="prose">{{ detail.dream || '（这一夜没有梦）' }}</p>
          </div>

          <!-- 日记卡(正文 + key_events 换行 chip 排) -->
          <div class="card">
            <div class="card-head">
              <span class="section-title">她的日记</span>
              <span v-if="detail.created_ts" class="write-at">写于 {{ fmtClock(detail.created_ts) }}</span>
            </div>
            <p class="prose">{{ detail.diary || '（这一天没有落笔）' }}</p>
            <div v-if="detail.key_events && detail.key_events.length" class="events">
              <span v-for="(k, i) in detail.key_events" :key="i" class="chip">{{ k }}</span>
            </div>
          </div>

          <!-- 当天心情曲线卡 -->
          <div class="card">
            <div class="card-head"><span class="section-title">当天心情</span></div>
            <Line v-if="curve.length" :data="lineData" :options="lineOptions" />
            <n-empty v-else size="small" description="当天无心情记录" />
          </div>
        </div>
      </n-spin>
    </template>
  </div>
</template>

<style scoped>
.m-diary {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.m-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.m-title {
  font-weight: 600;
  font-size: 16px;
}
/* 日期 chip 横向滚动条(一行装不下全部日期) */
.date-strip {
  display: flex;
  gap: var(--sp-2);
  overflow-x: auto;
  padding-bottom: 2px;
  flex-shrink: 0;
}
.date-chip {
  cursor: pointer;
  flex-shrink: 0;
  user-select: none;
}
.cards {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
}
/* 卡内首行小节标题去掉 tokens 默认的上边距 */
.card-head .section-title {
  margin-top: 0;
}
/* 梦/日记正文:保留换行、舒适行高 */
.prose {
  margin: var(--sp-2) 0 0;
  color: var(--text);
  font-size: var(--f-md);
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
.write-at {
  font-size: var(--f-xs);
  color: var(--text-faint);
}
.events {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
  margin-top: var(--sp-3);
}
</style>
