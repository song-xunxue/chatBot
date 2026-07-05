<script setup lang="ts">
/**
 * 系统配置页(M7):LLM provider 配置状态(只读)+ 重载配置 + QQ 机器人凭证管理(2026-07-05)。
 * QQ 凭证持久化 Redis(后端),保存后立即生效(下次 webhook 用新凭证换 token/验签,无需重启)。
 * 作者: 李文煜
 */
import { ref, onMounted } from 'vue'
import { NCard, NSpace, NButton, NTag, NSpin, NEmpty, NInput, useMessage } from 'naive-ui'
import { getSystemConfig, reloadSystem, getQQCredentials, setQQCredentials } from '@/api'

const message = useMessage()
const config = ref<any>(null)
const loading = ref(false)
const reloading = ref(false)
const qq = ref({ app_id: '', app_secret: '', has_secret: false })
const savingQQ = ref(false)
const showSecret = ref(false)

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
  </n-space>
</template>
