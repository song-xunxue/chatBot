<script setup lang="ts">
/**
 * 系统配置页(M7;2026-08-17 V3.0 精简):LLM provider 配置状态(只读)+ 重载配置 + 清空所有数据。
 * QQ 官方机器人凭证卡已删(V3.0 纯 QQ 号/OneBot 项目,无官方凭证概念)。
 * 清空所有数据:删运行时数据(对话/记忆/训练样本/评分/mood值/代答),保留人设+配置,需输入"清空"确认。
 * 2026-09-12 训练前置工具:人设盲测基准(A/B provider 对比)+ 训练数据导出(SFT/DPO)。
 * 作者: 李文煜
 */
import { ref, computed, onMounted } from 'vue'
import { NCard, NSpace, NButton, NTag, NSpin, NEmpty, NInput, NInputNumber, NModal,
         NSelect, NCollapse, NCollapseItem, useMessage } from 'naive-ui'
import { getSystemConfig, reloadSystem, resetAllData, benchmarkPersona, exportTraining } from '@/api'
import { useObject } from '@/composables/useObject'

const message = useMessage()
const { oid, ensureOid } = useObject()
const config = ref<any>(null)
const loading = ref(false)
const reloading = ref(false)

// 清空所有数据(危险操作)
const resetShow = ref(false)
const resetConfirm = ref('')
const resetting = ref(false)

// —— 人设盲测基准(训练前置 A2)——
const benchA = ref('glm')
const benchB = ref('local')
const benchN = ref(20)
const benchRunning = ref(false)
const benchResult = ref<any>(null)
const providerOptions = computed(() =>
  (config.value?.providers || []).map((p: any) => ({ label: p.name, value: p.name })))

async function runBenchmark() {
  if (!oid.value || oid.value === 'default') { message.warning('oid 未绑定真实会话'); return }
  benchRunning.value = true
  benchResult.value = null
  try {
    const r = await benchmarkPersona(oid.value, {
      provider_a: benchA.value, provider_b: benchB.value, n: benchN.value,
    })
    if (r.error) { message.error(r.message || r.error); return }
    benchResult.value = r
    message.success(`盲测完成:${r.a.provider} 均 ${r.a.avg ?? '—'} vs ${r.b.provider} 均 ${r.b.avg ?? '—'}`)
  } catch (e: any) { message.error('' + e) }
  finally { benchRunning.value = false }
}

// —— 训练数据导出(训练前置 B1)——
const exportMinScore = ref(85)
const exporting = ref(false)
const exportResult = ref<any>(null)

async function doExport() {
  if (!oid.value || oid.value === 'default') { message.warning('oid 未绑定真实会话'); return }
  exporting.value = true
  try {
    const r = await exportTraining(oid.value, { min_score: exportMinScore.value })
    exportResult.value = r
    message.success(`已导出:SFT ${r.sft} 条 + DPO ${r.dpo} 对`)
  } catch (e: any) { message.error('' + e) }
  finally { exporting.value = false }
}

async function load() {
  loading.value = true
  try {
    config.value = await getSystemConfig()
  } catch (e: any) { message.error('' + e) }
  finally { loading.value = false }
}

async function reload() {
  reloading.value = true
  try {
    const r = await reloadSystem()
    message.success(`配置已重载,可用 provider: ${r.providers.join(', ') || '无'}`)
    await load()
  } catch (e: any) { message.error('' + e) }
  finally { reloading.value = false }
}

function openReset() {
  resetConfirm.value = ''
  resetShow.value = true
}

async function doReset() {
  if (resetConfirm.value !== '清空') { message.warning('请输入"清空"二字确认'); return }
  resetting.value = true
  try {
    const r = await resetAllData()
    message.success(`已清空(删 ${r.deleted} 键,保留 ${r.kept} 键)`)
    resetShow.value = false
  } catch (e: any) { message.error('' + e) }
  finally { resetting.value = false }
}

onMounted(async () => { await ensureOid(); await load() })
</script>

<template>
  <n-space vertical size="large">
    <n-space align="center">
      <n-button type="primary" :loading="reloading" @click="reload">重载配置</n-button>
      <span style="color:#999;font-size:12px">改服务器 .env 后点击,新配置即时生效(不重启进程、不断连)</span>
    </n-space>
    <n-spin :show="loading">
      <n-card title="LLM Provider 配置状态">
        <n-empty v-if="!config" description="加载中..." />
        <n-space v-else vertical size="large">
          <div v-for="p in config.providers" :key="p.name"
               style="display:flex;align-items:center;gap:12px">
            <n-tag :type="p.available ? 'success' : 'default'" size="large">{{ p.name }}</n-tag>
            <n-tag :type="p.configured ? 'success' : 'warning'" size="small">
              {{ p.configured ? '已配置 key' : '未配置 key' }}
            </n-tag>
            <n-tag :type="p.available ? 'success' : 'error'" size="small">
              {{ p.available ? '可用' : '不可用' }}
            </n-tag>
          </div>
          <span style="color:#999;font-size:12px">共 {{ config.available.length }} 个 provider 可用(评分/反推/记忆编码会自动选用)</span>
        </n-space>
      </n-card>
    </n-spin>
    <!-- 训练前置:人设盲测基准(A2)——A/B provider 同上下文对比,固定裁判 -->
    <n-card title="人设盲测基准(训练前置)">
      <n-space vertical size="medium">
        <n-space align="center" :wrap="false">
          <n-select v-model:value="benchA" :options="providerOptions" size="small" style="width:150px" />
          <span style="font-size:12px;color:#666">vs</span>
          <n-select v-model:value="benchB" :options="providerOptions" size="small" style="width:150px" />
          <n-input-number v-model:value="benchN" :min="1" :max="30" size="small" style="width:100px" />
          <n-button type="primary" size="small" :loading="benchRunning" @click="runBenchmark">开始盲测</n-button>
        </n-space>
        <span style="color:#999;font-size:12px">
          取最近 N 条用户消息做上下文,两个 provider 各生成一遍,由固定裁判(云端评分链路)对照人设打分。
          本地 provider 经 frp 生成较慢,N=20 约需数分钟,请耐心等待。微调前后同法对比即可量化人设增益。
        </span>
        <template v-if="benchResult">
          <n-space align="center">
            <n-tag type="info" size="large">{{ benchResult.a.provider }}: 均 {{ benchResult.a.avg ?? '—' }} / {{ benchResult.a.count }} 条</n-tag>
            <n-tag type="success" size="large">{{ benchResult.b.provider }}: 均 {{ benchResult.b.avg ?? '—' }} / {{ benchResult.b.count }} 条</n-tag>
            <n-tag v-if="benchResult.a.errors || benchResult.b.errors" type="warning" size="small">
              失败 {{ benchResult.a.errors + benchResult.b.errors }} 条
            </n-tag>
          </n-space>
          <n-collapse>
            <n-collapse-item :title="`逐条样本(${benchResult.samples.length})`" name="s">
              <div v-for="(s, i) in benchResult.samples" :key="i"
                   style="border:1px solid #eee;border-radius:6px;padding:8px;margin:4px 0;font-size:12px">
                <div style="color:#888">用户:{{ s.user }}</div>
                <div style="display:flex;gap:8px;margin-top:4px">
                  <div style="flex:1;background:#f6ffed;border-radius:4px;padding:4px 8px">
                    <n-tag size="tiny" :type="s.a.score !== null ? 'success' : 'error'">{{ benchResult.a.provider }} {{ s.a.score ?? '失败' }}</n-tag>
                    <div style="margin-top:2px">{{ s.a.reply }}</div>
                  </div>
                  <div style="flex:1;background:#e8f1ff;border-radius:4px;padding:4px 8px">
                    <n-tag size="tiny" :type="s.b.score !== null ? 'success' : 'error'">{{ benchResult.b.provider }} {{ s.b.score ?? '失败' }}</n-tag>
                    <div style="margin-top:2px">{{ s.b.reply }}</div>
                  </div>
                </div>
              </div>
            </n-collapse-item>
          </n-collapse>
        </template>
      </n-space>
    </n-card>

    <!-- 训练前置:训练数据导出(B1)——SFT + DPO(LLaMA-Factory 格式) -->
    <n-card title="训练数据导出(训练前置)">
      <n-space vertical size="medium">
        <n-space align="center">
          <span style="font-size:13px">SFT 入选最低分</span>
          <n-input-number v-model:value="exportMinScore" :min="0" :max="100" size="small" style="width:100px" />
          <n-button type="primary" size="small" :loading="exporting" @click="doExport">导出训练数据</n-button>
        </n-space>
        <span style="color:#999;font-size:12px">
          从评分系统导出:pos 高分回复 / 手动回复 / 纠正回复 / 高分训练剧本 → SFT 集;纠正功能天然产出 DPO 偏好对
          (chosen=纠正文本,rejected=原回复)。LLaMA-Factory 格式 JSONL,写入服务器 server/data/training/。
        </span>
        <n-space v-if="exportResult" align="center" :wrap="true">
          <n-tag type="success">SFT {{ exportResult.sft }} 条</n-tag>
          <n-tag type="info">DPO {{ exportResult.dpo }} 对</n-tag>
          <n-tag v-for="(v, k) in exportResult.by_source" :key="k" size="small">{{ k }}: {{ v }}</n-tag>
        </n-space>
        <div v-if="exportResult" style="font-size:11px;color:#999;word-break:break-all">
          {{ exportResult.files.join(' ; ') }}
        </div>
      </n-space>
    </n-card>

    <n-card title="危险操作">
      <n-space vertical size="large">
        <span style="color:#999;font-size:12px">
          清空所有运行时数据(对话历史/训练样本/记忆/评分/mood值/代答队列),保留人设 + 心情档位 + 插件开关。<b style="color:#d03050">不可恢复</b>。
        </span>
        <n-button type="error" @click="openReset">清空所有数据</n-button>
      </n-space>
    </n-card>

    <!-- 清空确认弹窗(输入"清空"二次确认) -->
    <n-modal v-model:show="resetShow" preset="card" title="清空所有数据(危险操作)" style="width:480px;max-width:92vw">
      <n-space vertical :size="12">
        <div style="color:#d03050;font-size:13px">
          将清空:对话历史 / 训练样本 / 四级记忆 / 评分样本 / mood值+历史 / 代答队列。保留:人设 / 心情档位 / 插件开关。<b>不可恢复</b>。
        </div>
        <n-input v-model:value="resetConfirm" placeholder='输入"清空"二字确认' autofocus />
        <n-space justify="end">
          <n-button @click="resetShow = false">取消</n-button>
          <n-button type="error" :loading="resetting" :disabled="resetConfirm !== '清空'" @click="doReset">确认清空</n-button>
        </n-space>
      </n-space>
    </n-modal>
  </n-space>
</template>
