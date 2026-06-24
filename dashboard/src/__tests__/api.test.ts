/**
 * API 端点映射测试：mock axios client，验证 api/index 各函数调用正确的 URL/方法/参数。
 * 这是前后端契约的回归保护（端点路径/方法变动会被捕获）。
 * 作者: 李文煜
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/client', () => ({
  api: {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    put: vi.fn(() => Promise.resolve({ data: {} })),
    delete: vi.fn(() => Promise.resolve({ data: {} })),
  },
}))

import { api } from '@/api/client'
import {
  listPersonas, createPersona, deletePersona,
  enablePlugin, disablePlugin, setObjectPlugin,
  getMemory, getMemoryStats, forgetOneMemory,
  getModels, getHistory, getProposals, dismissProposal, bindPersonaModel,
} from '@/api'

describe('api endpoint mapping', () => {
  beforeEach(() => vi.clearAllMocks())

  it('persona: list/create/delete', async () => {
    await listPersonas()
    expect(api.get).toHaveBeenCalledWith('/api/v1/persona')
    await createPersona({ name: 'x' })
    expect(api.post).toHaveBeenCalledWith('/api/v1/persona', { name: 'x' })
    await deletePersona('p1')
    expect(api.delete).toHaveBeenCalledWith('/api/v1/persona/p1')
  })

  it('plugin: enable/disable/object config', async () => {
    await enablePlugin('tts')
    expect(api.post).toHaveBeenCalledWith('/api/v1/plugin/tts/enable')
    await disablePlugin('tts')
    expect(api.post).toHaveBeenCalledWith('/api/v1/plugin/tts/disable')
    await setObjectPlugin('o1', 'tts', { enabled: true })
    expect(api.put).toHaveBeenCalledWith('/api/v1/plugin/object/o1/tts', { enabled: true })
  })

  it('memory: get/stats/forget', async () => {
    await getMemory('o', 'episodic')
    expect(api.get).toHaveBeenCalledWith('/api/v1/memory/o', { params: { layer: 'episodic' } })
    await getMemoryStats('o')
    expect(api.get).toHaveBeenCalledWith('/api/v1/memory/o/stats')
    await forgetOneMemory('o', 'm1')
    expect(api.delete).toHaveBeenCalledWith('/api/v1/memory/o/m1')
  })

  it('admin: models/history/proposals/bind', async () => {
    await getModels()
    expect(api.get).toHaveBeenCalledWith('/api/v1/models')
    await getHistory('o', 10)
    expect(api.get).toHaveBeenCalledWith('/api/v1/history/o', { params: { limit: 10 } })
    await getProposals()
    expect(api.get).toHaveBeenCalledWith('/api/v1/persona_evolve/proposals')
    await dismissProposal('o')
    expect(api.delete).toHaveBeenCalledWith('/api/v1/persona_evolve/proposals/o')
    await bindPersonaModel('p', { provider: 'glm' })
    expect(api.put).toHaveBeenCalledWith('/api/v1/persona/p/model', { provider: 'glm' })
  })
})
