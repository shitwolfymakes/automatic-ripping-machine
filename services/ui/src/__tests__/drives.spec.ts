import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import Drives from '../views/Drives.vue'

const drive = {
  id: 'drv_x',
  hostname: 'ripper-host',
  device_path: '/dev/sr0',
  display_name: null,
  status: 'online',
  last_seen_at: null,
  default_session_id: null,
}

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

describe('Drives.vue', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('arm_token', 'aaa.bbb.ccc')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders one option per session plus a none entry', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: RequestInfo) => {
        const url = typeof input === 'string' ? input : input.url
        if (url.endsWith('/api/drives')) return Promise.resolve(jsonResponse([drive]))
        if (url.endsWith('/api/sessions'))
          return Promise.resolve(jsonResponse([sessionA, sessionB]))
        return Promise.resolve(jsonResponse({}, 404))
      }),
    )

    const wrapper = mount(Drives)
    await flushPromises()

    const select = wrapper.find(`[data-testid="default-session-${drive.id}"]`)
    expect(select.exists()).toBe(true)
    const options = select.findAll('option')
    expect(options.length).toBe(3)
    expect(options[0].text()).toContain('none')
    expect(options[1].text()).toContain('Movie → Plex 1080p')
    expect(options[2].text()).toContain('TV → Jellyfin')
  })
})
