import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Jobs from '../views/Jobs.vue'

const baseJob = {
  id: 'job_x',
  drive_id: 'drv_x',
  disc_type: 'dvd',
  status: 'ripping',
  title: 'Iron Man',
  year: 2008,
  metadata_json: {},
  resumed_from_crash: false,
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('Jobs.vue resumed_from_crash badge', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    localStorage.setItem('arm_token', 'aaa.bbb.ccc')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders the badge when resumed_from_crash and status is non-terminal', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse([{ ...baseJob, resumed_from_crash: true, status: 'ripping' }]),
        ),
    )
    const wrapper = mount(Jobs, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="resumed-badge-job_x"]').exists()).toBe(true)
  })

  it('hides the badge when status is terminal even if resumed_from_crash is true', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse([{ ...baseJob, resumed_from_crash: true, status: 'ripped' }]),
        ),
    )
    const wrapper = mount(Jobs, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="resumed-badge-job_x"]').exists()).toBe(false)
  })
})
