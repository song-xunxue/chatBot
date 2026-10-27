<script setup lang="ts">
/**
 * 日记页(桌面,2026-10-26 dream 插件出品:她睡着以后的梦境与日记):
 * 左栏日期列表(tone 标签 + 摘要,激活行暖色竖条)+ 右栏详情三卡
 * (她的梦 / 她的日记 + key_events / 当天心情曲线,暖色调);
 * 页头"立即补做"手动给今天生成一次(POST /api/v1/diary/run,传全局共享 oid)。
 * 列表/详情不依赖 oid;404 显示空态而非报错。
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
const { oid, reloadTick } = useObject()   // 全局共享 object_id(补做传参) + 头部回车刷新信号
// oid 就绪守卫(与 DiaryMobile 对齐):default 占位会话不做梦,后端同口径 400
const oidReady = computed(() => !!oid.value && oid.value !== 'default')

// tone → 文案/配色映射(positive 暖色甜梦 / negative 红色噩梦 / neutral 灰色平静)
function toneLabel(t: string): string {
  return t === 'positive' ? '甜梦' : t === 'negative' ? '噩梦' : '平静'
}
function toneClass(t: string): string {
  return t === 'positive' ? 'chip-warm' : t === 'negative' ? 'chip-danger' : ''
}

// —— 左栏:日期列表(倒序,最近 30 天)——
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

// —— 右栏:单日详情 ——
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
    // 404(详情被删/日期越界)不算错误,右栏空态提示;其余弹错
    if (e?.response?.status === 404) notFound.value = true
    else message.error('' + e)
  } finally { loadingDetail.value = false }
}

// 右栏空态文案:列表有货但未选中 → 引导;完全没日记 → 提示开 dream 插件
const emptyText = computed(() => entries.value.length
  ? '点左侧日期，查看那天的梦与日记'
  : '还没有日记。要么她还没做过梦，要么你还没开启 dream 插件（面板 → 插件 → 做梦与日记）')

// —— 立即补做(给今天手动跑一次 dream,LLM 生成耗时较长)——
const running = ref(false)
async function runToday() {
  if (!oidReady.value) {
    message.error('先在头部选择真实 QQ 会话再补做(default 占位会话不做梦)')
    return
  }
  running.value = true
  try {
    const entry = await runDiary({ object_id: oid.value })
    message.success(`已生成 ${entry?.date || ''} 的梦与日记`)
    await loadList()
    if (entry?.date) await select(entry.date)   // 刷新后选中新写的一天
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

watch(reloadTick, () => loadList())   // 头部 OID 回车 → 重载列表
onMounted(loadList)
</script>

<template>
  <div class="diary-page">
    <!-- 页头:标题 + 一句话说明 + 右侧"立即补做"(生成中置灰防重复触发) -->
    <div class="page-header page-header-center">
      <div>
        <h1 class="page-title">日记</h1>
        <div class="page-subtitle">她睡着以后，会做梦，也会写日记</div>
      </div>
      <n-popconfirm @positive-click="runToday">
        <template #trigger>
          <button class="btn btn-primary" :disabled="running || !oidReady">{{ running ? '生成中…' : '立即补做' }}</button>
        </template>
        给今天手动生成一次梦与日记？（需当天有对话素材且 LLM 可用）
      </n-popconfirm>
    </div>

    <div class="diary-body">
      <!-- 左栏:日期列表(激活行暖色竖条点缀) -->
      <div class="diary-side">
        <div class="side-head">
          <span>最近的梦（{{ entries.length }}）</span>
          <n-button size="tiny" quaternary :loading="loadingList" @click="loadList">刷新</n-button>
        </div>
        <n-empty v-if="!entries.length && !loadingList" size="small" description="还没有日记" />
        <div v-for="e in entries" :key="e.date"
             class="list-row diary-row" :class="{ active: e.date === selectedDate }"
             @click="select(e.date)">
          <div class="row-main">
            <div class="row-top">
              <span class="row-date">{{ e.date }}</span>
              <span class="chip" :class="toneClass(e.tone)">{{ toneLabel(e.tone) }}</span>
            </div>
            <div v-if="e.excerpt" class="row-excerpt">{{ e.excerpt }}</div>
          </div>
        </div>
      </div>

      <!-- 右栏:详情三卡 -->
      <div class="diary-main">
        <n-spin :show="loadingDetail">
          <div v-if="notFound" class="empty-state">
            <span class="empty-icon">🌙</span>
            <span>这一天的日记不存在</span>
          </div>
          <div v-else-if="!detail" class="empty-state">
            <span class="empty-icon">🌙</span>
            <span>{{ emptyText }}</span>
          </div>
          <div v-else class="detail-cards">
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

            <!-- 日记卡(正文 + key_events 一排 chip) -->
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
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 整页占满内容区(顶栏 52 + 上下 padding 20*2,同 History.vue 的 calc 口径) */
.diary-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 92px);
}
/* tokens 的 page-header 按 baseline 对齐,本页右侧是按钮需垂直居中 */
.page-header-center {
  align-items: center;
  flex-shrink: 0;
}
.diary-body {
  flex: 1;
  min-height: 0;
  display: flex;
}
/* 左栏:固定宽日期列表 */
.diary-side {
  width: 230px;
  flex-shrink: 0;
  overflow: auto;
  padding: 8px;
  border-right: 1px solid var(--border);
}
.side-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}
/* 日期行(复用 tokens 的 .list-row;激活态换暖色系 + 左侧 2px 暖色竖条) */
.diary-row {
  cursor: pointer;
  flex-direction: column;
  align-items: stretch;
  position: relative;
  padding-left: 14px;
}
.diary-row.active {
  background: var(--warm-dim);
  border-color: rgba(242, 163, 179, 0.3);
}
.diary-row.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 2px;
  border-radius: 1px;
  background: var(--warm);
}
.row-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.row-date {
  font-size: 13px;
  font-weight: 600;
}
.diary-row.active .row-date {
  color: var(--warm);
}
.row-excerpt {
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* 右栏:详情滚动区 */
.diary-main {
  flex: 1;
  min-width: 0;
  overflow: auto;
  padding-left: 16px;
}
.detail-cards {
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
