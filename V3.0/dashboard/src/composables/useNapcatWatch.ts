/**
 * NapCat 掉线监控轮询(2026-09-15,MainLayout/MobileLayout 共用)。
 * 60s 轮询 GET /system/napcat-status,offline 时布局层红色横幅常驻——
 * 09-08~15 QQ 登录态失效静默丢 8 天数据的教训,面板必须一打开就能看到"消息正在丢失"。
 * 失败静默(未登录/token 失效不误报横幅)。
 * 作者: 李文煜
 */
import { ref, onMounted, onUnmounted } from 'vue'
import { getNapcatStatus } from '@/api'

export function useNapcatWatch() {
  const offline = ref(false)
  const detail = ref('')
  const sinceTs = ref(0)
  let timer: number | undefined

  async function poll() {
    try {
      const st = await getNapcatStatus()
      offline.value = st?.state === 'offline'
      detail.value = st?.detail || ''
      sinceTs.value = st?.offline_since_ts || 0
    } catch {
      /* 未登录/网络异常:不误报 */
    }
  }

  onMounted(() => {
    poll()
    timer = window.setInterval(poll, 60000)
  })
  onUnmounted(() => {
    if (timer) window.clearInterval(timer)
  })
  return { offline, detail, sinceTs }
}
