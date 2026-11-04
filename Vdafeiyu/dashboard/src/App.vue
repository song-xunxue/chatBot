<script setup lang="ts">
/**
 * 根组件：Naive UI 全局 Provider（中文 locale + message/dialog 注入）
 * 2026-09-16 暗色重设计:darkTheme + NapCat 系主题覆盖(色板见 styles/theme.css)。
 * 2026-11-03 双主题:浅色(默认,NextNapCatWebUI 风格,NextUI pink #ec4899)/深色(#f31260),
 * localStorage「panel-theme」记忆;html.dark 类联动 CSS 变量(styles/theme.css);
 * provide('isDark'/'toggleTheme') 供侧栏/顶栏切换按钮消费。
 */
import { computed, provide, ref, watch } from 'vue'
import { NConfigProvider, NMessageProvider, NDialogProvider, NLoadingBarProvider,
         zhCN, dateZhCN, darkTheme } from 'naive-ui'
import type { GlobalThemeOverrides } from 'naive-ui'

const theme = ref<'light' | 'dark'>(
  (localStorage.getItem('panel-theme') === 'dark') ? 'dark' : 'light')
const isDark = computed(() => theme.value === 'dark')

watch(isDark, (v) => {
  document.documentElement.classList.toggle('dark', v)
  localStorage.setItem('panel-theme', v ? 'dark' : 'light')
}, { immediate: true })

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
}
provide('isDark', isDark)
provide('toggleTheme', toggleTheme)

// 浅色覆盖(NextNapCatWebUI 浅色:白卡片+粉 primary+粉调边框;文字交给 naive 浅色默认)
const LIGHT_OVERRIDES: GlobalThemeOverrides = {
  common: {
    primaryColor: '#ec4899',
    primaryColorHover: '#f472b6',
    primaryColorPressed: '#db2777',
    primaryColorSuppl: '#ec4899',
    bodyColor: '#fdf6f9',
    cardColor: '#ffffff',
    modalColor: '#ffffff',
    popoverColor: '#ffffff',
    tableColor: '#ffffff',
    inputColor: 'rgba(0, 0, 0, 0.045)',
    actionColor: '#faf3f7',
    hoverColor: 'rgba(236, 72, 153, 0.06)',
    borderColor: 'rgba(236, 72, 153, 0.22)',
    dividerColor: 'rgba(0, 0, 0, 0.06)',
    borderRadius: '8px',
    borderRadiusSmall: '6px',
    successColor: '#0ea5e9',
    warningColor: '#d97706',
    errorColor: '#e11d48',
    infoColor: '#0ea5e9',
  },
  Menu: {
    itemColorActive: 'rgba(236, 72, 153, 0.14)',
    itemColorActiveHover: 'rgba(236, 72, 153, 0.18)',
    itemColorActiveCollapsed: 'rgba(236, 72, 153, 0.14)',
    itemTextColorActive: '#db2777',
    itemTextColorActiveHover: '#db2777',
    itemBorderRadius: '10px',
  },
}

// 深色覆盖(NapCat dark 玫粉系,2026-09-16 原版)
const DARK_OVERRIDES: GlobalThemeOverrides = {
  common: {
    primaryColor: '#f31260',
    primaryColorHover: '#f54180',
    primaryColorPressed: '#c20e4d',
    primaryColorSuppl: '#f31260',
    bodyColor: '#111114',
    cardColor: '#1a1a1f',
    modalColor: '#1e1e24',
    popoverColor: '#222228',
    tableColor: '#1a1a1f',
    inputColor: 'rgba(255, 255, 255, 0.06)',
    actionColor: '#1e1e24',
    hoverColor: 'rgba(255, 255, 255, 0.06)',
    borderColor: 'rgba(255, 255, 255, 0.12)',
    dividerColor: 'rgba(255, 255, 255, 0.08)',
    borderRadius: '8px',
    borderRadiusSmall: '6px',
    successColor: '#88c0d0',
    warningColor: '#f0a935',
    errorColor: '#db3694',
    infoColor: '#88c0d0',
  },
  Menu: {
    itemColorActive: 'rgba(243, 18, 96, 0.16)',
    itemColorActiveHover: 'rgba(243, 18, 96, 0.2)',
    itemColorActiveCollapsed: 'rgba(243, 18, 96, 0.16)',
    itemTextColorActive: '#f54180',
    itemTextColorActiveHover: '#f54180',
    itemBorderRadius: '10px',
  },
}

const themeOverrides = computed(() => (isDark.value ? DARK_OVERRIDES : LIGHT_OVERRIDES))
</script>

<template>
  <n-config-provider :locale="zhCN" :date-locale="dateZhCN" :theme="isDark ? darkTheme : null" :theme-overrides="themeOverrides">
    <n-loading-bar-provider>
      <n-message-provider>
        <n-dialog-provider>
          <router-view />
        </n-dialog-provider>
      </n-message-provider>
    </n-loading-bar-provider>
  </n-config-provider>
</template>
