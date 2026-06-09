import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fetchSprayRecords, fetchSprayPdfBlob } from './useSprayRecords'
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

describe('fetchSprayPdfBlob', () => {
  beforeEach(() => vi.clearAllMocks())

  // Bug: the PDF was a plain <a href> nav with no Authorization header -> 401
  // "Not authenticated". Routing the download through the axios client (blob)
  // attaches the Bearer token like every other authed call.
  it('GETs the pdf endpoint as a blob so axios attaches the Bearer token', async () => {
    const blob = new Blob(['%PDF-1.4'], { type: 'application/pdf' })
    api.get.mockResolvedValue({ data: blob })
    const out = await fetchSprayPdfBlob('abc-123')
    expect(api.get).toHaveBeenCalledWith('/dicamba/record/abc-123/pdf', {
      responseType: 'blob',
    })
    expect(out).toBe(blob)
  })
})
