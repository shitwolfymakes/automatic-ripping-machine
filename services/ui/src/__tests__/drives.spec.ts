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
  name: 'Movie → Plex 1080p',
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

const sessionB = { ...sessionA, id: 'ses_b', name: 'TV → Jellyfin' }

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
    expect(options[1].text()).toContain('Movie → Plex 1080p')
    expect(options[2].text()).toContain('TV → Jellyfin')
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
    expect(badge.text()).toBe('○ detached — reconnect the drive')
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
})
