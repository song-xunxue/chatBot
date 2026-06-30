<script setup lang="ts">
/**
 * 心情系统页(M7,5 Tab 顶级菜单,docs/03 §8):
 * 使用说明 / 档位管理(CRUD + 范围冲突校验)/ 全局参数 / 实时监控(mood 曲线)/ 评分试算器。
 * 作者: 李文煜
 */
import { ref, computed } from 'vue'
import { Line } from 'vue-chartjs'
import { Chart as ChartJS, Title, Tooltip, Legend, LineElement, PointElement, CategoryScale, LinearScale } from 'chart.js'
import {
  NTabs, NTabPane, NSpace, NInput, NInputNumber, NButton, NCard, NTag, NSlider, NEmpty, NDivider,
  useMessage, useDialog,
} from 'naive-ui'
import {
  listMoodKinds, upsertMoodKind, deleteMoodKind,
  getMoodParams, setMoodParams, getMood, setMood, getMoodHistory, moodCalc,
} from '@/api'

ChartJS.register(Title, Tooltip, Legend, LineElement, PointElement, CategoryScale, LinearScale)

const message = useMessage()
const dialog = useDialog()

// —— 档位管理 ——
const kinds = ref<any[]>([])
const editing = ref<any | null>(null)

async function loadKinds() { kinds.value = await listMoodKinds() }
function startEdit(k?: any) {
  editing.value = k ? { ...k } : { key: '', label: '', mood_lo: 0, mood_hi: 1, kaomoji: '',
    prompt_hint: '', color: '#CCCCCC', score_bias: 0, bias_noise: 3, sort: 99 }
}
async function saveKind() {
  try { await upsertMoodKind(editing.value); message.success('档位已保存'); editing.value = null; await loadKinds() }
  catch (e: any) { message.error('保存失败: ' + e) }
}
function delKind(k: any) {
  dialog.warning({
    title: '确认删除', content: `删除档位「${k.label}」?(删后须仍覆盖 [0,1])`,
    positiveText: '删', negativeText: '取消',
    onPositiveClick: async () => {
      try { await deleteMoodKind(k.key); message.success('已删除'); await loadKinds() }
      catch (e: any) { message.error('删除失败: ' + e) }
    },
  })
}

// —— 全局参数 ——
const params = ref<any>({ mood_step: 0.1, mood_decay: 0.05, mood_neutral: 0.5, mood_kaomoji_prob: 0.3 })
async function loadParams() { params.value = await getMoodParams() }
async function saveParams() {
  try { params.value = await setMoodParams(params.value); message.success('参数已保存(apply_emotion/衰减即时生效)') }
  catch (e: any) { message.error('保存失败: ' + e) }
}

// —— 实时监控 ——
const moodOid = ref('default')
const moodInfo = ref<any>(null)
const moodHistory = ref<any[]>([])
const setMoodVal = ref(0.5)
async function loadMood() {
  if (!moodOid.value) return
  moodInfo.value = await getMood(moodOid.value)
  moodHistory.value = await getMoodHistory(moodOid.value, 50)
  setMoodVal.value = moodInfo.value.mood
}
async function applySetMood() {
  try { await setMood(moodOid.value, setMoodVal.value); message.success('mood 已设置'); await loadMood() }
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
  try { calcResult.value = await moodCalc(moodOid.value, { score_base: calcBase.value, mood: calcMood.value }) }
  catch (e: any) { message.error('' + e) }
}

loadKinds(); loadParams()
</script>

<template>
  <n-tabs type="line" animated>
    <!-- 1. 使用说明 -->
    <n-tab-pane name="doc" tab="📖 使用说明">
      <n-card>
        <n-space vertical>
          <p><b>心情模型</b>:mood ∈ [0,1](0.5 中性),由对话关键词情感驱动(apply_emotion),周期向中性衰减。</p>
          <p><b>种类表(档位)</b>:把 [0,1] 离散成若干档(开心/愉悦/平静/低落/难过...),每档带颜文字 + 评分补偿 score_bias。</p>
          <p><b>评分补偿</b>:回复评分 score = score_base + mood_bias(档位 score_bias ± 噪声),心情影响打分。</p>
          <p><b>反推联动</b>:评分正/负样本驱动人设反推(Score 页)。</p>
          <p><b>注入</b>:pipeline 调 LLM 前把当前档位的 prompt_hint + 颜文字追加到 system_prompt,影响回复语气。</p>
        </n-space>
      </n-card>
    </n-tab-pane>

    <!-- 2. 档位管理 -->
    <n-tab-pane name="kinds" tab="🎭 档位管理">
      <n-space vertical>
        <n-space>
          <n-button type="primary" @click="startEdit()">新增档位</n-button>
          <n-button @click="loadKinds">刷新</n-button>
        </n-space>
        <n-space>
          <n-tag v-for="k in kinds" :key="k.key" :color="{ color: k.color, textColor: '#fff' }"
                 style="cursor:pointer;padding:6px 12px" @click="startEdit(k)">
            {{ k.kaomoji }} {{ k.label }} [{{ k.mood_lo }}-{{ k.mood_hi }}) bias={{ k.score_bias }}
            <span style="margin-left:6px;color:#fff8" @click.stop="delKind(k)">✕</span>
          </n-tag>
        </n-space>
        <n-card v-if="editing" :title="editing.key ? '编辑档位' : '新增档位'">
          <n-space vertical>
            <n-space>
              <n-input v-model:value="editing.key" placeholder="key(英文唯一)" :disabled="!!editing.key && kinds.some(k=>k.key===editing.key)" style="width:160px" />
              <n-input v-model:value="editing.label" placeholder="标签" style="width:140px" />
              <n-input v-model:value="editing.kaomoji" placeholder="颜文字" style="width:140px" />
            </n-space>
            <n-space align="center">
              mood_lo <n-input-number v-model:value="editing.mood_lo" :min="0" :max="1" :step="0.05" />
              mood_hi <n-input-number v-model:value="editing.mood_hi" :min="0" :max="1" :step="0.05" />
              score_bias <n-input-number v-model:value="editing.score_bias" :step="1" />
              bias_noise <n-input-number v-model:value="editing.bias_noise" :step="1" />
              sort <n-input-number v-model:value="editing.sort" :step="1" />
            </n-space>
            <n-input v-model:value="editing.prompt_hint" placeholder="prompt_hint(注入 system_prompt)" type="textarea" :autosize="{ minRows: 2 }" />
            <n-space>
              颜色 <n-input v-model:value="editing.color" style="width:120px" />
              <n-button type="primary" @click="saveKind">保存</n-button>
              <n-button @click="editing = null">取消</n-button>
            </n-space>
          </n-space>
        </n-card>
      </n-space>
    </n-tab-pane>

    <!-- 3. 全局参数 -->
    <n-tab-pane name="params" tab="⚙️ 全局参数">
      <n-card>
        <n-space vertical size="large">
          <div v-for="(label, key) in { mood_step: '情感步长', mood_decay: '衰减幅度', mood_neutral: '中性值', mood_kaomoji_prob: '颜文字附加概率' }" :key="key">
            <div>{{ label }} ({{ key }}): {{ (params as any)[key] }}</div>
            <n-slider v-model:value="(params as any)[key]" :min="0" :max="1" :step="0.01" />
          </div>
          <n-button type="primary" @click="saveParams">保存参数</n-button>
          <n-button @click="loadParams">重新读取</n-button>
        </n-space>
      </n-card>
    </n-tab-pane>

    <!-- 4. 实时监控 -->
    <n-tab-pane name="monitor" tab="📊 实时监控">
      <n-space vertical>
        <n-space align="center">
          <n-input v-model:value="moodOid" placeholder="object_id" style="width:220px" @keyup.enter="loadMood" />
          <n-button type="primary" @click="loadMood">查询</n-button>
        </n-space>
        <n-empty v-if="!moodInfo" description="输入 object_id 查询当前 mood" />
        <n-space v-else vertical size="large">
          <n-card>
            <n-space align="center">
              <span>当前 mood:</span>
              <n-tag type="info">{{ moodInfo.mood }}</n-tag>
              <span>档位:</span>
              <n-tag v-if="moodInfo.kind" :color="{ color: moodInfo.kind.color, textColor: '#fff' }">
                {{ moodInfo.kind.kaomoji }} {{ moodInfo.kind.label }}
              </n-tag>
              <n-tag v-else>未匹配档位</n-tag>
            </n-space>
          </n-card>
          <n-card title="手动设置 mood">
            <n-space align="center">
              <n-slider v-model:value="setMoodVal" :min="0" :max="1" :step="0.01" style="width:300px" />
              <n-input-number v-model:value="setMoodVal" :min="0" :max="1" :step="0.01" />
              <n-button type="primary" @click="applySetMood">设置</n-button>
            </n-space>
          </n-card>
          <n-card title="mood 历史曲线(近 50 点)">
            <Line v-if="moodHistory.length" :data="lineData" :options="lineOptions" />
            <n-empty v-else description="无历史记录" />
          </n-card>
        </n-space>
      </n-space>
    </n-tab-pane>

    <!-- 5. 评分试算器 -->
    <n-tab-pane name="calc" tab="🧮 评分试算器">
      <n-card>
        <n-space vertical>
          <n-space align="center">
            score_base <n-input-number v-model:value="calcBase" :min="0" :max="100" />
            mood <n-input-number v-model:value="calcMood" :min="0" :max="1" :step="0.01" />
            <n-button type="primary" @click="doCalc">试算</n-button>
          </n-space>
          <n-divider v-if="calcResult" />
          <n-space v-if="calcResult" align="center">
            <span>mood_bias =</span><n-tag>{{ calcResult.mood_bias }}</n-tag>
            <span>最终 score =</span>
            <n-tag :type="calcResult.score >= 85 ? 'success' : (calcResult.score < 60 ? 'error' : 'default')">
              {{ calcResult.score }}
            </n-tag>
          </n-space>
          <span style="color:#999;font-size:12px">试算 = score_base + mood_bias(档位 score_bias 多次采样均值),调档位参数前可预演</span>
        </n-space>
      </n-card>
    </n-tab-pane>
  </n-tabs>
</template>
