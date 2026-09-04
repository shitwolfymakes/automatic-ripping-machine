import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import JobManual from '../views/JobManual.vue'
import type { DriveView } from '../api/types'

function drive(over: Partial<DriveView> = {}): DriveView {
  return {
    id: 'drv_x',
    hostname: 'arm-ripper-abc',
    device_path: '/dev/sr0',
    display_name: null,
    status: 'online',
    last_seen_at: null,
    media_status: null,
    media_status_at: null,
    default_session_id: null,
    rip_speed: null,
    drive_mode: null,
    uhd_capable: null,
    prescan_cache_mb: null,
    prescan_timeout: null,
    prescan_retries: null,
    disc_enum_timeout: null,
    created_at: null,
    updated_at: null,
    lifecycle: 'enrolled',
    present: true,
    identity_kind: 'by_id',
    serial: 'AAAABBBB000E',
    by_id_name: 'usb-PIONEER_BD-RW_BDR-S12JX_AAAABBBB000E-0:0',
    vendor: 'PIONEER',
    model: 'BD-RW BDR-S12JX',
    last_error: null,
    current_job: null,
    ...over,
  }
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function stubFetch(state: { drives: DriveView[] }) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: RequestInfo) => {
      const url = typeof input === 'string' ? input : input.url
      if (url.endsWith('/api/drives')) return Promise.resolve(jsonResponse(state.drives))
      if (url.endsWith('/api/sessions')) return Promise.resolve(jsonResponse([]))
      return Promise.resolve(jsonResponse({}, 404))
    }),
  )
}

async function mountJobManual() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/jobs/manual', name: 'manual', component: JobManual },
      { path: '/jobs', name: 'jobs', component: { template: '<div />' } },
      { path: '/dashboard', name: 'dashboard', component: { template: '<div />' } },
    ],
  })
  await router.push('/jobs/manual')
  await router.isReady()
  const wrapper = mount(JobManual, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

describe('JobManual.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    localStorage.setItem('arm_token', 'aaa.bbb.ccc')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('offers only enrolled drives, excluding detected ones', async () => {
    const enrolledOnline = drive({ id: 'drv_e', lifecycle: 'enrolled', status: 'online' })
    const detectedOnline = drive({ id: 'drv_d', lifecycle: 'detected', status: 'online' })
    stubFetch({ drives: [enrolledOnline, detectedOnline] })
    const wrapper = await mountJobManual()
    const select = wrapper.find('#drive')
    const options = select.findAll('option').filter((o) => o.attributes('value') !== '')
    expect(options.length).toBe(1)
    expect(options[0].attributes('value')).toBe('drv_e')
    expect(wrapper.html()).not.toContain('drv_d')
  })

  it('auto-selects a single enrolled online drive', async () => {
    const enrolledOnline = drive({ id: 'drv_e', lifecycle: 'enrolled', status: 'online' })
    stubFetch({ drives: [enrolledOnline] })
    const wrapper = await mountJobManual()
    const select = wrapper.find('#drive').element as HTMLSelectElement
    expect(select.value).toBe('drv_e')
  })

  it('shows the enroll-prompt empty state when there are no enrolled drives', async () => {
    const detectedOnline = drive({ id: 'drv_d', lifecycle: 'detected', status: 'online' })
    stubFetch({ drives: [detectedOnline] })
    const wrapper = await mountJobManual()
    expect(wrapper.text()).toContain('No enrolled drives — enroll one on the Drives page.')
  })
})
