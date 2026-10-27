/**
 * chart.js 暗色配置(2026-09-16 面板暗色重设计)
 * canvas 不解析 CSS 变量,图表须用字面色值——与 styles/theme.css 色板手动保持同步。
 */
export const CHART = {
  accent: '#3fc68a',
  accentFill: 'rgba(63, 198, 138, 0.2)',
  danger: '#e5484d',
  neutral: 'rgba(255, 255, 255, 0.25)',
  textDim: 'rgba(255, 255, 255, 0.45)',
  gridLine: 'rgba(255, 255, 255, 0.08)',
}

/** 通用暗色坐标轴(刻度/网格半透明白,Mood/History 图表共用) */
export const darkChartScales = {
  x: { ticks: { color: CHART.textDim, font: { size: 10 } }, grid: { color: CHART.gridLine } },
  y: { ticks: { color: CHART.textDim, font: { size: 10 } }, grid: { color: CHART.gridLine } },
}
