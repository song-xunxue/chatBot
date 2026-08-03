<script setup lang="ts">
/**
 * 插件管理(V2.0 M7 + M-tts 2026-08-04):原生 + .star 列表 + 启用/禁用 + 热重载 + 参数配置。
 * 参数配置为 M-tts 新增的泛化能力:凡 plugin.yaml 声明 config_schema 的插件自动渲染表单
 * (音色下拉/语速/gain/开关等),单人设 object_id 取 useObject 全局 oid。顺带让 continuous_send 等也可配。
 * 作者: 李文煜
 */
import { ref, computed, onMounted } from 'vue'
import {
  NCard, NSpace, NButton, NSwitch, NTag, NEmpty, NCollapse, NCollapseItem,
  NForm, NFormItem, NInputNumber, NInput, NSelect, useMessage,
} from 'naive-ui'
import {
  listPlugins, enablePlugin, disablePlugin, reloadPlugin, reloadStar,
  getPluginParams, setPluginParams, previewTTS,
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

onMounted(load)
</script>

<template>
  <n-space vertical size="large">
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
            </n-form-item>
          </n-form>
          <n-button size="small" type="primary" @click="saveParams(p)">保存</n-button>
        </n-collapse-item>
      </n-collapse>
    </n-card>
  </n-space>
</template>
