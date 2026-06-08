import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fetchSprayRecords } from './useSprayRecords'
import api from '../lib/api'

vi.mock('../lib/api', () => ({ default: { get: vi.fn() } }))

describe('fetchSprayRecords', () => {
  beforeEach(() => vi.clearAllMocks())

  it('GETs the records endpoint and returns the data array', async () => {
    api.get.mockResolvedValue({ data: [{ id: 'rec-1', product: 'engenia' }] })
    const data = await fetchSprayRecords()
    expect(api.get).toHaveBeenCalledWith('/dicamba/records')
    expect(data[0].id).toBe('rec-1')
  })
})
