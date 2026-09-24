import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import Drives from '../views/Drives.vue'
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
const enrolled = drive()

const sessionA = {
  id: 'ses_a',
  name: 'Movie to Plex 1080p',
  media_type: 'movie',
  is_builtin: true,
  rip_preset_id: 'rpr_x',
  transcode_preset_id: 'tpr_x',
  output_path_template: '{title}.mkv',
  overrides_json: null,
  created_by_user_id: null,
  created_at: null,
  updated_at: null,
}

const sessionB = { ...sessionA, id: 'ses_b', name: 'TV to Jellyfin' }

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** fetch stub: `drives` is re-read on every /api/drives call so tests can mutate it between actions. */
function stubFetch(
  state: { drives: DriveView[] },
  extra: (url: string, init?: RequestInit) => Response | null = () => null,
) {
  const calls: { url: string; method: string }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: RequestInfo, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.url
      calls.push({ url, method: init?.method ?? 'GET' })
      const custom = extra(url, init)
      if (custom) return Promise.resolve(custom)
      if (url.endsWith('/api/drives')) return Promise.resolve(jsonResponse(state.drives))
      if (url.endsWith('/api/sessions')) return Promise.resolve(jsonResponse([sessionA, sessionB]))
      if (url.endsWith('/api/config'))
        return Promise.resolve(jsonResponse({ drive_scan_interval_seconds: 30 }))
      return Promise.resolve(jsonResponse({}, 404))
    }),
  )
  return calls
}

describe('Drives.vue', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('arm_token', 'aaa.bbb.ccc')
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('renders one option per session plus a none entry', async () => {
    stubFetch({ drives: [enrolled] })
    const wrapper = mount(Drives)
    await flushPromises()
    const select = wrapper.find(`[data-testid="default-session-${enrolled.id}"]`)
    expect(select.exists()).toBe(true)
    const options = select.findAll('option')
    expect(options.length).toBe(3)
    expect(options[0].text()).toContain('none')
    expect(options[1].text()).toContain('Movie to Plex 1080p')
    expect(options[2].text()).toContain('TV to Jellyfin')
  })

  it('shows the identity line with the current node and the serial', async () => {
    stubFetch({ drives: [enrolled] })
    const wrapper = mount(Drives)
    await flushPromises()
    expect(wrapper.find('[data-testid="identity-drv_x"]').text()).toBe(
      'BD-RW BDR-S12JX · AAAABBBB000E · /dev/sr0',
    )
  })

  it('renders detached distinctly and greys the row', async () => {
    stubFetch({ drives: [drive({ status: 'offline', media_status: 'detached', present: false })] })
    const wrapper = mount(Drives)
    await flushPromises()
    const badge = wrapper.find('[data-testid="status-drv_x"]')
    expect(badge.text()).toBe('○ detached: reconnect the drive')
    expect(badge.classes()).toContain('detached')
    expect(wrapper.find('[data-testid="enrolled-row-drv_x"]').classes()).toContain('detached')
  })

  it('shows the error reason', async () => {
    stubFetch({
      drives: [
        drive({
          status: 'error',
          last_error: 'identity mismatch: row is bound to X but the ripper resolved Y',
        }),
      ],
    })
    const wrapper = mount(Drives)
    await flushPromises()
    const badge = wrapper.find('[data-testid="status-drv_x"]')
    expect(badge.text()).toContain('identity mismatch')
    expect(badge.classes()).toContain('error')
  })

  it('disables Unenroll while the drive is ripping', async () => {
    stubFetch({ drives: [drive({ status: 'ripping' })] })
    const wrapper = mount(Drives)
    await flushPromises()
    expect(
      (wrapper.find('[data-testid="unenroll-drv_x"]').element as HTMLButtonElement).disabled,
    ).toBe(true)
  })

  it('Unenroll confirms, POSTs, and refetches the list', async () => {
    const state = { drives: [enrolled] }
    const calls = stubFetch(state, (url, init) => {
      if (url.endsWith('/api/drives/drv_x/unenroll') && init?.method === 'POST') {
        state.drives = [drive({ lifecycle: 'detected' })]
        return new Response(null, { status: 204 })
      }
      return null
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = mount(Drives)
    await flushPromises()
    await wrapper.find('[data-testid="unenroll-drv_x"]').trigger('click')
    await flushPromises()
    expect(window.confirm).toHaveBeenCalledWith(
      expect.stringContaining('will reappear on the next rescan'),
    )
    expect(
      calls.some((c) => c.url.endsWith('/api/drives/drv_x/unenroll') && c.method === 'POST'),
    ).toBe(true)
    expect(wrapper.find('[data-testid="enrolled-row-drv_x"]').exists()).toBe(false)
  })

  it('Unenroll does nothing when the confirm is declined', async () => {
    const calls = stubFetch({ drives: [enrolled] })
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const wrapper = mount(Drives)
    await flushPromises()
    await wrapper.find('[data-testid="unenroll-drv_x"]').trigger('click')
    await flushPromises()
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
  })

  it('surfaces a 409 detail in the error banner and keeps the row', async () => {
    stubFetch({ drives: [enrolled] }, (url, init) =>
      url.endsWith('/unenroll') && init?.method === 'POST'
        ? jsonResponse({ detail: 'cannot unenroll: a drive is ripping' }, 409)
        : null,
    )
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = mount(Drives)
    await flushPromises()
    await wrapper.find('[data-testid="unenroll-drv_x"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="drives-error"]').text()).toContain(
      'cannot unenroll: a drive is ripping',
    )
    expect(wrapper.find('[data-testid="enrolled-row-drv_x"]').exists()).toBe(true)
  })

  it('clears the poll timer on an immediate unmount, even mid-initial-load', async () => {
    const calls: { url: string; method: string }[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: RequestInfo, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.url
        calls.push({ url, method: init?.method ?? 'GET' })
        if (url.endsWith('/api/drives')) return new Promise(() => {}) // never resolves
        return Promise.resolve(jsonResponse({}, 404))
      }),
    )
    const wrapper = mount(Drives)
    wrapper.unmount()
    const before = calls.filter((c) => c.url.endsWith('/api/drives')).length
    await vi.advanceTimersByTimeAsync(30_000)
    expect(calls.filter((c) => c.url.endsWith('/api/drives')).length).toBe(before)
  })

  it('re-polls /api/drives every 10 s and stops on unmount', async () => {
    const calls = stubFetch({ drives: [enrolled] })
    const wrapper = mount(Drives)
    await flushPromises()
    const before = calls.filter((c) => c.url.endsWith('/api/drives')).length
    await vi.advanceTimersByTimeAsync(10_000)
    await flushPromises()
    expect(calls.filter((c) => c.url.endsWith('/api/drives')).length).toBe(before + 1)
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(20_000)
    expect(calls.filter((c) => c.url.endsWith('/api/drives')).length).toBe(before + 1)
  })

  const detected = drive({
    id: 'drv_d',
    lifecycle: 'detected',
    hostname: 'scan-drv_d',
    status: 'online',
  })
  const portDrive = drive({
    id: 'drv_p',
    lifecycle: 'detected',
    hostname: 'scan-drv_p',
    serial: null,
    by_id_name: null,
    identity_kind: 'port',
    model: 'OLD-ATAPI',
  })
  const ignored = drive({ id: 'drv_i', lifecycle: 'ignored', hostname: 'scan-drv_i' })

  it('lists detected drives with model, serial, node, last seen and actions', async () => {
    stubFetch({ drives: [enrolled, detected] })
    const wrapper = mount(Drives)
    await flushPromises()
    const row = wrapper.find('[data-testid="detected-row-drv_d"]')
    expect(row.exists()).toBe(true)
    expect(row.text()).toContain('BD-RW BDR-S12JX')
    expect(row.text()).toContain('AAAABBBB000E')
    expect(row.text()).toContain('/dev/sr0')
    expect(wrapper.find('[data-testid="enroll-drv_d"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ignore-drv_d"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="enrolled-row-drv_d"]').exists()).toBe(false)
  })

  it('flags a port-identity drive in amber', async () => {
    stubFetch({ drives: [portDrive] })
    const wrapper = mount(Drives)
    await flushPromises()
    const cell = wrapper.find('[data-testid="serial-drv_p"]')
    expect(cell.text()).toBe('no serial, identified by port')
    expect(cell.classes()).toContain('warn')
  })

  it('shows the empty state with the scan interval when nothing is detected', async () => {
    stubFetch({ drives: [enrolled] })
    const wrapper = mount(Drives)
    await flushPromises()
    expect(wrapper.find('[data-testid="detected-empty"]').text()).toBe(
      'No unenrolled drives. Plug one in and it appears here within 30s.',
    )
  })

  it('falls back to "a minute" when the config is not readable', async () => {
    stubFetch({ drives: [enrolled] }, (url) =>
      url.endsWith('/api/config') ? jsonResponse({}, 403) : null,
    )
    const wrapper = mount(Drives)
    await flushPromises()
    expect(wrapper.find('[data-testid="detected-empty"]').text()).toContain('within a minute.')
  })

  it('Enroll POSTs and moves the drive to the enrolled table', async () => {
    const state = { drives: [detected] }
    stubFetch(state, (url, init) => {
      if (url.endsWith('/api/drives/drv_d/enroll') && init?.method === 'POST') {
        state.drives = [drive({ id: 'drv_d', lifecycle: 'enrolled' })]
        return jsonResponse(state.drives[0])
      }
      return null
    })
    const wrapper = mount(Drives)
    await flushPromises()
    await wrapper.find('[data-testid="enroll-drv_d"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="enrolled-row-drv_d"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="detected-row-drv_d"]').exists()).toBe(false)
  })

  it('a failed Enroll shows the backend detail and leaves the drive detected', async () => {
    stubFetch({ drives: [detected] }, (url, init) =>
      url.endsWith('/enroll') && init?.method === 'POST'
        ? jsonResponse({ detail: 'ImageNotFound: arm-ripper:latest' }, 502)
        : null,
    )
    const wrapper = mount(Drives)
    await flushPromises()
    await wrapper.find('[data-testid="enroll-drv_d"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="drives-error"]').text()).toContain('ImageNotFound')
    expect(wrapper.find('[data-testid="detected-row-drv_d"]').exists()).toBe(true)
  })

  it('Ignore moves the drive into the collapsed Ignored section', async () => {
    const state = { drives: [detected] }
    stubFetch(state, (url, init) => {
      if (url.endsWith('/api/drives/drv_d/ignore') && init?.method === 'POST') {
        state.drives = [drive({ id: 'drv_d', lifecycle: 'ignored' })]
        return jsonResponse(state.drives[0])
      }
      return null
    })
    const wrapper = mount(Drives)
    await flushPromises()
    await wrapper.find('[data-testid="ignore-drv_d"]').trigger('click')
    await flushPromises()
    const toggle = wrapper.find('[data-testid="ignored-toggle"]')
    expect(toggle.text()).toBe('Ignored (1) ▸')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('[data-testid="ignored-row-drv_d"]').exists()).toBe(false) // collapsed
    await toggle.trigger('click')
    expect(wrapper.find('[data-testid="ignored-toggle"]').text()).toBe('Ignored (1) ▾')
    expect(wrapper.find('[data-testid="ignored-toggle"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('[data-testid="ignored-row-drv_d"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="unignore-drv_d"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="enroll-drv_d"]').exists()).toBe(true)
  })

  it('Un-ignore POSTs and the drive returns to the detected list', async () => {
    const state = { drives: [ignored] }
    const calls = stubFetch(state, (url, init) => {
      if (url.endsWith('/api/drives/drv_i/unignore') && init?.method === 'POST') {
        state.drives = [drive({ id: 'drv_i', lifecycle: 'detected' })]
        return jsonResponse(state.drives[0])
      }
      return null
    })
    const wrapper = mount(Drives)
    await flushPromises()
    await wrapper.find('[data-testid="ignored-toggle"]').trigger('click')
    await wrapper.find('[data-testid="unignore-drv_i"]').trigger('click')
    await flushPromises()
    expect(
      calls.some((c) => c.url.endsWith('/api/drives/drv_i/unignore') && c.method === 'POST'),
    ).toBe(true)
    expect(wrapper.find('[data-testid="detected-row-drv_i"]').exists()).toBe(true)
  })

  it('hides the Ignored section when there is nothing ignored', async () => {
    stubFetch({ drives: [enrolled] })
    const wrapper = mount(Drives)
    await flushPromises()
    expect(wrapper.find('[data-testid="ignored-toggle"]').exists()).toBe(false)
  })

  it('Rescan POSTs, shows the counts, and refetches both lists', async () => {
    const state = { drives: [enrolled] }
    const calls = stubFetch(state, (url, init) => {
      if (url.endsWith('/api/drives/rescan') && init?.method === 'POST') {
        state.drives = [enrolled, detected]
        return jsonResponse({
          online: 1,
          stale: 0,
          detected: 1,
          ignored: 0,
          enrolled: 1,
          absent: 0,
          pruned: 0,
        })
      }
      return null
    })
    const wrapper = mount(Drives)
    await flushPromises()
    await wrapper.find('[data-testid="rescan"]').trigger('click')
    await flushPromises()
    expect(calls.some((c) => c.url.endsWith('/api/drives/rescan') && c.method === 'POST')).toBe(
      true,
    )
    expect(wrapper.find('[data-testid="rescan-summary"]').text()).toBe(
      '1 detected · 1 enrolled · 0 ignored',
    )
    expect(wrapper.find('[data-testid="detected-row-drv_d"]').exists()).toBe(true)
  })
})
