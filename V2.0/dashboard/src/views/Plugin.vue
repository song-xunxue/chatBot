<script setup lang="ts">
/**
 * 插件管理(V2.0 M7 + M-tts 2026-08-04):原生 + .star 列表 + 启用/禁用 + 热重载 + 参数配置。
 * 参数配置为 M-tts 新增的泛化能力:凡 plugin.yaml 声明 config_schema 的插件自动渲染表单
 * (音色下拉/语速/gain/开关等),单人设 object_id 取 useObject 全局 oid。顺带让 continuous_send 等也可配。
 * 作者: 李文煜
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
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
const { oid, ensureOid } = useObject()
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
  await loadAllParams()
}

async function loadAllParams() {
  await ensureOid()
  for (const p of pluginsWithConfig.value) {
    try {
      paramsMap.value[p.name] = await getPluginParams(p.name, oid.value)
    } catch (e) {
      /* 单个插件参数加载失败不阻塞(可能 oid 未就绪);展开时表单用默认空值 */
    }
  }
}

// 参数键 → 中文标签(常见键枚举;未知键回退原 key)
const LABELS: Record<string, string> = {
  voice: '音色', speed: '语速', gain: '增益(dB)',
  emotion_enable: '情感推导', send_text_also: '同时发文本',
  top_k: 'Top K', top_p: 'Top P', temperature: '温度',
  batch_size: '批量大小', repetition_penalty: '重复惩罚',
  max_segments: '最大段数', min_segments: '最小段数',
  interval_min_ms: '段间最小(ms)', interval_max_ms: '段间最大(ms)',
  reply_delay_min_ms: '思考延迟最小(ms)', reply_delay_max_ms: '思考延迟最大(ms)',
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

// 音色试听(M-tts 2026-08-04):点试听 → 调 /tts/preview 拿 mp3 blob → Audio.play 播放
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

// —— GPT-SoVITS 本地模型就绪状态(M-tts-2,2026-08-10:折叠懒检测 + 心跳缓存 + 展开轮询)——
// 折叠态零开销(只 onMounted 读一次心跳缓存填标题点);展开才主动探测(心跳过期时);展开态轮询只读心跳
const ttsStatus = ref<any>(null)
const statusLoading = ref(false)
const statusExpanded = ref(false)
let statusTimer: any = null

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

function onStatusExpand(val: boolean) {
  statusExpanded.value = val
  if (val) {
    loadStatus()                                        // 展开:检测一次(心跳命中秒回,过期才探测)
    statusTimer = setInterval(() => loadStatus({ probe: false }), 15000)  // 展开态每15s 跟随心跳(只读不探)
  } else if (statusTimer) {
    clearInterval(statusTimer)                          // 折叠:停轮询
    statusTimer = null
  }
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

onMounted(() => {
  load()
  loadStatus({ probe: false })   // 进页只读心跳缓存填标题点(不打 frp);展开才主动探测
})
onUnmounted(() => { if (statusTimer) clearInterval(statusTimer) })
</script>

<template>
  <n-space vertical size="large">
    <!-- 本地语音合成(GPT-SoVITS)就绪状态:折叠懒检测,展开轮询跟随心跳 -->
    <n-card size="small">
      <template #header>
        <n-space align="center" :wrap="false" size="small">
          <span>本地语音合成（GPT-SoVITS）</span>
          <n-tag :type="statusTag.type" size="small" round>{{ statusTag.text }}</n-tag>
        </n-space>
      </template>
      <template #header-extra>
        <n-switch :value="statusExpanded" @update:value="onStatusExpand" size="small" />
      </template>
      <div v-if="statusExpanded">
        <n-space vertical size="small">
          <n-space align="center" size="small">
            <n-button size="small" :loading="statusLoading" @click="loadStatus({ force: true })">
              重新检测（强制探测）
            </n-button>
            <span style="font-size:12px;color:#999" v-if="ttsStatus?.source === 'heartbeat'">心跳缓存命中（未探测隧道）</span>
            <span style="font-size:12px;color:#999" v-else-if="ttsStatus?.source === 'probe'">主动探测</span>
          </n-space>
          <div style="font-size:13px;line-height:1.8">
            <div>api_base：{{ ttsStatus?.api_base || '-' }}</div>
            <div>状态：{{ ttsStatus?.detail || '-' }}</div>
            <div v-if="ttsStatus?.reachable">延迟：{{ ttsStatus?.latency_ms ?? '-' }} ms</div>
            <div v-if="ttsStatus?.missing?.length" style="color:#a08400">
              配置缺失：{{ ttsStatus.missing.join('、') }}
            </div>
          </div>
        </n-space>
      </div>
    </n-card>

    <n-space><n-button @click="load">刷新插件</n-button></n-space>

    <n-card title="插件列表(原生 + .star)" size="small">
      <n-empty v-if="!plugins.length" description="无已加载插件" />
      <div v-for="p in plugins" :key="p.name + p.type"
           style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid #f0f0f0">
        <n-tag :type="p.type === 'star' ? 'warning' : 'info'" size="small">{{ p.type }}</n-tag>
        <span style="font-weight:600;min-width:120px">{{ p.display_name || p.name }}</span>
        <span style="color:#999;font-size:12px;flex:1">{{ p.description || '' }}</span>
        <n-switch v-if="p.type === 'native'" :value="!!p.enabled" @update:value="() => toggle(p)" />
        <n-button size="tiny" @click="reload(p)">重载</n-button>
      </div>
    </n-card>

    <n-card v-if="pluginsWithConfig.length" title="插件参数配置" size="small">
      <span style="color:#999;font-size:12px">展开配置各插件参数(音色/语速/gain/开关等),改完点保存。</span>
      <n-collapse style="margin-top:8px">
        <n-collapse-item v-for="p in pluginsWithConfig" :key="p.name" :name="p.name"
                         :title="`${p.display_name || p.name} 参数`">
          <n-form label-placement="left" :show-feedback="false" style="padding:4px 0">
            <n-form-item v-for="(spec, key) in p.config_schema" :key="String(key)"
                         :label="labelOf(String(key))" style="margin-bottom:10px">
              <div style="display:flex;flex-direction:column;gap:2px">
                <n-space v-if="String(key) === 'voice' && spec.options" align="center" :wrap="false">
                  <n-select v-model:value="paramsMap[p.name].voice" :options="spec.options" style="width:200px" />
                  <n-button size="small" :loading="previewing" @click="previewVoice(p)">试听</n-button>
                </n-space>
                <n-switch v-else-if="spec.type === 'bool'"
                          v-model:value="paramsMap[p.name][String(key)]" />
                <n-input-number v-else-if="spec.type === 'number'"
                          v-model:value="paramsMap[p.name][String(key)]"
                          :min="spec.min" :max="spec.max" :step="spec.step || 1" />
                <n-select v-else-if="spec.type === 'string' && spec.options"
                          v-model:value="paramsMap[p.name][String(key)]"
                          :options="spec.options" style="width:220px" />
                <n-input v-else-if="spec.type === 'string'"
                         v-model:value="paramsMap[p.name][String(key)]" style="width:220px" />
                <span v-if="spec.description" style="font-size:11px;color:#bbb;line-height:1.3">{{ spec.description }}</span>
              </div>
            </n-form-item>
          </n-form>
          <n-button size="small" type="primary" @click="saveParams(p)">保存</n-button>
        </n-collapse-item>
      </n-collapse>
    </n-card>
  </n-space>
</template>
