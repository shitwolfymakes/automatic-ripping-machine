import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Config from '../views/Config.vue'

const baseConfig = {
  tmdb_api_key: null,
  omdb_api_key: null,
  tvdb_api_key: null,
  makemkv_key: null,
  musicbrainz_user_agent: null,
  auto_transcode_on_idle: false,
  auto_rip_on_insert: true,
  block_on_miss: true,
  ripping_paused: false,
  default_retention_policy: 'prune_after_session',
  notification_apprise_urls: [],
  notifications_enabled: false,
  metadata_provider: 'tmdb',
  makemkv_key_valid: null,
  makemkv_key_state: null,
  makemkv_key_checked_at: null,
  updated_by_user_id: null,
  updated_at: null,
  drive_scan_interval_seconds: 30,
  drive_detected_prune_days: 7,
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('Config.vue notifications', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    localStorage.setItem('arm_token', 'aaa.bbb.ccc')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders the enable checkbox unchecked by default', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(baseConfig)))
    const wrapper = mount(Config)
    await flushPromises()
    const checkbox = wrapper.find('[data-testid="notifications-enabled"]')
    expect(checkbox.exists()).toBe(true)
    expect((checkbox.element as HTMLInputElement).checked).toBe(false)
  })

  it('sends notifications_enabled=true in the PATCH body when toggled', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(baseConfig))
      .mockResolvedValueOnce(jsonResponse({ ...baseConfig, notifications_enabled: true }))
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(Config)
    await flushPromises()

    const checkbox = wrapper.find('[data-testid="notifications-enabled"]')
    await checkbox.setValue(true)
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    const patchCall = fetchMock.mock.calls.find((c) => c[1]?.method === 'PATCH')
    expect(patchCall).toBeDefined()
    const body = JSON.parse(patchCall![1].body as string)
    expect(body.notifications_enabled).toBe(true)
  })

  it('sends makemkv_key in the PATCH body when set', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(baseConfig))
      .mockResolvedValueOnce(jsonResponse({ ...baseConfig, makemkv_key: 'T-abc123' }))
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(Config)
    await flushPromises()

    const field = wrapper.find('[data-testid="makemkv-key"]')
    expect(field.exists()).toBe(true)
    await field.setValue('T-abc123')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    const patchCall = fetchMock.mock.calls.find((c) => c[1]?.method === 'PATCH')
    expect(patchCall).toBeDefined()
    const body = JSON.parse(patchCall![1].body as string)
    expect(body.makemkv_key).toBe('T-abc123')
  })

  it('sends metadata_provider in the PATCH body when changed', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(baseConfig))
      .mockResolvedValueOnce(jsonResponse({ ...baseConfig, metadata_provider: 'omdb' }))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(Config)
    await flushPromises()
    const select = wrapper.find('[data-testid="metadata-provider"]')
    expect(select.exists()).toBe(true)
    await select.setValue('omdb')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    const patchCall = fetchMock.mock.calls.find((c) => c[1]?.method === 'PATCH')
    const body = JSON.parse(patchCall![1].body as string)
    expect(body.metadata_provider).toBe('omdb')
  })

  it('sends tvdb_api_key in the PATCH body when set', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(baseConfig))
      .mockResolvedValueOnce(jsonResponse({ ...baseConfig, tvdb_api_key: 'tvdb-xyz' }))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(Config)
    await flushPromises()
    const field = wrapper.find('[data-testid="tvdb-key"]')
    expect(field.exists()).toBe(true)
    await field.setValue('tvdb-xyz')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    const patchCall = fetchMock.mock.calls.find((c) => c[1]?.method === 'PATCH')
    const body = JSON.parse(patchCall![1].body as string)
    expect(body.tvdb_api_key).toBe('tvdb-xyz')
  })

  it('sends ripping_paused in the PATCH body when toggled', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(baseConfig))
      .mockResolvedValueOnce(jsonResponse({ ...baseConfig, ripping_paused: true }))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(Config)
    await flushPromises()
    const checkbox = wrapper.find('[data-testid="ripping-paused"]')
    expect(checkbox.exists()).toBe(true)
    await checkbox.setValue(true)
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    const patchCall = fetchMock.mock.calls.find((c) => c[1]?.method === 'PATCH')
    const body = JSON.parse(patchCall![1].body as string)
    expect(body.ripping_paused).toBe(true)
  })

  it('loads existing metadata_provider and ripping_paused from GET', async () => {
    const loaded = { ...baseConfig, metadata_provider: 'omdb', ripping_paused: true }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(loaded)))
    const wrapper = mount(Config)
    await flushPromises()
    const select = wrapper.find('[data-testid="metadata-provider"]')
    expect((select.element as HTMLSelectElement).value).toBe('omdb')
    const paused = wrapper.find('[data-testid="ripping-paused"]')
    expect((paused.element as HTMLInputElement).checked).toBe(true)
  })

  it('does not render the retention or legacy-apprise controls', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(baseConfig)))
    const wrapper = mount(Config)
    await flushPromises()
    expect(wrapper.find('[data-testid="retention"]').exists()).toBe(false)
    expect(wrapper.find('textarea').exists()).toBe(false)
  })
})

describe('Config.vue drive scanner tunables', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    localStorage.setItem('arm_token', 'aaa.bbb.ccc')
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders both tunables from the config', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(baseConfig)))
    const wrapper = mount(Config)
    await flushPromises()
    expect(
      (wrapper.find('[data-testid="drive-scan-interval"]').element as HTMLInputElement).value,
    ).toBe('30')
    expect(
      (wrapper.find('[data-testid="drive-prune-days"]').element as HTMLInputElement).value,
    ).toBe('7')
  })

  it('sends the edited numbers in the PATCH body', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(baseConfig))
      .mockResolvedValueOnce(jsonResponse({ ...baseConfig, drive_scan_interval_seconds: 15 }))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(Config)
    await flushPromises()
    await wrapper.find('[data-testid="drive-scan-interval"]').setValue('15')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    const [, init] = fetchMock.mock.calls[1] as [string, RequestInit]
    const body = JSON.parse(init.body as string) as Record<string, unknown>
    expect(body.drive_scan_interval_seconds).toBe(15)
    expect(body.drive_detected_prune_days).toBe(7)
  })

  it('shows the backend detail when a value is rejected', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(baseConfig))
      .mockResolvedValueOnce(
        jsonResponse({ detail: 'drive_scan_interval_seconds must be >= 1' }, 400),
      )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(Config)
    await flushPromises()
    await wrapper.find('[data-testid="drive-scan-interval"]').setValue('0')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('.error').text()).toContain('must be >= 1')
  })
})
