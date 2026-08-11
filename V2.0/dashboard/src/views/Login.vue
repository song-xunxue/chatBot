<script setup lang="ts">
/**
 * 登录页：输入 access_token（与服务端 ACCESS_TOKEN 一致），存 localStorage 后跳转。
 * 支持 redirect 回跳：移动端 /m/* 被守卫拦截时带 redirect，登录后回到原页面。
 * 作者: 李文煜
 */
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { NCard, NInput, NButton, NSpace, useMessage } from 'naive-ui'

const router = useRouter()
const route = useRoute()
const message = useMessage()
const token = ref(localStorage.getItem('access_token') || '')

function login() {
  if (!token.value.trim()) {
    message.warning('请输入访问令牌')
    return
  }
  localStorage.setItem('access_token', token.value.trim())
  // 登录后回到原目标页（移动端 /m/* 被守卫拦截时带 redirect 回跳）；无 redirect 默认人设页
  const redirect = (route.query.redirect as string) || '/persona'
  router.push(redirect)
}
</script>

<template>
  <div style="height:100vh;display:flex;align-items:center;justify-content:center;background:#faf7f2">
    <n-card title="MyChat 管理面板" style="width:90%;max-width:360px" :bordered="true">
      <n-space vertical>
        <n-input v-model:value="token" placeholder="访问令牌 access_token" type="password" show-password-on="click" @keyup.enter="login" />
        <n-button type="primary" block @click="login">进入</n-button>
        <div style="color:#999;font-size:12px">令牌需与服务端 .env 的 ACCESS_TOKEN 一致</div>
      </n-space>
    </n-card>
  </div>
</template>
