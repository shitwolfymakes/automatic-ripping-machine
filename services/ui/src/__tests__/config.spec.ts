import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Config from '../views/Config.vue'

const baseConfig = {
  tmdb_api_key: null,
  omdb_api_key: null,
  makemkv_key: null,
  musicbrainz_user_agent: null,
  auto_transcode_on_idle: false,
  block_on_miss: true,
  default_retention_policy: 'prune_after_session',
  notification_apprise_urls: [],
  notifications_enabled: false,
  updated_by_user_id: null,
  updated_at: null,
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

  it('renders backend 400 detail when invalid apprise URL is rejected', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(baseConfig))
      .mockResolvedValueOnce(jsonResponse({ detail: 'invalid apprise URL: discord://****' }, 400))
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(Config)
    await flushPromises()

    const textarea = wrapper.find('textarea')
    await textarea.setValue('discord://AAA/BBB')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    const errorEl = wrapper.find('p.error')
    expect(errorEl.exists()).toBe(true)
    expect(errorEl.text()).toContain('invalid apprise URL: discord://****')
    expect(wrapper.text()).not.toContain('Saved.')
  })
})
