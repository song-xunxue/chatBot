<script setup lang="ts">
/**
 * 移动端心情系统页(功能对等 PC Mood.vue,5 Tab,窄屏重排):
 * ① 实时监控置顶(当前 mood + 档位 + 手动设置 mood + 近 50 点历史曲线,最高频)
 * ② 档位管理(增删改,PC 的行内编辑卡改 NModal 弹窗,删除由 dialog 改 NPopconfirm 二次确认)
 * ③ 全局参数(mood_step 等 4 滑条全宽) ④ 评分试算器 ⑤ 使用说明
 * 逻辑与 PC 端完全一致:共享 useObject 的 oid(reloadTick 联动重载);
 * 本页 PC 端无轮询,移动端同样不加轮询。
 * 仅 template 按窄屏重组:档位 tag 列表改卡片列表、删写死宽度→全宽、按钮 size large(touch≥44px)、
 * 编辑表单左右分栏改上下堆叠。
 * 作者: 李文煜
 */
import { ref, computed, watch, onMounted } from 'vue'
import { Line } from 'vue-chartjs'
import { Chart as ChartJS, Title, Tooltip, Legend, LineElement, PointElement, CategoryScale, LinearScale } from 'chart.js'
import {
  NTabs, NTabPane, NSpace, NInput, NInputNumber, NButton, NCard, NTag, NSlider, NEmpty, NDivider, NModal, NPopconfirm,
  useMessage,
} from 'naive-ui'
import {
  listMoodKinds, upsertMoodKind, deleteMoodKind,
  getMoodParams, setMoodParams, getMood, setMood, getMoodHistory, moodCalc,
} from '@/api'
import { useObject } from '@/composables/useObject'

ChartJS.register(Title, Tooltip, Legend, LineElement, PointElement, CategoryScale, LinearScale)

const message = useMessage()
const { oid, reloadTick, ensureOid } = useObject()
watch(reloadTick, () => loadMood())   // 头部切换会话 → 重载本页 mood 监控

// —— 档位管理 ——
const kinds = ref<any[]>([])
const editing = ref<any | null>(null)
const showEdit = ref(false)

async function loadKinds() {
  try { kinds.value = await listMoodKinds() } catch (e: any) { message.error('' + e) }
}
function startEdit(k?: any) {
  editing.value = k ? { ...k } : { key: '', label: '', mood_lo: 0, mood_hi: 1, kaomoji: '',
    prompt_hint: '', color: '#CCCCCC', score_bias: 0, bias_noise: 3, sort: 99 }
  showEdit.value = true
}
function closeEdit() { showEdit.value = false; editing.value = null }
async function saveKind() {
  try {
    await upsertMoodKind(editing.value)
    message.success('档位已保存')
    closeEdit()
    await loadKinds()
  } catch (e: any) { message.error('保存失败: ' + e) }
}
async function delKind(k: any) {
  try { await deleteMoodKind(k.key); message.success('已删除'); await loadKinds() }
  catch (e: any) { message.error('删除失败: ' + e) }
}

// —— 全局参数 ——
const params = ref<any>({ mood_step: 0.1, mood_decay: 0.05, mood_neutral: 0.5, mood_kaomoji_prob: 0.3 })
async function loadParams() {
  try { params.value = await getMoodParams() } catch (e: any) { message.error('' + e) }
}
async function saveParams() {
  try { params.value = await setMoodParams(params.value); message.success('参数已保存(apply_emotion/衰减即时生效)') }
  catch (e: any) { message.error('保存失败: ' + e) }
}

// —— 实时监控(PC 的 oid 输入框由共享 useObject 取代,MobileLayout 无头部输入)——
const moodInfo = ref<any>(null)
const moodHistory = ref<any[]>([])
const setMoodVal = ref(0.5)
async function loadMood() {
  if (!oid.value || oid.value === 'default') return
  try {
    moodInfo.value = await getMood(oid.value)
    moodHistory.value = await getMoodHistory(oid.value, 50)
    setMoodVal.value = moodInfo.value.mood
  } catch (e: any) { message.error('' + e) }
}
async function applySetMood() {
  try { await setMood(oid.value, setMoodVal.value); message.success('mood 已设置'); await loadMood() }
  catch (e: any) { message.error('' + e) }
}
const lineData = computed(() => ({
  labels: moodHistory.value.map((_, i) => `${i + 1}`),
  datasets: [{ label: 'mood', borderColor: '#36a3eb', backgroundColor: '#36a3eb33',
               data: moodHistory.value.map((h) => h.mood), tension: 0.3 }],
}))
const lineOptions = { responsive: true, scales: { y: { min: 0, max: 1 } }, plugins: { legend: { display: false } } }

// —— 评分试算器 ——
const calcBase = ref(80)
const calcMood = ref(0.8)
const calcResult = ref<any>(null)
async function doCalc() {
  try { calcResult.value = await moodCalc(oid.value, { score_base: calcBase.value, mood: calcMood.value }) }
  catch (e: any) { message.error('' + e) }
}

// 顶栏刷新:三路数据全量重载
async function loadAll() {
  await loadMood()
  loadKinds()
  loadParams()
}

onMounted(async () => {
  await ensureOid()
  await loadAll()
})
</script>

<template>
  <n-space vertical size="medium">
    <!-- 顶栏:标题 + 刷新(本页持有,不放 MobileLayout) -->
    <div class="m-topbar">
      <span class="m-title">心情系统</span>
      <n-button size="small" quaternary @click="loadAll">刷新</n-button>
    </div>

    <n-tabs type="line" animated default-value="monitor">
      <!-- 1. 实时监控(移动端置顶,最高频) -->
      <n-tab-pane name="monitor" tab="📊 监控">
        <n-space vertical size="medium">
          <div v-if="!oid || oid === 'default'" class="m-hint" style="color:#d03050">
            oid 未绑定真实会话(V3.0 须为 QQ 号):先在 QQ 上与角色对话一次即可自动绑定
          </div>
          <n-card title="当前心情">
            <n-empty v-if="!moodInfo" size="small" description="暂无 mood 数据(绑定会话后点右上刷新)" />
            <n-space v-else vertical size="medium">
              <div class="m-mood-row">
                <n-tag type="info">mood {{ moodInfo.mood }}</n-tag>
                <n-tag v-if="moodInfo.kind" :color="{ color: moodInfo.kind.color, textColor: '#fff' }">
                  {{ moodInfo.kind.kaomoji }} {{ moodInfo.kind.label }}
                </n-tag>
                <n-tag v-else>未匹配档位</n-tag>
              </div>
              <!-- 心情值进度条(0-1,竖线为中性点 0.5):窄屏替代性可视化,与曲线互补 -->
              <div class="m-mood-bar">
                <div class="m-mood-bar-fill"
                     :style="{ width: (moodInfo.mood * 100) + '%', background: (moodInfo.kind && moodInfo.kind.color) || '#36a3eb' }" />
                <span class="m-mood-neutral" />
              </div>
              <div class="m-hint">会话 {{ oid }};竖线为中性点 0.5,左低落右开心</div>
            </n-space>
          </n-card>
          <n-card title="手动设置 mood">
            <n-space vertical size="small">
              <n-slider v-model:value="setMoodVal" :min="0" :max="1" :step="0.01" />
              <n-input-number v-model:value="setMoodVal" :min="0" :max="1" :step="0.01" style="width:100%" />
              <n-button type="primary" size="large" block :disabled="!oid || oid === 'default'" @click="applySetMood">设置</n-button>
            </n-space>
          </n-card>
          <n-card title="mood 历史曲线(近 50 点)">
            <Line v-if="moodHistory.length" :data="lineData" :options="lineOptions" />
            <n-empty v-else size="small" description="无历史记录" />
          </n-card>
        </n-space>
      </n-tab-pane>

      <!-- 2. 档位管理(种类表 CRUD;tag 列表改卡片列表,编辑改 NModal) -->
      <n-tab-pane name="kinds" tab="🎭 档位">
        <n-space vertical size="medium">
          <n-space>
            <n-button type="primary" size="large" style="flex:1" @click="startEdit()">新增档位</n-button>
            <n-button size="large" @click="loadKinds">刷新</n-button>
          </n-space>
          <n-empty v-if="!kinds.length" size="small" description="暂无档位" />
          <div v-for="k in kinds" :key="k.key" class="m-kind-item" @click="startEdit(k)">
            <span class="m-kind-dot" :style="{ background: k.color }" />
            <div class="m-kind-main">
              <div class="m-kind-title">{{ k.kaomoji }} {{ k.label }}<span class="m-kind-key">{{ k.key }}</span></div>
              <div class="m-kind-sub">[{{ k.mood_lo }}-{{ k.mood_hi }}) bias={{ k.score_bias }} noise={{ k.bias_noise }} sort={{ k.sort }}</div>
            </div>
            <n-popconfirm @positive-click="delKind(k)">
              <template #trigger>
                <n-button size="medium" type="error" quaternary @click.stop>✕</n-button>
              </template>
              删除档位「{{ k.label }}」?(删后须仍覆盖 [0,1])
            </n-popconfirm>
          </div>
          <div class="m-hint">点卡片编辑档位;档位须完整覆盖 [0,1] 且范围不重叠。</div>
        </n-space>
      </n-tab-pane>

      <!-- 3. 全局参数(4 滑条全宽) -->
      <n-tab-pane name="params" tab="⚙️ 参数">
        <n-card>
          <n-space vertical size="large">
            <div v-for="(label, key) in { mood_step: '情感步长', mood_decay: '衰减幅度', mood_neutral: '中性值', mood_kaomoji_prob: '颜文字附加概率' }" :key="key">
              <div class="m-label">{{ label }} ({{ key }}): {{ (params as any)[key] }}</div>
              <n-slider v-model:value="(params as any)[key]" :min="0" :max="1" :step="0.01" />
            </div>
            <n-button type="primary" size="large" block @click="saveParams">保存参数</n-button>
            <n-button size="large" block @click="loadParams">重新读取</n-button>
          </n-space>
        </n-card>
      </n-tab-pane>

      <!-- 4. 评分试算器 -->
      <n-tab-pane name="calc" tab="🧮 试算">
        <n-card>
          <n-space vertical size="medium">
            <div>
              <div class="m-label">score_base(0-100)</div>
              <n-input-number v-model:value="calcBase" :min="0" :max="100" style="width:100%" />
            </div>
            <div>
              <div class="m-label">mood(0-1)</div>
              <n-input-number v-model:value="calcMood" :min="0" :max="1" :step="0.01" style="width:100%" />
            </div>
            <n-button type="primary" size="large" block :disabled="!oid || oid === 'default'" @click="doCalc">试算</n-button>
            <template v-if="calcResult">
              <n-divider />
              <div class="m-calc-result">
                <span>mood_bias =</span><n-tag>{{ calcResult.mood_bias }}</n-tag>
                <span>最终 score =</span>
                <n-tag :type="calcResult.score >= 85 ? 'success' : (calcResult.score < 60 ? 'error' : 'default')">
                  {{ calcResult.score }}
                </n-tag>
              </div>
            </template>
            <div class="m-hint">试算 = score_base + mood_bias(档位 score_bias 多次采样均值),调档位参数前可预演</div>
          </n-space>
        </n-card>
      </n-tab-pane>

      <!-- 5. 使用说明(低频,置底) -->
      <n-tab-pane name="doc" tab="📖 说明">
        <n-card>
          <div class="m-doc">
            <p><b>心情模型</b>:mood ∈ [0,1](0.5 中性),由对话关键词情感驱动(apply_emotion),周期向中性衰减。</p>
            <p><b>种类表(档位)</b>:把 [0,1] 离散成若干档(开心/愉悦/平静/低落/难过...),每档带颜文字 + 评分补偿 score_bias。</p>
            <p><b>评分补偿</b>:回复评分 score = score_base + mood_bias(档位 score_bias ± 噪声),心情影响打分。</p>
            <p><b>反推联动</b>:评分正/负样本驱动人设反推(Score 页)。</p>
            <p><b>注入</b>:pipeline 调 LLM 前把当前档位的 prompt_hint + 颜文字追加到 system_prompt,影响回复语气。</p>
          </div>
        </n-card>
      </n-tab-pane>
    </n-tabs>

    <!-- 档位编辑弹窗(PC 行内编辑卡 → 移动端 NModal,内容限高可滚) -->
    <n-modal v-model:show="showEdit" preset="card" :title="editing && editing.key ? '编辑档位' : '新增档位'" style="width:94vw">
      <div v-if="editing" class="m-modal-body">
        <n-space vertical :size="12">
          <div>
            <div class="m-label">key(英文唯一{{ editing.key && kinds.some((k) => k.key === editing.key) ? ',编辑中不可改' : '' }})</div>
            <n-input v-model:value="editing.key" :disabled="!!editing.key && kinds.some((k) => k.key === editing.key)" placeholder="如 happy / sad" />
          </div>
          <div>
            <div class="m-label">标签</div>
            <n-input v-model:value="editing.label" placeholder="如 开心" />
          </div>
          <div>
            <div class="m-label">颜文字</div>
            <n-input v-model:value="editing.kaomoji" placeholder="如 (≧▽≦)" />
          </div>
          <div>
            <div class="m-label">mood_lo(档位下界 0-1)</div>
            <n-input-number v-model:value="editing.mood_lo" :min="0" :max="1" :step="0.05" style="width:100%" />
          </div>
          <div>
            <div class="m-label">mood_hi(档位上界 0-1)</div>
            <n-input-number v-model:value="editing.mood_hi" :min="0" :max="1" :step="0.05" style="width:100%" />
          </div>
          <div>
            <div class="m-label">score_bias(评分补偿)</div>
            <n-input-number v-model:value="editing.score_bias" :step="1" style="width:100%" />
          </div>
          <div>
            <div class="m-label">bias_noise(补偿噪声)</div>
            <n-input-number v-model:value="editing.bias_noise" :step="1" style="width:100%" />
          </div>
          <div>
            <div class="m-label">sort(排序,小在前)</div>
            <n-input-number v-model:value="editing.sort" :step="1" style="width:100%" />
          </div>
          <div>
            <div class="m-label">prompt_hint(注入 system_prompt)</div>
            <n-input v-model:value="editing.prompt_hint" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="如 语气轻快,多用感叹号" />
          </div>
          <div>
            <div class="m-label">颜色(如 #36a3eb)</div>
            <n-input v-model:value="editing.color" placeholder="#CCCCCC" />
          </div>
          <n-space>
            <n-button type="primary" size="large" style="flex:1" @click="saveKind">保存</n-button>
            <n-button size="large" @click="closeEdit">取消</n-button>
          </n-space>
        </n-space>
      </div>
    </n-modal>
  </n-space>
</template>

<style scoped>
.m-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.m-title {
  font-weight: 600;
  font-size: 16px;
}
.m-label {
  font-size: 13px;
  color: #333;
  margin-bottom: 4px;
}
.m-hint {
  font-size: 11px;
  color: #999;
}
.m-kind-item {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 10px;
  cursor: pointer;
}
.m-kind-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
}
.m-kind-main {
  flex: 1;
  min-width: 0;
}
.m-kind-title {
  font-size: 14px;
  font-weight: 500;
}
.m-kind-key {
  font-size: 11px;
  color: #999;
  margin-left: 4px;
}
.m-kind-sub {
  font-size: 12px;
  color: #888;
  margin-top: 2px;
}
.m-mood-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.m-mood-bar {
  position: relative;
  height: 10px;
  border-radius: 5px;
  background: #eee;
  margin: 4px 0;
}
.m-mood-bar-fill {
  height: 100%;
  border-radius: 5px;
  transition: width 0.3s;
}
.m-mood-neutral {
  position: absolute;
  left: 50%;
  top: -2px;
  height: 14px;
  width: 1px;
  background: #999;
}
.m-calc-result {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.m-modal-body {
  max-height: 68vh;
  overflow-y: auto;
}
.m-doc p {
  margin: 0 0 10px;
  font-size: 13px;
  line-height: 1.7;
}
</style>
