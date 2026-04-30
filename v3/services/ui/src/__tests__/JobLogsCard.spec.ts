import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import JobLogsCard from '../components/JobLogsCard.vue'
import { wsClient, type WSEnvelope } from '../api/ws'

// Capture the most recent handler the component registered against
// `wsClient.subscribe`, so the test can synthesize WS frames.
let capturedHandler: ((env: WSEnvelope) => void) | null = null

function ndjsonResponse(records: unknown[]): Response {
  const body = records.map((r) => JSON.stringify(r)).join('\n') + '\n'
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'application/x-ndjson' },
  })
}

function makeLine(msg: string, jobId = 'job_x'): Record<string, unknown> {
  return {
    ts: '2026-04-30T12:00:00+00:00',
    level: 'info',
    service: 'arm-backend',
    job_id: jobId,
    track_id: null,
    session_application_id: null,
    msg,
    extra: { logger: 'arm_backend.test' },
  }
}

describe('JobLogsCard.vue', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('arm_token', 'aaa.bbb.ccc')
    capturedHandler = null
    vi.spyOn(wsClient, 'start').mockImplementation(() => {})
    vi.spyOn(wsClient, 'subscribe').mockImplementation((_topic, handler) => {
      capturedHandler = handler
      return () => {
        capturedHandler = null
      }
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('seeds the pane with the initial GET /api/logs/{id} response', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          ndjsonResponse([makeLine('boot'), makeLine('identify'), makeLine('rip-start')]),
        ),
    )
    const wrapper = mount(JobLogsCard, { props: { jobId: 'job_x' } })
    await flushPromises()
    const pane = wrapper.find('[data-testid="logs-pane"]').text()
    expect(pane).toContain('boot')
    expect(pane).toContain('identify')
    expect(pane).toContain('rip-start')
  })

  it('appends WS-pushed log.line events to the pane', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ndjsonResponse([makeLine('seed-1')])))
    const wrapper = mount(JobLogsCard, { props: { jobId: 'job_x' } })
    await flushPromises()
    expect(capturedHandler).not.toBeNull()
    capturedHandler!({
      op: 'event',
      event_type: 'log.line',
      topic: 'logs.job_x',
      event_id: 'evt_1',
      emitted_at: '2026-04-30T12:00:00+00:00',
      job_id: 'job_x',
      track_id: null,
      payload: makeLine('live-1'),
    })
    capturedHandler!({
      op: 'event',
      event_type: 'log.line',
      topic: 'logs.job_x',
      event_id: 'evt_2',
      emitted_at: '2026-04-30T12:00:01+00:00',
      job_id: 'job_x',
      track_id: null,
      payload: makeLine('live-2'),
    })
    await flushPromises()
    const pane = wrapper.find('[data-testid="logs-pane"]').text()
    expect(pane).toMatch(/seed-1[\s\S]*live-1[\s\S]*live-2/)
  })

  it('triggers a fetch + object URL on download click', async () => {
    const blobBytes = new TextEncoder().encode('PK\x03\x04zip-bytes')
    const initial = ndjsonResponse([])
    const zipResponse = new Response(blobBytes, {
      status: 200,
      headers: { 'Content-Type': 'application/zip' },
    })
    const fetchMock = vi.fn().mockResolvedValueOnce(initial).mockResolvedValueOnce(zipResponse)
    vi.stubGlobal('fetch', fetchMock)
    const createSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fake-url')
    const revokeSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})

    const wrapper = mount(JobLogsCard, { props: { jobId: 'job_x' }, attachTo: document.body })
    await flushPromises()
    await wrapper.find('[data-testid="logs-download-zip"]').trigger('click')
    await flushPromises()

    const zipCall = fetchMock.mock.calls.find((c) =>
      typeof c[0] === 'string' ? c[0].endsWith('/api/logs/job_x.zip') : false,
    )
    expect(zipCall).toBeDefined()
    expect(createSpy).toHaveBeenCalledTimes(1)
    expect(revokeSpy).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
})
