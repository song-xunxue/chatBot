/**
 * 全局共享 object_id(composable)——跨页复用同一聊天对象 ID + 头部回车触发当前页刷新
 * 各页(History/Memory/Mood/Plugin/Roleplay)原本各自维护独立 oid 输入框,用户每页都要重填;
 * 改为模块级单例 ref + localStorage 持久化,头部一处输入全局生效。
 * reloadTick:头部输入 @keyup.enter 自增 → 各页 watch(reloadTick) 触发本页 load(仅当前挂载页响应)。
 * 作者: 李文煜
 */
import { ref, watch } from 'vue'

const STORAGE_KEY = 'mychat_object_id'
// 模块级单例(所有 useObject() 调用共享同一 ref)
const oid = ref(localStorage.getItem(STORAGE_KEY) || 'default')
// 刷新信号:自增触发各页 reload(避免每键 stroke 都 load;只在头部回车时触发)
const reloadTick = ref(0)

// 持久化 + 跨标签页同步(storage 事件)
watch(oid, (v) => localStorage.setItem(STORAGE_KEY, v))
window.addEventListener('storage', (e) => {
  if (e.key === STORAGE_KEY && e.newValue != null) oid.value = e.newValue
})

function triggerReload() {
  reloadTick.value++
}

export function useObject() {
  return { oid, reloadTick, triggerReload }
}
