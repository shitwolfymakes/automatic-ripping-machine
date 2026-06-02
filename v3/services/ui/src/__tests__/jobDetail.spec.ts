import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import JobDetail from '../views/JobDetail.vue'
import type { JobStatus } from '../api/types'
import { wsClient } from '../api/ws'

const baseJob = {
  id: 'job_x',
  drive_id: 'drv_x',
  disc_type: 'dvd',
  status: 'identified' as JobStatus,
  title: 'Iron Man',
  year: 2008,
  poster_url: null,
  poster_url_manual: null,
  metadata_json: {},
  resumed_from_crash: false,
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function detailFor(status: JobStatus): unknown {
  return {
    job: { ...baseJob, status },
    tracks: [],
  }
}

function ndjsonResponse(records: unknown[]): Response {
  const body = records.map((r) => JSON.stringify(r)).join('\n') + '\n'
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'application/x-ndjson' },
  })
}

async function mountWithStatus(status: JobStatus) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/jobs/:id', name: 'job', component: JobDetail }],
  })
  await router.push('/jobs/job_x')
  await router.isReady()
  // load() calls /api/jobs/:id, then transcodes.fetchAll() hits /api/transcodes.
  // JobLogsCard fetches /api/logs/:id (ndjson) and subscribes to a WS topic.
  // Stub everything: real WS would blow up under jsdom (no WebSocket).
  const fetchMock = vi.fn().mockImplementation((url: string) => {
    if (url.includes('/api/jobs/')) return Promise.resolve(jsonResponse(detailFor(status)))
    if (url.includes('/api/transcodes')) return Promise.resolve(jsonResponse([]))
    if (url.includes('/api/logs/')) return Promise.resolve(ndjsonResponse([]))
    return Promise.resolve(jsonResponse(null))
  })
  vi.stubGlobal('fetch', fetchMock)
  vi.spyOn(wsClient, 'start').mockImplementation(() => {})
  vi.spyOn(wsClient, 'subscribe').mockImplementation(() => () => {})
  const wrapper = mount(JobDetail, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

describe('JobDetail.vue identify-disc button', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    localStorage.setItem('arm_token', 'aaa.bbb.ccc')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows the Identify disc button when job is awaiting_user_id', async () => {
    const wrapper = await mountWithStatus('awaiting_user_id')
    expect(wrapper.find('[data-testid="identify-disc"]').exists()).toBe(true)
  })

  it('shows the Identify disc button when job is ripped_awaiting_identify', async () => {
    const wrapper = await mountWithStatus('ripped_awaiting_identify')
    expect(wrapper.find('[data-testid="identify-disc"]').exists()).toBe(true)
  })

  it.each<JobStatus>([
    'created',
    'identified',
    'ripping',
    'ripped',
    'ripped_partial',
    'abandoned',
    'failed',
  ])('hides the Identify disc button when status is %s', async (status) => {
    const wrapper = await mountWithStatus(status)
    expect(wrapper.find('[data-testid="identify-disc"]').exists()).toBe(false)
  })
})
