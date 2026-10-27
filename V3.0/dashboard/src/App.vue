<script setup lang="ts">
/**
 * 根组件：Naive UI 全局 Provider（中文 locale + message/dialog 注入）
 * 2026-09-16 暗色重设计:darkTheme + NapCat 系主题覆盖(色板见 styles/theme.css)。
 */
import { NConfigProvider, NMessageProvider, NDialogProvider, NLoadingBarProvider,
         zhCN, dateZhCN, darkTheme } from 'naive-ui'
import type { GlobalThemeOverrides } from 'naive-ui'

// NapCat 风格覆盖:荧光绿主色 + 暗灰底/卡片/边框/输入,组件圆角统一 8px
const themeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#3fc68a',
    primaryColorHover: '#5bd6a0',
    primaryColorPressed: '#36ad7b',
    primaryColorSuppl: '#3fc68a',
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
    successColor: '#3fc68a',
    warningColor: '#f0a935',
    errorColor: '#e5484d',
    infoColor: '#5b9cf5',
  },
}
</script>

<template>
  <n-config-provider :locale="zhCN" :date-locale="dateZhCN" :theme="darkTheme" :theme-overrides="themeOverrides">
    <n-loading-bar-provider>
      <n-message-provider>
        <n-dialog-provider>
          <router-view />
        </n-dialog-provider>
      </n-message-provider>
    </n-loading-bar-provider>
  </n-config-provider>
</template>
