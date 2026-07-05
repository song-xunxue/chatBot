/**
 * API 契约测试(V2.0 M7):
 *   mock 底层 axios + 驱动拦截器,验证封装层 .then(r=>r.data) 解包、token 注入、401 跳转,
 *   以及各 V2.0 端点 URL/method/body 契约(persona/chat/score/mood/memory/plugin/system)。
 * 作者: 李文煜
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// hoisted 共享态:vi.mock 工厂提升到顶部,普通 let 不可被工厂引用
const hoisted = vi.hoisted(() => ({
  routerPush: vi.fn(),
  requestFulfilled: null as ((cfg: any) => any) | null,
  responseRejected: null as ((err: any) => any) | null,
  apiMethods: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}))

vi.mock('@/router', () => ({ default: { push: hoisted.routerPush } }))

// mock axios:create 返回伪实例,拦截器 use 存 handler,method 被调时驱动拦截器
vi.mock('axios', () => {
  const fakeInstance = {
    interceptors: {
      request: { use: (ful: (cfg: any) => any) => { hoisted.requestFulfilled = ful } },
      response: { use: (_f: any, rej: (err: any) => any) => { hoisted.responseRejected = rej } },
    },
    ...hoisted.apiMethods,
  }
  return { default: { create: () => fakeInstance } }
})

const routerPush = hoisted.routerPush
const apiMethods = hoisted.apiMethods

import {
  listPersonas, bindPersonaModel,
  listBlocks, listMessages, deleteMessage,
  getSamples, reverseInferDryRun, reverseInferApply,
  getMoodParams, setMoodParams, moodCalc,
  restoreMemory, lockMemory,
  enablePlugin, reloadStar,
  getSystemConfig, reloadSystem,
  toggleTakeover, getTakeoverStatus, listTakeoverQueue, answerTakeover, answerTakeoverBatch, skipTakeover,
  addRoleplay, addRoleplayBatch, listRoleplay, updateRoleplay, deleteRoleplay,
} from '@/api'

function mockResolve(method: 'get' | 'post' | 'put' | 'delete', responseData: any) {
  apiMethods[method].mockImplementation(async (url: string, config?: any) => {
    const base = { url, headers: {}, ...config }
    const cfg = hoisted.requestFulfilled ? hoisted.requestFulfilled(base) : base
    return { data: { ...responseData, __cfg: cfg } }
  })
}

function mockReject(method: 'get' | 'post' | 'put' | 'delete', status: number) {
  apiMethods[method].mockImplementation(async () => {
    const err = { response: { status } }
    if (hoisted.responseRejected) return hoisted.responseRejected(err)
    throw err
  })
}

describe('api endpoint mapping + wrapper unwrapping', () => {
  beforeEach(() => { vi.clearAllMocks(); localStorage.clear() })

  it('wrapper 解包:返回 r.data 而非整个 response', async () => {
    mockResolve('get', { id: 'p1', name: 'alice' })
    const ret: any = await listPersonas()
    expect(ret).not.toHaveProperty('data')
    expect(ret.id).toBe('p1')
  })

  it('persona: list/bindModel(单人设简化:无 create/delete)', async () => {
    mockResolve('get', {}); await listPersonas()
    expect(apiMethods.get).toHaveBeenCalledWith('/api/v1/persona')
    mockResolve('put', {}); await bindPersonaModel('p', { provider: 'glm' })
    expect(apiMethods.put).toHaveBeenCalledWith('/api/v1/persona/p/model', { provider: 'glm' })
  })

  it('chat: blocks/messages/delete(联动 body)', async () => {
    mockResolve('get', {}); await listBlocks('o', 10)
    expect(apiMethods.get).toHaveBeenCalledWith('/api/v1/chat/o/blocks', { params: { limit: 10 } })
    await listMessages('o', { block_id: 'b1' })
    expect(apiMethods.get).toHaveBeenCalledWith('/api/v1/chat/o/messages', { params: { block_id: 'b1' } })
    mockResolve('delete', {}); await deleteMessage('m1', 'bad')
    expect(apiMethods.delete).toHaveBeenCalledWith('/api/v1/chat/messages/m1', { data: { reason: 'bad' } })
  })

  it('score: samples/reverseInfer 两步', async () => {
    mockResolve('get', {}); await getSamples('o', 'positive')
    expect(apiMethods.get).toHaveBeenCalledWith('/api/v1/score/samples/o', { params: { kind: 'positive' } })
    mockResolve('post', {}); await reverseInferDryRun('o', { mode: 'overwrite' })
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/score/reverse_infer/o/dry_run', { mode: 'overwrite' })
    await reverseInferApply('o', 'tok9')
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/score/reverse_infer/o/apply', { confirm_token: 'tok9' })
  })

  it('mood: params/calc', async () => {
    mockResolve('get', {}); await getMoodParams()
    expect(apiMethods.get).toHaveBeenCalledWith('/api/v1/mood/params')
    mockResolve('put', {}); await setMoodParams({ mood_step: 0.2 })
    expect(apiMethods.put).toHaveBeenCalledWith('/api/v1/mood/params', { mood_step: 0.2 })
    mockResolve('post', {}); await moodCalc('o', { score_base: 80, mood: 0.8 })
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/mood/o/calc', { score_base: 80, mood: 0.8 })
  })

  it('memory: restore/lock(V2.0 新路径)', async () => {
    mockResolve('post', {}); await restoreMemory('o', 'm1')
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/memory/o/m1/restore')
    await lockMemory('o', 'm1', true)
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/memory/o/m1/lock', { locked: true })
  })

  it('plugin: enable/reloadStar/objectConfig', async () => {
    mockResolve('post', {}); await enablePlugin('tts')
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/plugin/tts/enable')
    await reloadStar('s1')
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/plugin/star/s1/reload')
  })

  it('system: config/reload', async () => {
    mockResolve('get', {}); await getSystemConfig()
    expect(apiMethods.get).toHaveBeenCalledWith('/api/v1/system/config')
    mockResolve('post', {}); await reloadSystem()
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/system/reload')
  })

  it('takeover: toggle/status/queue/answer/batch/skip', async () => {
    mockResolve('post', {}); await toggleTakeover('o', true)
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/takeover/o/toggle', { enabled: true })
    mockResolve('get', {}); await getTakeoverStatus('o')
    expect(apiMethods.get).toHaveBeenCalledWith('/api/v1/takeover/o/status')
    await listTakeoverQueue('o')
    expect(apiMethods.get).toHaveBeenCalledWith('/api/v1/takeover/o/queue')
    mockResolve('post', {}); await answerTakeover('o', { pid: 'p1', answer: 'a' })
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/takeover/o/answer', { pid: 'p1', answer: 'a' })
    await answerTakeoverBatch('o', [{ answer: 'a' }])
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/takeover/o/answer/batch', { items: [{ answer: 'a' }] })
    await skipTakeover('o', 'p1')
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/takeover/o/skip', { pid: 'p1' })
  })

  it('roleplay: add/batch/list/update/delete', async () => {
    mockResolve('post', {}); await addRoleplay('o', { role: 'user', content: 'hi' })
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/roleplay/o/messages', { role: 'user', content: 'hi' })
    await addRoleplayBatch('o', [{ role: 'user', content: 'x' }])
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/roleplay/o/messages/batch', { items: [{ role: 'user', content: 'x' }] })
    mockResolve('get', {}); await listRoleplay('o')
    expect(apiMethods.get).toHaveBeenCalledWith('/api/v1/roleplay/o/messages', { params: { limit: 1000 } })
    mockResolve('put', {}); await updateRoleplay('o', 'm1', 'new')
    expect(apiMethods.put).toHaveBeenCalledWith('/api/v1/roleplay/o/messages/m1', { content: 'new' })
    mockResolve('delete', {}); await deleteRoleplay('o', 'm1')
    expect(apiMethods.delete).toHaveBeenCalledWith('/api/v1/roleplay/o/messages/m1')
  })
})

describe('client.ts token 注入', () => {
  beforeEach(() => { vi.clearAllMocks(); localStorage.clear() })

  it('无 token 不注入 X-Access-Token', async () => {
    mockResolve('get', {}); const ret: any = await listPersonas()
    expect(ret.__cfg.headers['X-Access-Token']).toBeUndefined()
  })
  it('有 token 注入 X-Access-Token', async () => {
    localStorage.setItem('access_token', 'tkn-abc')
    mockResolve('get', {}); const ret: any = await listPersonas()
    expect(ret.__cfg.headers['X-Access-Token']).toBe('tkn-abc')
  })
})

describe('client.ts 401 拦截', () => {
  beforeEach(() => { vi.clearAllMocks(); localStorage.clear() })

  it('401 → 清 token + 跳登录', async () => {
    localStorage.setItem('access_token', 'stale')
    mockReject('get', 401)
    await expect(getSystemConfig()).rejects.toEqual({ response: { status: 401 } })
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(routerPush).toHaveBeenCalledWith({ name: 'login' })
  })
  it('非 401 → 不跳转、不清 token', async () => {
    localStorage.setItem('access_token', 'keep')
    mockReject('get', 500)
    await expect(getSystemConfig()).rejects.toEqual({ response: { status: 500 } })
    expect(localStorage.getItem('access_token')).toBe('keep')
    expect(routerPush).not.toHaveBeenCalled()
  })
})
