// Canonical editable config keys the settings form renders. Mirrors the backend
// CONFIG_FIELD_META editable surface (verified equal). If the backend adds or
// removes an editable config key, update this list in the same change — the
// config-fields-guard test pins it so a field can't be silently dropped from the
// form again (settings audit §1.3 / structural fix 3).
import type { ConfigUpdateRequest } from '../api/types'

export const CONFIG_FORM_KEYS = [
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
] as const satisfies readonly (keyof ConfigUpdateRequest)[]
