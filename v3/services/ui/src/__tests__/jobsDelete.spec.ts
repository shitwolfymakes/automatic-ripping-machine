import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useJobsStore } from '../stores/jobs'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function emptyResponse(status = 204): Response {
  return new Response(null, { status })
}

const fakeJob = {
  id: 'job_a',
  drive_id: 'drv_x',
  disc_type: 'dvd' as const,
  status: 'ripped' as const,
  title: 'X',
  year: 2000,
  poster_url: null,
  poster_url_manual: null,
  metadata_json: {},
  resumed_from_crash: false,
}

describe('jobs store delete actions', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    localStorage.setItem('arm_token', 'aaa.bbb.ccc')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('deleteJob without delete_raw posts plain DELETE and prunes local state', async () => {
    const fetchMock = vi.fn().mockResolvedValue(emptyResponse())
    vi.stubGlobal('fetch', fetchMock)
    const store = useJobsStore()
    store.jobs = [fakeJob, { ...fakeJob, id: 'job_b' }]

    await store.deleteJob('job_a')

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/jobs/job_a')
    expect(init.method).toBe('DELETE')
    expect(store.jobs.map((j) => j.id)).toEqual(['job_b'])
  })

  it('deleteJob with delete_raw appends the query string', async () => {
    const fetchMock = vi.fn().mockResolvedValue(emptyResponse())
    vi.stubGlobal('fetch', fetchMock)
    const store = useJobsStore()
    store.jobs = [fakeJob]

    await store.deleteJob('job_a', { deleteRaw: true })

    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/jobs/job_a?delete_raw=true')
  })

  it('deleteAll returns the partition response and prunes deleted ids', async () => {
    const result = {
      deleted_ids: ['job_a', 'job_b'],
      skipped_non_terminal: ['job_c'],
    }
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(result))
    vi.stubGlobal('fetch', fetchMock)
    const store = useJobsStore()
    store.jobs = [
      fakeJob,
      { ...fakeJob, id: 'job_b' },
      { ...fakeJob, id: 'job_c', status: 'ripping' },
    ]

    const got = await store.deleteAll({ deleteRaw: true })
    expect(got).toEqual(result)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/jobs?delete_raw=true')
    expect(init.method).toBe('DELETE')
    // Survivor list matches the skipped set.
    expect(store.jobs.map((j) => j.id)).toEqual(['job_c'])
  })

  it('deleteAll without delete_raw omits the query string', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ deleted_ids: [], skipped_non_terminal: [] }))
    vi.stubGlobal('fetch', fetchMock)
    const store = useJobsStore()

    await store.deleteAll()

    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/jobs')
  })
})
