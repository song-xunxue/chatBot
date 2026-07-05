<script setup lang="ts">
/**
 * 系统配置页(M7):LLM provider 配置状态(只读)+ 重载配置 + QQ 机器人凭证管理 + 清空所有数据(2026-07-05)。
 * QQ 凭证持久化 Redis(后端),保存后立即生效(下次 webhook 用新凭证换 token/验签,无需重启)。
 * 清空所有数据:删运行时数据(对话/记忆/训练样本/评分/mood值/代答),保留人设+配置,需输入"清空"确认。
 * 作者: 李文煜
 */
import { ref, onMounted } from 'vue'
import { NCard, NSpace, NButton, NTag, NSpin, NEmpty, NInput, NModal, useMessage } from 'naive-ui'
import { getSystemConfig, reloadSystem, getQQCredentials, setQQCredentials, resetAllData } from '@/api'

const message = useMessage()
const config = ref<any>(null)
const loading = ref(false)
const reloading = ref(false)
const qq = ref({ app_id: '', app_secret: '', has_secret: false })
const savingQQ = ref(false)
const showSecret = ref(false)

// 清空所有数据(危险操作)
const resetShow = ref(false)
const resetConfirm = ref('')
const resetting = ref(false)

async function load() {
  loading.value = true
  try {
    config.value = await getSystemConfig()
    const c = await getQQCredentials()
    qq.value = { app_id: c.app_id || '', app_secret: '', has_secret: !!c.has_secret }
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

async function saveQQ() {
  if (!qq.value.app_id || !qq.value.app_secret) {
    message.warning('AppID 和 AppSecret 都要填'); return
  }
  savingQQ.value = true
  try {
    await setQQCredentials({ app_id: qq.value.app_id, app_secret: qq.value.app_secret })
    message.success('QQ 凭证已保存并生效(下次用新 secret 换 token)')
    qq.value.app_secret = ''; qq.value.has_secret = true   // 清输入,标记已配置
  } catch (e: any) { message.error('' + e) }
  finally { savingQQ.value = false }
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

onMounted(load)
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
    <n-card title="QQ 机器人凭证">
      <n-space vertical size="large">
        <span style="color:#999;font-size:12px">
          凭证保存后立即生效(下次 webhook 用新凭证换 token/验签,无需重启)。AppSecret 不回显,仅显示"已配置"。
        </span>
        <n-input v-model:value="qq.app_id" placeholder="AppID(机器人 ID)" />
        <n-input v-model:value="qq.app_secret" :type="showSecret ? 'text' : 'password'"
                 :placeholder="qq.has_secret ? '(已配置,留空不改)输入新值覆盖' : 'AppSecret'" />
        <n-space align="center">
          <n-button type="primary" :loading="savingQQ" @click="saveQQ">保存</n-button>
          <n-button size="small" quaternary @click="showSecret = !showSecret">{{ showSecret ? '隐藏' : '显示' }} Secret</n-button>
          <n-tag v-if="qq.has_secret" type="success" size="small">已配置 Secret</n-tag>
        </n-space>
      </n-space>
    </n-card>
    <n-card title="危险操作">
      <n-space vertical size="large">
        <span style="color:#999;font-size:12px">
          清空所有运行时数据(对话历史/训练样本/记忆/评分/mood值/代答队列),保留人设 + QQ凭证 + 心情档位 + 插件开关。<b style="color:#d03050">不可恢复</b>。
        </span>
        <n-button type="error" @click="openReset">清空所有数据</n-button>
      </n-space>
    </n-card>

    <!-- 清空确认弹窗(输入"清空"二次确认) -->
    <n-modal v-model:show="resetShow" preset="card" title="清空所有数据(危险操作)" style="width:480px;max-width:92vw">
      <n-space vertical :size="12">
        <div style="color:#d03050;font-size:13px">
          将清空:对话历史 / 训练样本 / 四级记忆 / 评分样本 / mood值+历史 / 代答队列。保留:人设 / QQ凭证 / 心情档位 / 插件开关 / token缓存。<b>不可恢复</b>。
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
