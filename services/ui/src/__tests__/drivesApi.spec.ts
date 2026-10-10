import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  enrollDrive,
  ignoreDrive,
  listDrives,
  rescanDrives,
  unenrollDrive,
  unignoreDrive,
} from '../api/drives'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('api/drives', () => {
  beforeEach(() => {
    localStorage.setItem('arm_token', 'aaa.bbb.ccc')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it.each([
    ['enroll', enrollDrive],
    ['ignore', ignoreDrive],
    ['unignore', unignoreDrive],
  ])('%s POSTs to the lifecycle endpoint and returns the drive', async (op, fn) => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ id: 'drv_1', lifecycle: 'enrolled' }))
    vi.stubGlobal('fetch', fetchMock)
    const d = await fn('drv_1')
    expect(d.id).toBe('drv_1')
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`/api/drives/drv_1/${op}`)
    expect(init.method).toBe('POST')
  })

  it('unenroll tolerates an empty 204', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
    await expect(unenrollDrive('drv_1')).resolves.toBeUndefined()
  })

  it('unenroll tolerates a 200 with a body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ id: 'drv_1' })))
    await expect(unenrollDrive('drv_1')).resolves.toBeUndefined()
  })

  it('rescan POSTs and returns the counts', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        online: 1,
        stale: 0,
        detected: 2,
        ignored: 0,
        enrolled: 1,
        absent: 0,
        pruned: 0,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const r = await rescanDrives()
    expect(r.detected).toBe(2)
    expect((fetchMock.mock.calls[0] as [string])[0]).toBe('/api/drives/rescan')
  })

  it('listDrives GETs /api/drives', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)
    expect(await listDrives()).toEqual([])
    expect((fetchMock.mock.calls[0] as [string])[0]).toBe('/api/drives')
  })

  it('surfaces the backend detail on a 409', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(jsonResponse({ detail: 'cannot unenroll: a drive is ripping' }, 409)),
    )
    await expect(unenrollDrive('drv_1')).rejects.toThrow('cannot unenroll: a drive is ripping')
  })
})
