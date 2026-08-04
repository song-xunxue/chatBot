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
  NForm, NFormItem, NInputNumber, NInput, NSelect, NPopconfirm, useMessage,
} from 'naive-ui'
import {
  listPlugins, enablePlugin, disablePlugin, reloadPlugin, reloadStar,
  getPluginParams, setPluginParams, previewTTS,
  uploadVoice, listVoices, deleteVoice, getActiveVoice, setActiveVoice,
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
  await loadVoices()
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

// 自定义音色(声音克隆)管理:上传音/视频→硅基流动 zero-shot 克隆→uri→设为当前→全 TTS 复用
const cloneVoices = ref<any[]>([])
const activeVoiceUri = ref<string | null>(null)
const uploadFile = ref<File | null>(null)
const uploadName = ref('')
const uploadText = ref('')
const uploadStart = ref(0)
const uploadDur = ref(0)
const uploading = ref(false)

async function loadVoices() {
  try {
    const [lv, av] = await Promise.all([listVoices(), getActiveVoice(oid.value)])
    cloneVoices.value = lv.result || []
    activeVoiceUri.value = av.uri
  } catch (e: any) { /* 静默(oid 未就绪等) */ }
}
function onFileChange(e: Event) {
  const t = e.target as HTMLInputElement
  uploadFile.value = t.files && t.files[0] ? t.files[0] : null
  if (uploadFile.value && !uploadName.value) {
    uploadName.value = uploadFile.value.name.replace(/\.[^.]+$/, '')
  }
}
async function onUpload() {
  if (!uploadFile.value) { message.warning('请选择音频或视频文件'); return }
  if (!uploadName.value.trim()) { message.warning('请填写音色名'); return }
  try {
    uploading.value = true
    const r = await uploadVoice(uploadFile.value, uploadName.value.trim(),
      uploadText.value, uploadStart.value, uploadDur.value)
    message.success(`克隆成功:${r.customName}`)
    uploadFile.value = null; uploadName.value = ''; uploadText.value = ''
    uploadStart.value = 0; uploadDur.value = 0
    const inp = document.getElementById('clone-file') as HTMLInputElement | null
    if (inp) inp.value = ''
    await loadVoices()
  } catch (e: any) {
    message.error('克隆失败: ' + (e?.response?.data?.detail || e?.message || e))
  } finally {
    uploading.value = false
  }
}
async function previewClone(uri: string) {
  try {
    const blob = await previewTTS(uri)
    stopPreview()
    audioEl = new Audio(URL.createObjectURL(blob))
    await audioEl.play()
  } catch (e: any) {
    message.error('试听失败: ' + (e?.response?.status || e?.message || e))
  }
}
async function deleteClone(uri: string) {
  try {
    await deleteVoice(uri)
    if (activeVoiceUri.value === uri) {
      await setActiveVoice(oid.value, null); activeVoiceUri.value = null
    }
    message.success('已删除')
    await loadVoices()
  } catch (e: any) { message.error('删除失败: ' + e) }
}
async function useClone(uri: string) {
  try {
    await setActiveVoice(oid.value, uri)
    activeVoiceUri.value = uri
    message.success('已设为当前音色(全 TTS 复用,含代答)')
  } catch (e: any) { message.error('设置失败: ' + e) }
}
async function clearActive() {
  try {
    await setActiveVoice(oid.value, null)
    activeVoiceUri.value = null
    message.success('已恢复预设音色')
  } catch (e: any) { message.error('清除失败: ' + e) }
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

    <!-- 自定义音色(声音克隆,M-tts):上传音/视频→克隆 uri→设为当前→全 TTS 复用 -->
    <n-card title="自定义音色(声音克隆)" size="small">
      <span style="color:#999;font-size:12px">上传目标音色的音频/视频(8-10s 干净片段最佳,单一说话人无噪),硅基流动秒级克隆(zero-shot,免训练)。「设为当前」后全 TTS(自动回复+代答)复用此音色。需账号已实名。</span>
      <n-space align="center" :wrap="false" style="margin-top:10px">
        <input id="clone-file" type="file" accept="audio/*,video/*" @change="onFileChange" />
        <n-input v-model:value="uploadName" placeholder="音色名" style="width:130px" />
        <n-input v-model:value="uploadText" placeholder="参考音频对应文字(助对齐,可选)" style="width:220px" />
        <n-input-number v-model:value="uploadStart" :min="0" :step="1" placeholder="起(s)" style="width:88px" />
        <n-input-number v-model:value="uploadDur" :min="0" :step="1" placeholder="取(s)" style="width:88px" />
        <n-button type="primary" size="small" :loading="uploading" @click="onUpload">克隆</n-button>
      </n-space>
      <div style="margin-top:10px;font-size:13px;display:flex;align-items:center;gap:6px">
        当前音色:
        <n-tag v-if="activeVoiceUri" size="small" type="success">克隆音色</n-tag>
        <n-tag v-else size="small">预设(上方插件参数所选)</n-tag>
        <n-button v-if="activeVoiceUri" size="tiny" quaternary @click="clearActive">恢复预设</n-button>
      </div>
      <div v-for="v in cloneVoices" :key="v.uri"
           style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid #f5f5f5">
        <span style="font-weight:600;min-width:100px">{{ v.customName }}</span>
        <span style="color:#bbb;font-size:11px;flex:1;font-family:monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ v.uri }}</span>
        <n-button size="tiny" @click="previewClone(v.uri)">试听</n-button>
        <n-button size="tiny" :type="activeVoiceUri === v.uri ? 'success' : 'default'" @click="useClone(v.uri)">
          {{ activeVoiceUri === v.uri ? '当前' : '设为当前' }}
        </n-button>
        <n-popconfirm @positive-click="deleteClone(v.uri)">
          <template #trigger><n-button size="tiny" quaternary type="error">删</n-button></template>
          删除此克隆音色?
        </n-popconfirm>
      </div>
    </n-card>
  </n-space>
</template>
