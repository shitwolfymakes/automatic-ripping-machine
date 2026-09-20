import { describe, it, expect } from 'vitest'
import { CONFIG_FORM_KEYS } from '../views/configFormFields'

// The editable config keys the form is expected to render. Mirrors the backend
// CONFIG_FIELD_META editable surface. If the backend changes its editable keys,
// update BOTH this list and CONFIG_FORM_KEYS in the same change.
const EXPECTED_EDITABLE = [
  'tmdb_api_key',
  'omdb_api_key',
  'tvdb_api_key',
  'makemkv_key',
  'musicbrainz_user_agent',
  'metadata_provider',
  'auto_transcode_on_idle',
  'auto_rip_on_insert',
  'block_on_miss',
  'ripping_paused',
  'notifications_enabled',
]
const FORBIDDEN = ['default_retention_policy', 'notification_apprise_urls']

describe('config form field guard', () => {
  it('binds exactly the expected editable config keys', () => {
    expect(new Set(CONFIG_FORM_KEYS)).toEqual(new Set(EXPECTED_EDITABLE))
  })
  it('does not bind the hidden/removed keys', () => {
    for (const k of FORBIDDEN) {
      expect(CONFIG_FORM_KEYS as readonly string[]).not.toContain(k)
    }
  })
})
