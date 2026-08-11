/**
 * REST API 封装(V2.0 M7):人设 / 聊天历史 / 评分 / 心情 / 记忆 / 插件 / 系统。
 * 对接 V2.0 服务端 rest_persona / rest_chat / rest_score / rest_mood / rest_memory / rest_plugin / rest_system。
 * 鉴权由 client.ts 拦截器自动注入 X-Access-Token(Header)。
 * 作者: 李文煜
 */
import { api } from './client'

// —— 人设 persona ——
export const listPersonas = () => api.get('/api/v1/persona').then((r) => r.data)
export const getPersona = (id: string) => api.get(`/api/v1/persona/${id}`).then((r) => r.data)
export const updatePersona = (id: string, body: any) => api.put(`/api/v1/persona/${id}`, body).then((r) => r.data)
export const exportPersona = (id: string) => api.get(`/api/v1/persona/${id}/export`).then((r) => r.data)
export const bindPersonaModel = (id: string, body: any) =>
  api.put(`/api/v1/persona/${id}/model`, body).then((r) => r.data)
export const snapshotPersona = (id: string) => api.post(`/api/v1/persona/${id}/snapshot`).then((r) => r.data)
export const rollbackPersona = (id: string, version_no: number) =>
  api.post(`/api/v1/persona/${id}/rollback`, { version_no }).then((r) => r.data)

// —— 聊天历史 chat(block 三层)——
export const listSessions = (limit = 50) =>
  api.get('/api/v1/chat/sessions', { params: { limit } }).then((r) => r.data)
export const listRecentBlocks = (limit = 80) =>
  api.get('/api/v1/chat/recent_blocks', { params: { limit } }).then((r) => r.data)
export const listBlocks = (oid: string, limit = 100) =>
  api.get(`/api/v1/chat/${oid}/blocks`, { params: { limit } }).then((r) => r.data)
export const listMessages = (oid: string, params: { block_id?: string; limit?: number } = {}) =>
  api.get(`/api/v1/chat/${oid}/messages`, { params }).then((r) => r.data)
export const getMessage = (mid: string) => api.get(`/api/v1/chat/messages/${mid}`).then((r) => r.data)
export const updateMessage = (mid: string, body: any) =>
  api.put(`/api/v1/chat/messages/${mid}`, body).then((r) => r.data)
export const deleteMessage = (mid: string, reason = 'out_of_character') =>
  api.delete(`/api/v1/chat/messages/${mid}`, { data: { reason } }).then((r) => r.data)
export const closeBlock = (bid: string, reason = 'manual') =>
  api.post(`/api/v1/chat/blocks/${bid}/close`, { reason }).then((r) => r.data)
export const deleteBlock = (bid: string) =>
  api.delete(`/api/v1/chat/blocks/${bid}`).then((r) => r.data)
export const clearHistory = (oid: string) =>
  api.delete(`/api/v1/chat/${oid}/history`).then((r) => r.data)

// —— 评分 score(M3 + M7 samples)——
export const getScore = (mid: string) => api.get(`/api/v1/chat/messages/${mid}/score`).then((r) => r.data)
export const setScore = (mid: string, score_base: number, score_note?: string) =>
  api.patch(`/api/v1/chat/messages/${mid}/score`, { score_base, score_note }).then((r) => r.data)
export const getHealth = (oid: string, window = 0) =>
  api.get(`/api/v1/chat/${oid}/health`, { params: { window } }).then((r) => r.data)
export const getSamples = (oid: string, kind = 'negative') =>
  api.get(`/api/v1/score/samples/${oid}`, { params: { kind } }).then((r) => r.data)
export const reverseInferDryRun = (oid: string, body: any = {}) =>
  api.post(`/api/v1/score/reverse_infer/${oid}/dry_run`, body).then((r) => r.data)
export const reverseInferApply = (oid: string, token: string) =>
  api.post(`/api/v1/score/reverse_infer/${oid}/apply`, { confirm_token: token }).then((r) => r.data)

// —— 心情 mood ——
export const getMood = (oid: string) => api.get(`/api/v1/mood/${oid}`).then((r) => r.data)
export const setMood = (oid: string, mood: number) => api.put(`/api/v1/mood/${oid}`, { mood }).then((r) => r.data)
export const getMoodHistory = (oid: string, limit = 100) =>
  api.get(`/api/v1/mood/${oid}/history`, { params: { limit } }).then((r) => r.data)
export const listMoodKinds = () => api.get('/api/v1/mood/kinds').then((r) => r.data)
export const upsertMoodKind = (body: any) => api.post('/api/v1/mood/kinds', body).then((r) => r.data)
export const putMoodKind = (key: string, body: any) => api.put(`/api/v1/mood/kinds/${key}`, body).then((r) => r.data)
export const deleteMoodKind = (key: string) => api.delete(`/api/v1/mood/kinds/${key}`).then((r) => r.data)
export const getMoodParams = () => api.get('/api/v1/mood/params').then((r) => r.data)
export const setMoodParams = (body: any) => api.put('/api/v1/mood/params', body).then((r) => r.data)
export const moodCalc = (oid: string, body: any) => api.post(`/api/v1/mood/${oid}/calc`, body).then((r) => r.data)

// —— 记忆 memory ——
export const getMemory = (oid: string, layer = 'all', category = '', limit = 100) =>
  api.get(`/api/v1/memory/${oid}`, { params: { layer, category, limit } }).then((r) => r.data)
export const getMemoryStats = (oid: string) => api.get(`/api/v1/memory/${oid}/stats`).then((r) => r.data)
export const forgetOneMemory = (oid: string, mid: string) =>
  api.delete(`/api/v1/memory/${oid}/${mid}`).then((r) => r.data)
export const restoreMemory = (oid: string, mid: string) =>
  api.post(`/api/v1/memory/${oid}/${mid}/restore`).then((r) => r.data)
export const lockMemory = (oid: string, mid: string, locked = true) =>
  api.post(`/api/v1/memory/${oid}/${mid}/lock`, { locked }).then((r) => r.data)
export const updateMemory = (oid: string, mid: string, body: { content?: string; category?: string; importance?: number }) =>
  api.patch(`/api/v1/memory/${oid}/${mid}`, body).then((r) => r.data)
export const batchForgetMemory = (oid: string, body: any = {}) =>
  api.post(`/api/v1/memory/${oid}/forget`, body).then((r) => r.data)

// —— 插件 plugin(原生 + .star)——
export const listPlugins = () => api.get('/api/v1/plugin').then((r) => r.data)
export const getPlugin = (name: string) => api.get(`/api/v1/plugin/${name}`).then((r) => r.data)
export const enablePlugin = (name: string) => api.post(`/api/v1/plugin/${name}/enable`).then((r) => r.data)
export const disablePlugin = (name: string) => api.post(`/api/v1/plugin/${name}/disable`).then((r) => r.data)
export const reloadPlugin = (name: string) => api.post(`/api/v1/plugin/${name}/reload`).then((r) => r.data)
export const reloadStar = (name: string) => api.post(`/api/v1/plugin/star/${name}/reload`).then((r) => r.data)
// 插件参数(M-tts 2026-08-04:面板 config_schema 表单读写;单人设 object_id=全局 oid)
export const getPluginParams = (name: string, oid: string) =>
  api.get(`/api/v1/plugin/${name}/params`, { params: { object_id: oid } }).then((r) => r.data)
export const setPluginParams = (name: string, oid: string, params: Record<string, any>) =>
  api.put(`/api/v1/plugin/${name}/params`, params, { params: { object_id: oid } }).then((r) => r.data)

// —— TTS 音色预览(M-tts 2026-08-04:面板试听,返 mp3 blob → Audio.play)——
export const previewTTS = (voice: string, text?: string) =>
  api.post('/api/v1/tts/preview', { voice, text }, { responseType: 'blob' }).then((r) => r.data)

// —— TTS 自定义音色(声音克隆,M-tts:上传音/视频→硅基流动 zero-shot 克隆→uri)——
export const uploadVoice = (file: File, customName: string, text: string, startSec = 0, durSec = 0) => {
  const form = new FormData()
  form.append('file', file)
  form.append('customName', customName)
  form.append('text', text)
  form.append('start_sec', String(startSec))
  form.append('dur_sec', String(durSec))
  return api.post('/api/v1/tts/voice/upload', form).then((r) => r.data)
}
export const listVoices = () => api.get('/api/v1/tts/voice/list').then((r) => r.data)
export const deleteVoice = (uri: string) => api.post('/api/v1/tts/voice/delete', { uri }).then((r) => r.data)
export const getActiveVoice = (oid: string) =>
  api.get('/api/v1/tts/voice/active', { params: { object_id: oid } }).then((r) => r.data)
export const setActiveVoice = (oid: string, uri: string | null) =>
  api.put('/api/v1/tts/voice/active', { uri }).then((r) => r.data)

// —— GPT-SoVITS 就绪状态(M-tts-2,2026-08-10:心跳缓存优先;展开懒检测+轮询)——
// force=true 跳心跳强探(手动「重新检测」);probe=false 只读心跳不探测(折叠态/轮询,零 frp 开销)
export const getGPTSoVITSStatus = (force = false, probe = true) =>
  api.get('/api/v1/tts/gptsovits/status', { params: { force, probe } }).then((r) => r.data)

// —— 系统 system ——
export const getSystemConfig = () => api.get('/api/v1/system/config').then((r) => r.data)
export const reloadSystem = () => api.post('/api/v1/system/reload').then((r) => r.data)
export const getQQCredentials = () => api.get('/api/v1/system/qq-credentials').then((r) => r.data)
export const setQQCredentials = (body: { app_id: string; app_secret: string }) =>
  api.put('/api/v1/system/qq-credentials', body).then((r) => r.data)
export const resetAllData = () =>
  api.post('/api/v1/system/reset', { confirm: '清空' }).then((r) => r.data)

// —— 代答 takeover(M8)——
export const toggleTakeover = (oid: string, enabled: boolean) =>
  api.post(`/api/v1/takeover/${oid}/toggle`, { enabled }).then((r) => r.data)
export const getTakeoverStatus = (oid: string) =>
  api.get(`/api/v1/takeover/${oid}/status`).then((r) => r.data)
export const listTakeoverQueue = (oid: string) =>
  api.get(`/api/v1/takeover/${oid}/queue`).then((r) => r.data)
export const answerTakeover = (oid: string, body: { pid?: string; answer: string }) =>
  api.post(`/api/v1/takeover/${oid}/answer`, body).then((r) => r.data)
export const answerTakeoverBatch = (oid: string, items: { pid?: string; answer: string }[]) =>
  api.post(`/api/v1/takeover/${oid}/answer/batch`, { items }).then((r) => r.data)
export const skipTakeover = (oid: string, pid?: string) =>
  api.post(`/api/v1/takeover/${oid}/skip`, { pid }).then((r) => r.data)
export const sendTakeover = (oid: string, content: string) =>
  api.post(`/api/v1/takeover/${oid}/send`, { content }).then((r) => r.data)
// 代答 TTS 开关(M-tts 2026-08-04:两开关 enable/send_text_also;voice 参数复用 tts_reply 插件 config)
export const getTakeoverTTSConfig = (oid: string) =>
  api.get(`/api/v1/takeover/${oid}/tts_config`).then((r) => r.data)
export const setTakeoverTTSConfig = (oid: string, enable: boolean, send_text_also: boolean) =>
  api.put(`/api/v1/takeover/${oid}/tts_config`, { enable, send_text_also }).then((r) => r.data)

// —— roleplay 训练样本(M8 + 2026-07-05 多会话+评分)——
export const listRoleplaySessions = (oid: string) =>
  api.get(`/api/v1/roleplay/${oid}/sessions`).then((r) => r.data)
export const newRoleplaySession = (oid: string) =>
  api.post(`/api/v1/roleplay/${oid}/sessions`).then((r) => r.data)
export const deleteRoleplaySession = (blockId: string) =>
  api.delete(`/api/v1/roleplay/blocks/${blockId}`).then((r) => r.data)
export const addRoleplay = (oid: string, body: { role: string; content: string; score_base?: number }) =>
  api.post(`/api/v1/roleplay/${oid}/messages`, body).then((r) => r.data)
export const addRoleplayBatch = (oid: string, items: { role: string; content: string; score_base?: number }[]) =>
  api.post(`/api/v1/roleplay/${oid}/messages/batch`, { items }).then((r) => r.data)
export const listRoleplay = (oid: string, params: { block_id?: string; limit?: number } = {}) =>
  api.get(`/api/v1/roleplay/${oid}/messages`, { params }).then((r) => r.data)
export const updateRoleplay = (oid: string, mid: string, content: string) =>
  api.put(`/api/v1/roleplay/${oid}/messages/${mid}`, { content }).then((r) => r.data)
export const setRoleplayScore = (oid: string, mid: string, score_base: number) =>
  api.patch(`/api/v1/roleplay/${oid}/messages/${mid}/score`, { score_base }).then((r) => r.data)
export const deleteRoleplay = (oid: string, mid: string) =>
  api.delete(`/api/v1/roleplay/${oid}/messages/${mid}`).then((r) => r.data)
export const extractRoleplay = (oid: string, blockId?: string) =>
  api.post(`/api/v1/roleplay/${oid}/extract`, blockId ? { block_id: blockId } : {}).then((r) => r.data)
