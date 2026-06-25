/**
 * REST API 封装：人设 / 插件 / 记忆 / 桌宠 / 多模态
 * 对接服务端 rest_persona / rest_plugin / rest_memory / rest_pet / rest_multimodal
 * 作者: 李文煜
 */
import { api } from './client'

// —— 人设 ——
export const listPersonas = () => api.get('/api/v1/persona').then((r) => r.data)
export const getPersona = (id: string) => api.get(`/api/v1/persona/${id}`).then((r) => r.data)
export const createPersona = (body: any) => api.post('/api/v1/persona', body).then((r) => r.data)
export const updatePersona = (id: string, body: any) => api.put(`/api/v1/persona/${id}`, body).then((r) => r.data)
export const deletePersona = (id: string) => api.delete(`/api/v1/persona/${id}`).then((r) => r.data)
export const importPersona = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post('/api/v1/persona/import', fd).then((r) => r.data)
}

// —— 插件 ——
export const listPlugins = () => api.get('/api/v1/plugin').then((r) => r.data)
export const getPlugin = (name: string) => api.get(`/api/v1/plugin/${name}`).then((r) => r.data)
export const enablePlugin = (name: string) => api.post(`/api/v1/plugin/${name}/enable`).then((r) => r.data)
export const disablePlugin = (name: string) => api.post(`/api/v1/plugin/${name}/disable`).then((r) => r.data)
export const reloadPlugin = (name: string) => api.post(`/api/v1/plugin/${name}/reload`).then((r) => r.data)
export const getObjectPlugins = (oid: string) => api.get(`/api/v1/plugin/object/${oid}`).then((r) => r.data)
export const setObjectPlugin = (oid: string, name: string, body: any) =>
  api.put(`/api/v1/plugin/object/${oid}/${name}`, body).then((r) => r.data)

// —— 记忆（rest_memory 端点）——
export const getMemory = (oid: string, layer = 'all') =>
  api.get(`/api/v1/memory/${oid}`, { params: { layer } }).then((r) => r.data)
export const getMemoryStats = (oid: string) => api.get(`/api/v1/memory/${oid}/stats`).then((r) => r.data)
export const forgetMemory = (oid: string, body: any) => api.post(`/api/v1/memory/${oid}/forget`, body).then((r) => r.data)
export const forgetOneMemory = (oid: string, mid: string) =>
  api.delete(`/api/v1/memory/${oid}/${mid}`).then((r) => r.data)
export const lockMemory = (oid: string, mid: string) => api.post(`/api/v1/memory/${oid}/lock/${mid}`).then((r) => r.data)
export const restoreMemory = (oid: string, mid: string) =>
  api.post(`/api/v1/memory/${oid}/restore/${mid}`).then((r) => r.data)

// —— 管理面板杂项（rest_admin，M7）——
export const getModels = () => api.get('/api/v1/models').then((r) => r.data)
export const getHistory = (oid: string, limit = 50) =>
  api.get(`/api/v1/history/${oid}`, { params: { limit } }).then((r) => r.data)
// V1.2 历史编辑
export const updateHistoryMsg = (oid: string, mid: string, body: any) =>
  api.put(`/api/v1/history/${oid}/${mid}`, body).then((r) => r.data)
export const deleteHistoryMsg = (oid: string, mid: string) =>
  api.delete(`/api/v1/history/${oid}/${mid}`).then((r) => r.data)
export const getProposals = () => api.get('/api/v1/persona_evolve/proposals').then((r) => r.data)
export const dismissProposal = (oid: string) =>
  api.delete(`/api/v1/persona_evolve/proposals/${oid}`).then((r) => r.data)
// 人设模型绑定（rest_persona）
export const bindPersonaModel = (id: string, body: any) =>
  api.put(`/api/v1/persona/${id}/model`, body).then((r) => r.data)

// —— 代人聊天 A：模拟训练（rest_roleplay，V1.1 M11）——
export const listRoleplayMsgs = (oid: string) =>
  api.get(`/api/v1/roleplay/${oid}/messages`).then((r) => r.data)
export const addRoleplayMsg = (oid: string, body: any) =>
  api.post(`/api/v1/roleplay/${oid}/messages`, body).then((r) => r.data)
// V1.2 代人聊天单条录入
export const addRoleplaySingle = (oid: string, body: any) =>
  api.post(`/api/v1/roleplay/${oid}/messages/single`, body).then((r) => r.data)
export const updateRoleplayMsg = (oid: string, mid: string, body: any) =>
  api.put(`/api/v1/roleplay/${oid}/messages/${mid}`, body).then((r) => r.data)
export const deleteRoleplayMsg = (oid: string, mid: string) =>
  api.delete(`/api/v1/roleplay/${oid}/messages/${mid}`).then((r) => r.data)
// V1.2 反推人设·两步合并（infer 预览 → apply 落库）
export const reverseInfer = (oid: string, mode = 'fill_empty') =>
  api.post(`/api/v1/roleplay/${oid}/reverse-infer`, { mode }).then((r) => r.data)
export const applyReverseInfer = (oid: string, token: string) =>
  api.post(`/api/v1/roleplay/${oid}/reverse-infer/apply`, { confirm_token: token }).then((r) => r.data)

// —— 代人聊天 B：实时接管（rest_takeover，V1.1 M13）——
export const takeoverToggle = (oid: string, enabled: boolean) =>
  api.post('/api/v1/takeover/toggle', { object_id: oid, enabled }).then((r) => r.data)
export const takeoverStatus = (oid: string) =>
  api.get('/api/v1/takeover/status', { params: { object_id: oid } }).then((r) => r.data)
export const takeoverPending = () => api.get('/api/v1/takeover/pending').then((r) => r.data)
export const takeoverAnswer = (oid: string, pid: string, answer: string) =>
  api.post('/api/v1/takeover/answer', { object_id: oid, pending_id: pid, answer }).then((r) => r.data)
