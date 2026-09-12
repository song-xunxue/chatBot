<script setup lang="ts">
/**
 * 移动端系统配置页(功能对等 PC System.vue,窄屏重排):
 * ① 重载配置(改服务器 .env 后热生效) ② LLM Provider 配置状态(只读) ③ 危险操作:清空所有数据(弹窗输入"清空"强确认)。
 * 逻辑与 PC 端完全一致(同 getSystemConfig / reloadSystem / resetAllData 三接口);PC 端无轮询,移动端同样不加轮询。
 * oid 说明:系统配置为全局接口(PC 端不依赖 oid),故 load() 不做 oid 守卫(守卫会在 oid=default 时空白,删功能);
 * 仅保留 useObject 接线(reloadTick 联动刷新 + ensureOid 预取,与其它移动页共享单例)。
 * 窄屏重组:按钮 size=large 全宽(触摸≥44px)、provider 三标签卡片化换行、确认弹窗 92vw 全宽、确认输入改 textarea。
 * 鉴权:无 token 时 router 守卫跳登录页,axios 拦截器自动注入 X-Access-Token。
 * 作者: 李文煜
 */
import { ref, computed, onMounted, watch } from 'vue'
import { NCard, NSpace, NButton, NTag, NSpin, NEmpty, NInput, NInputNumber, NModal,
         NSelect, NCollapse, NCollapseItem, useMessage } from 'naive-ui'
import { getSystemConfig, reloadSystem, resetAllData, benchmarkPersona, exportTraining } from '@/api'
import { useObject } from '@/composables/useObject'

const message = useMessage()
// oid 接线(共享单例):系统页为全局配置不消费 oid,保留 reloadTick/ensureOid 以与其它移动页行为一致
const { oid, reloadTick, ensureOid } = useObject()
watch(reloadTick, () => load())

const config = ref<any>(null)
const loading = ref(false)
const reloading = ref(false)

// —— 人设盲测基准(训练前置 A2,2026-09-12)——
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

// 清空所有数据(危险操作)
const resetShow = ref(false)
const resetConfirm = ref('')
const resetting = ref(false)

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

onMounted(async () => {
  await ensureOid()
  await load()
})
</script>

<template>
  <n-space vertical size="medium">
    <!-- 顶栏:标题 + 刷新(本页持有,不放 MobileLayout) -->
    <div class="m-topbar">
      <span class="m-title">系统配置</span>
      <n-button size="small" quaternary @click="load">刷新</n-button>
    </div>

    <!-- ① 重载配置(高频操作置顶,全宽大按钮) -->
    <n-card title="重载配置">
      <n-space vertical size="small">
        <n-button type="primary" size="large" block :loading="reloading" @click="reload">重载配置</n-button>
        <div class="m-hint">改服务器 .env 后点击,新配置即时生效(不重启进程、不断连)</div>
      </n-space>
    </n-card>

    <!-- ② LLM Provider 配置状态(只读;PC 的横排三标签改卡片内换行) -->
    <n-card title="LLM Provider 配置状态">
      <n-spin :show="loading">
        <n-empty v-if="!config" size="small" description="加载中..." />
        <n-space v-else vertical size="medium">
          <div v-for="p in config.providers" :key="p.name" class="m-prov">
            <n-tag :type="p.available ? 'success' : 'default'" size="large">{{ p.name }}</n-tag>
            <n-tag :type="p.configured ? 'success' : 'warning'" size="small">
              {{ p.configured ? '已配置 key' : '未配置 key' }}
            </n-tag>
            <n-tag :type="p.available ? 'success' : 'error'" size="small">
              {{ p.available ? '可用' : '不可用' }}
            </n-tag>
          </div>
          <div class="m-hint">共 {{ config.available.length }} 个 provider 可用(评分/反推/记忆编码会自动选用)</div>
        </n-space>
      </n-spin>
    </n-card>

    <!-- 训练前置:人设盲测基准(A2)——窄屏竖排控件 -->
    <n-card title="人设盲测基准(训练前置)">
      <n-space vertical size="small">
        <n-space vertical size="small">
          <n-select v-model:value="benchA" :options="providerOptions" size="large" />
          <n-select v-model:value="benchB" :options="providerOptions" size="large" />
        </n-space>
        <n-space align="center">
          <n-input-number v-model:value="benchN" :min="1" :max="30" size="large" style="width:110px" />
          <n-button type="primary" size="large" style="flex:1" :loading="benchRunning" @click="runBenchmark">开始盲测</n-button>
        </n-space>
        <div class="m-hint">两 provider 同上下文各生成,固定裁判(云端评分链路)打分;本地经 frp 较慢,N=20 约数分钟</div>
        <template v-if="benchResult">
          <n-space>
            <n-tag type="info" size="large">{{ benchResult.a.provider }} 均 {{ benchResult.a.avg ?? '—' }}</n-tag>
            <n-tag type="success" size="large">{{ benchResult.b.provider }} 均 {{ benchResult.b.avg ?? '—' }}</n-tag>
          </n-space>
          <n-collapse>
            <n-collapse-item :title="`逐条样本(${benchResult.samples.length})`" name="s">
              <div v-for="(s, i) in benchResult.samples" :key="i" class="m-sample">
                <div style="color:#888">用户:{{ s.user }}</div>
                <div class="m-sample-side" style="background:#f6ffed">
                  <n-tag size="tiny" :type="s.a.score !== null ? 'success' : 'error'">{{ benchResult.a.provider }} {{ s.a.score ?? '失败' }}</n-tag>
                  <div>{{ s.a.reply }}</div>
                </div>
                <div class="m-sample-side" style="background:#e8f1ff">
                  <n-tag size="tiny" :type="s.b.score !== null ? 'success' : 'error'">{{ benchResult.b.provider }} {{ s.b.score ?? '失败' }}</n-tag>
                  <div>{{ s.b.reply }}</div>
                </div>
              </div>
            </n-collapse-item>
          </n-collapse>
        </template>
      </n-space>
    </n-card>

    <!-- 训练前置:训练数据导出(B1) -->
    <n-card title="训练数据导出(训练前置)">
      <n-space vertical size="small">
        <n-space align="center">
          <n-input-number v-model:value="exportMinScore" :min="0" :max="100" size="large" style="width:110px" />
          <n-button type="primary" size="large" style="flex:1" :loading="exporting" @click="doExport">导出训练数据</n-button>
        </n-space>
        <div class="m-hint">pos 高分/手动/纠正/高分剧本 → SFT;纠正功能天然产出 DPO 偏好对。LLaMA-Factory 格式,写服务器 server/data/training/</div>
        <n-space v-if="exportResult" :wrap="true">
          <n-tag type="success">SFT {{ exportResult.sft }} 条</n-tag>
          <n-tag type="info">DPO {{ exportResult.dpo }} 对</n-tag>
        </n-space>
      </n-space>
    </n-card>

    <!-- ③ 危险操作(红色强调,置底) -->
    <n-card title="危险操作">
      <n-space vertical size="medium">
        <div class="m-hint">
          清空所有运行时数据(对话历史/训练样本/记忆/评分/mood值/代答队列),保留人设 + 心情档位 + 插件开关。<b class="m-danger">不可恢复</b>。
        </div>
        <n-button type="error" size="large" block @click="openReset">清空所有数据</n-button>
      </n-space>
    </n-card>

    <!-- 清空确认弹窗(输入"清空"二字强确认;窄屏 92vw 全宽,内容可滚动) -->
    <n-modal
      v-model:show="resetShow"
      preset="card"
      title="清空所有数据(危险操作)"
      style="width:92vw;max-width:480px"
    >
      <n-space vertical :size="12">
        <div class="m-danger-text">
          将清空:对话历史 / 训练样本 / 四级记忆 / 评分样本 / mood值+历史 / 代答队列。保留:人设 / 心情档位 / 插件开关。<b>不可恢复</b>。
        </div>
        <n-input
          v-model:value="resetConfirm"
          type="textarea"
          placeholder='输入"清空"二字确认'
          :autosize="{ minRows: 1, maxRows: 2 }"
          autofocus
        />
        <div class="m-modal-actions">
          <n-button size="large" style="flex:1" @click="resetShow = false">取消</n-button>
          <n-button type="error" size="large" style="flex:1" :loading="resetting" :disabled="resetConfirm !== '清空'" @click="doReset">确认清空</n-button>
        </div>
      </n-space>
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
.m-prov {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 10px;
}
.m-hint {
  font-size: 11px;
  color: #999;
}
.m-danger {
  color: #d03050;
}
.m-danger-text {
  color: #d03050;
  font-size: 13px;
}
.m-sample {
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 8px;
  margin: 4px 0;
  font-size: 12px;
}
.m-sample-side {
  border-radius: 4px;
  padding: 4px 8px;
  margin-top: 4px;
  word-break: break-all;
}
.m-modal-actions {
  display: flex;
  gap: 12px;
}
</style>
