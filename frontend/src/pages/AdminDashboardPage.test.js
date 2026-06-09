import { describe, expect, it, vi } from 'vitest'
import { loadAquiferStress } from './AdminDashboardPage'

describe('loadAquiferStress', () => {
  it('returns the aquifer stress payload', async () => {
    const apiClient = {
      get: vi.fn(async () => ({ data: { data: { '05001': 'high' } } })),
    }

    await expect(loadAquiferStress(apiClient)).resolves.toEqual({ '05001': 'high' })
    expect(apiClient.get).toHaveBeenCalledWith('/admin/aquifer-stress')
  })

  it('lets callers handle aquifer load failures', async () => {
    const apiClient = {
      get: vi.fn(async () => {
        throw new Error('network failed')
      }),
    }

    await expect(loadAquiferStress(apiClient)).rejects.toThrow('network failed')
  })
})
