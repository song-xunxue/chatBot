/**
 * API 契约测试（强化版）：
 *   1. 不再整体 mock @/api/client —— 让真实封装层运行，验证 .then(r=>r.data) 解包。
 *   2. 改为 mock 底层 axios，并提供"驱动拦截器"的伪实例，
 *      使 client.ts 的 request 拦截器(token 注入)与 response 拦截器(401 跳转)真实执行。
 *   3. 为 V1.1/V1.2 新封装补端点 URL + method + body 断言。
 * 作者: 李文煜
 * 日期: 2026-06-25
 *
 * 2026-06-25
 * 变更说明：
 *   1. 由"mock 整个 @/api/client"改为"mock axios + 驱动拦截器"，恢复对解包/token/401 的真实覆盖。
 *   2. 补充 reverseInfer / applyReverseInfer / takeover* / addRoleplaySingle / update|deleteHistoryMsg 契约断言。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// —— hoisted 共享态：vi.mock 工厂会被提升到文件顶部，普通 let 不可被工厂引用 ——
// 用 vi.hoisted 把可变容器提前创建，工厂与测试体共享同一份引用
const hoisted = vi.hoisted(() => ({
  routerPush: vi.fn(),
  requestFulfilled: null as ((cfg: any) => any) | null,
  responseRejected: null as ((err: any) => any) | null,
  apiMethods: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

// —— mock 依赖：避免加载真实 router（含懒加载视图组件）——
vi.mock('@/router', () => ({ default: { push: hoisted.routerPush } }))

// —— mock axios：提供"驱动拦截器"的伪实例 ——
// axios.create 返回的对象：
//   - 拦截器 use 把 handler 存起来，供下方在 method 被调用时手动驱动
//   - get/post/put/delete 在被调用时，先经 request 拦截器处理 cfg，再 resolve/reject
vi.mock('axios', () => {
  const fakeInstance = {
    interceptors: {
      request: { use: (ful: (cfg: any) => any) => { hoisted.requestFulfilled = ful } },
      response: {
        use: (_ful: any, rej: (err: any) => any) => { hoisted.responseRejected = rej },
      },
    },
    ...hoisted.apiMethods,
  }
  return {
    default: { create: () => fakeInstance },
  }
})

// 测试体内便捷别名（仅引用，不重新声明）
const routerPush = hoisted.routerPush
const apiMethods = hoisted.apiMethods

import {
  listPersonas, createPersona, deletePersona, updatePersona,
  enablePlugin, disablePlugin, setObjectPlugin,
  getMemory, getMemoryStats, forgetOneMemory,
  getModels, getHistory, getProposals, dismissProposal, bindPersonaModel,
  // V1.1/V1.2 新封装
  reverseInfer, applyReverseInfer,
  takeoverToggle, takeoverStatus, takeoverPending, takeoverAnswer,
  addRoleplaySingle,
  updateHistoryMsg, deleteHistoryMsg,
} from '@/api'

// 让某个 method 返回特定 response，先经过 request 拦截器处理 cfg，再 resolve
// 把经拦截器处理后的 cfg 塞进 response.data.__cfg，使封装层解包后仍可断言 token 注入
function mockResolve(method: 'get' | 'post' | 'put' | 'delete', responseData: any) {
  apiMethods[method].mockImplementation(async (url: string, config?: any) => {
    // 真实 axios 请求 config 含 headers 字段，这里初始化空对象供拦截器写入
    const base = { url, headers: {}, ...config }
    const cfg = hoisted.requestFulfilled ? hoisted.requestFulfilled(base) : base
    return { data: { ...responseData, __cfg: cfg } }
  })
}

// 让某个 method reject 一个带 status 的错误，并驱动 response 错误拦截器
// （模拟 axios 行为：请求 reject 时会执行 response 拦截器的错误处理函数）
function mockReject(method: 'get' | 'post' | 'put' | 'delete', status: number) {
  apiMethods[method].mockImplementation(async () => {
    const err = { response: { status } }
    if (hoisted.responseRejected) return hoisted.responseRejected(err)
    throw err
  })
}

describe('api endpoint mapping + wrapper unwrapping', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('wrapper 解包：封装函数返回 r.data 而非整个 response', async () => {
    mockResolve('get', { id: 'p1', name: 'alice' })
    // listPersonas 应返回 r.data（即 {id,name,...}），不是 { data: {...} }
    const ret: any = await listPersonas()
    // 关键：返回值不含外层 data 包裹，且包含原始 payload 字段
    expect(ret).not.toHaveProperty('data')
    expect(ret.id).toBe('p1')
    expect(ret.name).toBe('alice')
  })

  it('persona: list/create/delete', async () => {
    mockResolve('get', {})
    await listPersonas()
    expect(apiMethods.get).toHaveBeenCalledWith('/api/v1/persona')
    mockResolve('post', {})
    await createPersona({ name: 'x' })
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/persona', { name: 'x' })
    mockResolve('delete', {})
    await deletePersona('p1')
    expect(apiMethods.delete).toHaveBeenCalledWith('/api/v1/persona/p1')
  })

  it('plugin: enable/disable/object config', async () => {
    mockResolve('post', {})
    await enablePlugin('tts')
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/plugin/tts/enable')
    await disablePlugin('tts')
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/plugin/tts/disable')
    mockResolve('put', {})
    await setObjectPlugin('o1', 'tts', { enabled: true })
    expect(apiMethods.put).toHaveBeenCalledWith('/api/v1/plugin/object/o1/tts', { enabled: true })
  })

  it('memory: get/stats/forget', async () => {
    mockResolve('get', {})
    await getMemory('o', 'episodic')
    expect(apiMethods.get).toHaveBeenCalledWith('/api/v1/memory/o', { params: { layer: 'episodic' } })
    await getMemoryStats('o')
    expect(apiMethods.get).toHaveBeenCalledWith('/api/v1/memory/o/stats')
    mockResolve('delete', {})
    await forgetOneMemory('o', 'm1')
    expect(apiMethods.delete).toHaveBeenCalledWith('/api/v1/memory/o/m1')
  })

  it('admin: models/history/proposals/bind', async () => {
    mockResolve('get', {})
    await getModels()
    expect(apiMethods.get).toHaveBeenCalledWith('/api/v1/models')
    await getHistory('o', 10)
    expect(apiMethods.get).toHaveBeenCalledWith('/api/v1/history/o', { params: { limit: 10 } })
    await getProposals()
    expect(apiMethods.get).toHaveBeenCalledWith('/api/v1/persona_evolve/proposals')
    mockResolve('delete', {})
    await dismissProposal('o')
    expect(apiMethods.delete).toHaveBeenCalledWith('/api/v1/persona_evolve/proposals/o')
    mockResolve('put', {})
    await bindPersonaModel('p', { provider: 'glm' })
    expect(apiMethods.put).toHaveBeenCalledWith('/api/v1/persona/p/model', { provider: 'glm' })
  })

  // —— V1.1/V1.2 新封装契约 ——
  it('V1.2 history edit: update/delete message', async () => {
    mockResolve('put', {})
    await updateHistoryMsg('o1', 'm1', { text: 'hi' })
    expect(apiMethods.put).toHaveBeenCalledWith('/api/v1/history/o1/m1', { text: 'hi' })
    mockResolve('delete', {})
    await deleteHistoryMsg('o1', 'm1')
    expect(apiMethods.delete).toHaveBeenCalledWith('/api/v1/history/o1/m1')
  })

  it('V1.1 roleplay single insert', async () => {
    mockResolve('post', {})
    await addRoleplaySingle('o1', { role: 'user', content: 'c' })
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/roleplay/o1/messages/single', {
      role: 'user', content: 'c',
    })
  })

  it('V1.2 reverse-infer: preview (default mode) + apply (confirm_token)', async () => {
    mockResolve('post', {})
    await reverseInfer('o1') // 默认 fill_empty
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/roleplay/o1/reverse-infer', { mode: 'fill_empty' })
    await reverseInfer('o1', 'overwrite')
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/roleplay/o1/reverse-infer', { mode: 'overwrite' })
    await applyReverseInfer('o1', 'tok123')
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/roleplay/o1/reverse-infer/apply', {
      confirm_token: 'tok123',
    })
  })

  it('V1.1 takeover: toggle/status/pending/answer', async () => {
    mockResolve('post', {})
    await takeoverToggle('o1', true)
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/takeover/toggle', {
      object_id: 'o1', enabled: true,
    })
    await takeoverAnswer('o1', 'pid9', 'yes')
    expect(apiMethods.post).toHaveBeenCalledWith('/api/v1/takeover/answer', {
      object_id: 'o1', pending_id: 'pid9', answer: 'yes',
    })
    mockResolve('get', {})
    await takeoverStatus('o1')
    expect(apiMethods.get).toHaveBeenCalledWith('/api/v1/takeover/status', {
      params: { object_id: 'o1' },
    })
    await takeoverPending()
    expect(apiMethods.get).toHaveBeenCalledWith('/api/v1/takeover/pending')
  })
})

describe('client.ts token 注入 (request interceptor)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('无 token 时不注入 X-Access-Token 头', async () => {
    mockResolve('get', {})
    const ret: any = await listPersonas()
    const cfg = ret.__cfg
    expect(cfg.headers['X-Access-Token']).toBeUndefined()
  })

  it('有 token 时注入 X-Access-Token 头', async () => {
    localStorage.setItem('access_token', 'tkn-abc')
    mockResolve('get', {})
    const ret: any = await listPersonas()
    const cfg = ret.__cfg
    expect(cfg.headers['X-Access-Token']).toBe('tkn-abc')
  })
})

describe('client.ts 401 拦截 (response interceptor)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('401 → 清除 token + 跳转登录页', async () => {
    localStorage.setItem('access_token', 'stale')
    mockReject('get', 401)
    // response 拦截器 reject err 前，会清 token 并 push login
    await expect(getModels()).rejects.toEqual({ response: { status: 401 } })
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(routerPush).toHaveBeenCalledWith({ name: 'login' })
  })

  it('非 401 错误 → 不跳转、不清 token', async () => {
    localStorage.setItem('access_token', 'keep')
    mockReject('get', 500)
    await expect(getModels()).rejects.toEqual({ response: { status: 500 } })
    expect(localStorage.getItem('access_token')).toBe('keep')
    expect(routerPush).not.toHaveBeenCalled()
  })
})
