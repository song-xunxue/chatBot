<script setup lang="ts">
/**
 * 移动端插件管理(功能对等 PC Plugin.vue,窄屏重排):
 * ① 插件列表置顶(每插件 启用/禁用开关 + 重载,star 插件走 reloadStar)
 * ② 插件参数配置(config_schema 泛化表单:音色下拉+试听/开关/数字/文本,逐插件折叠展开)
 * ③ GPT-SoVITS 就绪检测折叠置底(四态徽标常显 / 强制重测 / 展开态 15s 心跳轮询,后台隐藏时暂停)
 * 逻辑与 PC 端完全一致(useObject 共享 oid + 相同 API),仅 template 按窄屏重组:
 * 删写死宽度→全宽、按钮 size large(touch≥44px)、表单 label 上置、列表行改卡片堆叠。
 * 作者: 李文煜
 */
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import {
  NCard, NSpace, NButton, NSwitch, NTag, NEmpty, NCollapse, NCollapseItem,
  NForm, NFormItem, NInputNumber, NInput, NSelect, useMessage,
} from 'naive-ui'
import {
  listPlugins, enablePlugin, disablePlugin, reloadPlugin, reloadStar,
  getPluginParams, setPluginParams, previewTTS, getGPTSoVITSStatus,
} from '@/api'
import { useObject } from '@/composables/useObject'

const message = useMessage()
const { oid, reloadTick, ensureOid } = useObject()
watch(reloadTick, () => load())

const plugins = ref<any[]>([])
const paramsMap = ref<Record<string, Record<string, any>>>({})

const pluginsWithConfig = computed(() =>
  plugins.value.filter(p => p.type === 'native' && p.config_schema && Object.keys(p.config_schema).length))

async function load() {
  plugins.value = await listPlugins()
  // 先初始化空对象,避免模板 v-model 访问 undefined(再异步填实际值)
  for (const p of pluginsWithConfig.value) {
    if (!paramsMap.value[p.name]) paramsMap.value[p.name] = {}
  }
  // oid 未绑定真实会话时参数暂不拉取(插件列表/开关/重载不依赖 oid,照常可用)
  if (!oid.value || oid.value === 'default') return
  await loadAllParams()
}

async function loadAllParams() {
  for (const p of pluginsWithConfig.value) {
    try {
      paramsMap.value[p.name] = await getPluginParams(p.name, oid.value)
    } catch (e) {
      /* 单个插件参数加载失败不阻塞(可能 oid 未就绪);展开时表单用默认空值 */
    }
  }
}

// 参数键 → 中文标签(常见键枚举;未知键回退原 key,与 PC 端一致)
const LABELS: Record<string, string> = {
  voice: '音色', speed: '语速', gain: '增益(dB)',
  emotion_enable: '情感推导', send_text_also: '同时发文本',
  top_k: 'Top K', top_p: 'Top P', temperature: '温度',
  batch_size: '批量大小', repetition_penalty: '重复惩罚',
  max_segments: '最大段数', min_segments: '最小段数',
  interval_min_ms: '段间最小(ms)', interval_max_ms: '段间最大(ms)',
  reply_delay_min_ms: '思考延迟最小(ms)', reply_delay_max_ms: '思考延迟最大(ms)',
  sample_steps: '采样步数', fragment_interval: '碎片间隔',
}
const labelOf = (key: string) => LABELS[key] || key

async function saveParams(p: any) {
  try {
    await setPluginParams(p.name, oid.value, paramsMap.value[p.name] || {})
    message.success(`${p.display_name || p.name} 参数已保存`)
  } catch (e: any) {
    message.error('保存失败: ' + e)
  }
}

// 音色试听(M-tts):点试听 → 调 /tts/preview 拿 mp3 blob → Audio.play 播放
const previewing = ref(false)
let audioEl: HTMLAudioElement | null = null
function stopPreview() {
  if (audioEl) { audioEl.pause(); audioEl = null }
}
async function previewVoice(p: any) {
  const voice = paramsMap.value[p.name]?.voice
  if (!voice) return
  try {
    previewing.value = true
    const blob = await previewTTS(voice)
    stopPreview()
    audioEl = new Audio(URL.createObjectURL(blob))
    await audioEl.play()
  } catch (e: any) {
    message.error('试听失败: ' + (e?.response?.status || e?.message || e))
  } finally {
    previewing.value = false
  }
}

async function toggle(p: any) {
  try {
    if (p.enabled) await disablePlugin(p.name)
    else await enablePlugin(p.name)
    message.success('已更新'); await load()
  } catch (e: any) { message.error('' + e) }
}
async function reload(p: any) {
  try {
    if (p.type === 'star') await reloadStar(p.name)
    else await reloadPlugin(p.name)
    message.success('已重载'); await load()
  } catch (e: any) { message.error('重载失败: ' + e) }
}

// —— GPT-SoVITS 本地模型就绪状态(M-tts-2:折叠懒检测 + 心跳缓存 + 展开轮询,照 PC)——
// 折叠态零开销(只 onMounted 读一次心跳缓存填徽标);展开才主动探测(心跳过期时);
// 展开态 15s 轮询只读心跳;移动端补充 visibilitychange 后台暂停(照 TakeoverMobile 轮询模式)
const ttsStatus = ref<any>(null)
const statusLoading = ref(false)
let statusTimer: any = null
const STATUS_POLL_MS = 15000
// 折叠面板展开项(n-collapse v-model;GSV 检测卡片默认折叠置底)
const gsvExpanded = ref<any>(null)
const gsvOpen = ref(false)

async function loadStatus(opts: { force?: boolean; probe?: boolean } = {}) {
  statusLoading.value = true
  try {
    ttsStatus.value = await getGPTSoVITSStatus(opts.force ?? false, opts.probe ?? true)
  } catch (e: any) {
    ttsStatus.value = { source: 'none', reachable: false, detail: '查询失败: ' + (e?.message || e) }
  } finally {
    statusLoading.value = false
  }
}

watch(gsvExpanded, (v) => {
  const on = Array.isArray(v) ? v.includes('gsv') : v === 'gsv'
  gsvOpen.value = on
  if (on) {
    loadStatus()                                                       // 展开:检测一次(心跳命中秒回,过期才探测)
    startStatusPoll()
  } else {
    stopStatusPoll()                                                   // 折叠:停轮询
  }
})

function startStatusPoll() {
  stopStatusPoll()
  statusTimer = setInterval(() => {
    if (typeof document !== 'undefined' && document.hidden) return
    loadStatus({ probe: false })                                       // 展开态每15s 跟随心跳(只读不探)
  }, STATUS_POLL_MS)
}
function stopStatusPoll() {
  if (statusTimer) { clearInterval(statusTimer); statusTimer = null }
}
// 页面隐藏暂停轮询省流量;回前台立即跟随一次心跳并恢复轮询(仅展开态)
function onVis() {
  if (document.hidden) { stopStatusPoll(); return }
  if (gsvOpen.value) { loadStatus({ probe: false }); startStatusPoll() }
}

// 状态徽标(四态:就绪/在线·配置缺/未连接/非本地/检测中)
const statusTag = computed(() => {
  const s = ttsStatus.value
  if (!s) return { type: 'default', text: '检测中…' }
  if ((s.tts_provider || '').toLowerCase() !== 'gptsovits')
    return { type: 'default', text: `非本地 TTS（${s.tts_provider || '-'}）` }
  if (s.reachable && s.config_ok) return { type: 'success', text: '就绪' }
  if (s.reachable && !s.config_ok) return { type: 'warning', text: '在线·配置缺' }
  return { type: 'error', text: '未连接' }
})

onMounted(async () => {
  await ensureOid()
  await load()
  loadStatus({ probe: false })   // 进页只读心跳缓存填徽标(不打 frp);展开才主动探测
  window.addEventListener('visibilitychange', onVis)
})
onUnmounted(() => {
  stopStatusPoll()
  stopPreview()
  window.removeEventListener('visibilitychange', onVis)
})
</script>

<template>
  <n-space vertical size="medium">
    <!-- 顶栏:标题 + 刷新(本页持有,不放 MobileLayout) -->
    <div class="m-topbar">
      <span class="m-title">插件管理</span>
      <n-button size="small" quaternary @click="load">刷新</n-button>
    </div>

    <!-- ① 插件列表(置顶,高频:开关 + 重载) -->
    <n-card title="插件列表(原生 + .star)">
      <n-empty v-if="!plugins.length" size="small" description="无已加载插件" />
      <n-space v-else vertical size="medium">
        <div v-for="p in plugins" :key="p.name + p.type" class="m-plugin-card">
          <div class="m-plugin-head">
            <n-tag :type="p.type === 'star' ? 'warning' : 'info'" size="small">{{ p.type }}</n-tag>
            <span class="m-plugin-name">{{ p.display_name || p.name }}</span>
          </div>
          <div v-if="p.description" class="m-plugin-desc">{{ p.description }}</div>
          <div class="m-plugin-ops">
            <n-switch v-if="p.type === 'native'" size="large" :value="!!p.enabled" @update:value="() => toggle(p)" />
            <span v-else class="m-hint">star 插件无启停</span>
            <n-button size="large" tertiary @click="reload(p)">重载</n-button>
          </div>
        </div>
      </n-space>
    </n-card>

    <!-- ② 插件参数配置(config_schema 泛化表单,逐插件折叠) -->
    <n-card v-if="pluginsWithConfig.length" title="插件参数配置">
      <span class="m-hint">展开配置各插件参数(音色/语速/gain/开关等),改完点保存。</span>
      <div v-if="!oid || oid === 'default'" class="m-hint" style="color:#d03050;margin-top:4px">
        oid 未绑定真实会话(V3.0 须为 QQ 号),参数暂未拉取:先在 QQ 上与角色对话一次即可自动绑定
      </div>
      <n-collapse style="margin-top:8px">
        <n-collapse-item v-for="p in pluginsWithConfig" :key="p.name" :name="p.name"
                         :title="`${p.display_name || p.name} 参数`">
          <n-form label-placement="top" :show-feedback="false">
            <n-form-item v-for="(spec, key) in p.config_schema" :key="String(key)"
                         :label="labelOf(String(key))">
              <div class="m-field">
                <!-- 音色:下拉 + 试听(同一行,下拉 flex 占满) -->
                <div v-if="String(key) === 'voice' && spec.options" class="m-voice-row">
                  <n-select v-model:value="paramsMap[p.name].voice" :options="spec.options" size="large" class="m-flex1" />
                  <n-button size="large" :loading="previewing" @click="previewVoice(p)">试听</n-button>
                </div>
                <n-switch v-else-if="spec.type === 'bool'" size="large"
                          v-model:value="paramsMap[p.name][String(key)]" />
                <n-input-number v-else-if="spec.type === 'number'" size="large" class="m-full"
                          v-model:value="paramsMap[p.name][String(key)]"
                          :min="spec.min" :max="spec.max" :step="spec.step || 1" />
                <n-select v-else-if="spec.type === 'string' && spec.options" size="large" class="m-full"
                          v-model:value="paramsMap[p.name][String(key)]"
                          :options="spec.options" />
                <n-input v-else-if="spec.type === 'string'" size="large" class="m-full"
                         type="textarea" :autosize="{ minRows: 1, maxRows: 4 }"
                         v-model:value="paramsMap[p.name][String(key)]" />
                <span v-if="spec.description" class="m-hint">{{ spec.description }}</span>
              </div>
            </n-form-item>
          </n-form>
          <n-button size="large" type="primary" block @click="saveParams(p)">保存</n-button>
        </n-collapse-item>
      </n-collapse>
    </n-card>

    <!-- ③ GPT-SoVITS 就绪检测(低频诊断,折叠置底;徽标常显于标题行) -->
    <n-collapse v-model:expanded-names="gsvExpanded">
      <n-collapse-item name="gsv">
        <template #header>
          <n-space align="center" :wrap="false" size="small">
            <span>本地语音合成（GPT-SoVITS）</span>
            <n-tag :type="statusTag.type" size="small" round>{{ statusTag.text }}</n-tag>
          </n-space>
        </template>
        <n-space vertical size="small">
          <n-button size="large" block :loading="statusLoading" @click="loadStatus({ force: true })">
            重新检测（强制探测）
          </n-button>
          <div v-if="ttsStatus?.source === 'heartbeat'" class="m-hint">心跳缓存命中（未探测隧道）</div>
          <div v-else-if="ttsStatus?.source === 'probe'" class="m-hint">主动探测</div>
          <div class="m-gsv-line">
            <div>api_base：{{ ttsStatus?.api_base || '-' }}</div>
            <div>状态：{{ ttsStatus?.detail || '-' }}</div>
            <div v-if="ttsStatus?.reachable">延迟：{{ ttsStatus?.latency_ms ?? '-' }} ms</div>
            <div v-if="ttsStatus?.missing?.length" style="color:#a08400">
              配置缺失：{{ ttsStatus.missing.join('、') }}
            </div>
          </div>
        </n-space>
      </n-collapse-item>
    </n-collapse>
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
.m-plugin-card {
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 10px;
}
.m-plugin-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.m-plugin-name {
  font-weight: 600;
  font-size: 14px;
}
.m-plugin-desc {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}
.m-plugin-ops {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
}
.m-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
}
.m-voice-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}
.m-flex1 {
  flex: 1;
  min-width: 0;
}
.m-full {
  width: 100%;
}
.m-gsv-line {
  font-size: 13px;
  line-height: 1.8;
  word-break: break-all;
}
.m-hint {
  font-size: 11px;
  color: #999;
}
</style>
