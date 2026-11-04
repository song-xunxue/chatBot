/**
 * chart.js 主题化配置(2026-11-03 双主题:浅色 NextUI pink 系/深色 NapCat 玫粉系)
 * canvas 不解析 CSS 变量,图表须用字面色值——经 Proxy 按当前主题(html.dark 类)动态取值:
 * 组件 setup 构造 options 时取到当时主题的色板,切换主题后重新进入页面即刷新。
 * 色板与 styles/theme.css 手动保持同步。
 * 日期: 2026-09-16

2026-11-03
变更说明:
  1. 双主题:LIGHT(浅色粉调网格/深灰刻度)/DARK(原暗色白调)双色板;
     CHART/darkChartScales 改 Proxy 按当前主题动态返回(导出名与消费方不变,零改动迁移)
 */
function isDarkNow(): boolean {
  return typeof document !== 'undefined' && document.documentElement.classList.contains('dark')
}

const LIGHT = {
  accent: '#ec4899',
  accentFill: 'rgba(236, 72, 153, 0.16)',
  danger: '#e11d48',
  neutral: 'rgba(0, 0, 0, 0.3)',
  textDim: 'rgba(33, 38, 54, 0.55)',
  gridLine: 'rgba(0, 0, 0, 0.07)',
  scales: {
    x: { ticks: { color: 'rgba(33, 38, 54, 0.55)', font: { size: 10 } }, grid: { color: 'rgba(0, 0, 0, 0.07)' } },
    y: { ticks: { color: 'rgba(33, 38, 54, 0.55)', font: { size: 10 } }, grid: { color: 'rgba(0, 0, 0, 0.07)' } },
  },
}

const DARK = {
  accent: '#f31260',
  accentFill: 'rgba(243, 18, 96, 0.2)',
  danger: '#db3694',
  neutral: 'rgba(255, 255, 255, 0.25)',
  textDim: 'rgba(255, 255, 255, 0.45)',
  gridLine: 'rgba(255, 255, 255, 0.08)',
  scales: {
    x: { ticks: { color: 'rgba(255, 255, 255, 0.45)', font: { size: 10 } }, grid: { color: 'rgba(255, 255, 255, 0.08)' } },
    y: { ticks: { color: 'rgba(255, 255, 255, 0.45)', font: { size: 10 } }, grid: { color: 'rgba(255, 255, 255, 0.08)' } },
  },
}

/* eslint-disable @typescript-eslint/no-explicit-any */
export const CHART: any = new Proxy({} as any, {
  get: (_t, key) => (isDarkNow() ? DARK : LIGHT)[key as keyof typeof LIGHT],
})

export const darkChartScales: any = new Proxy({} as any, {
  get: (_t, key) => (isDarkNow() ? DARK : LIGHT).scales[key as 'x' | 'y'],
})
