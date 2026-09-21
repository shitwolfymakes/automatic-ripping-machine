<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, ApiError } from '../api/client'
import type { ConfigUpdateRequest, ConfigView } from '../api/types'
import { CONFIG_FORM_KEYS } from './configFormFields'

const cfg = ref<ConfigView | null>(null)
const error = ref<string | null>(null)
const saved = ref(false)
const submitting = ref(false)

const form = ref<ConfigUpdateRequest>({})

async function reload() {
  cfg.value = await api.get<ConfigView>('/api/config')
  const next: ConfigUpdateRequest = {}
  for (const k of CONFIG_FORM_KEYS) {
    // each key is a valid ConfigUpdateRequest field; copy its current value
    ;(next as Record<string, unknown>)[k] = (cfg.value as Record<string, unknown>)[k]
  }
  form.value = next
}

onMounted(async () => {
  try {
    await reload()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Failed to load'
  }
})

async function save() {
  saved.value = false
  error.value = null
  submitting.value = true
  try {
    cfg.value = await api.patch<ConfigView>('/api/config', form.value)
    saved.value = true
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Save failed'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <h2>Config</h2>
  <p v-if="error" class="error">{{ error }}</p>
  <form v-if="cfg" class="card" @submit.prevent="save">
    <div class="field">
      <label>TMDB API key</label>
      <input v-model="form.tmdb_api_key" />
    </div>
    <div class="field">
      <label>OMDB API key</label>
      <input v-model="form.omdb_api_key" />
    </div>
    <div class="field">
      <label>TVDB API key</label>
      <input v-model="form.tvdb_api_key" data-testid="tvdb-key" />
    </div>
    <div class="field">
      <label>MakeMKV key</label>
      <input
        v-model="form.makemkv_key"
        data-testid="makemkv-key"
        placeholder="T-… (perma-key or beta key)"
      />
      <p class="muted">
        Leave blank to use the monthly free beta key (scraped automatically) or a
        <code>MAKEMKV_KEY</code> env var. A key set here takes precedence.
      </p>
    </div>
    <div class="field">
      <label>MusicBrainz user agent</label>
      <input v-model="form.musicbrainz_user_agent" placeholder="my-arm/1.0 (you@example.com)" />
    </div>
    <div class="field">
      <label>Metadata provider</label>
      <select v-model="form.metadata_provider" data-testid="metadata-provider">
        <option value="tmdb">tmdb</option>
        <option value="omdb">omdb</option>
      </select>
      <!-- TODO(1.4): render options from /api/settings/schema enum_values once the form fetches the schema -->
    </div>
    <div class="row" style="margin-bottom: 12px">
      <label class="row" style="gap: 6px">
        <input type="checkbox" v-model="form.auto_rip_on_insert" data-testid="auto-rip-on-insert" />
        auto-rip on disc insert (uncheck to rip only via "+ Manual rip")
      </label>
    </div>
    <div class="row" style="margin-bottom: 12px">
      <label class="row" style="gap: 6px">
        <input type="checkbox" v-model="form.auto_transcode_on_idle" />
        auto-transcode on idle
      </label>
    </div>
    <div class="row" style="margin-bottom: 12px">
      <label class="row" style="gap: 6px">
        <input type="checkbox" v-model="form.block_on_miss" />
        block on identify miss (otherwise rip immediately as placeholder)
      </label>
    </div>
    <div class="row" style="margin-bottom: 12px">
      <label class="row" style="gap: 6px">
        <input type="checkbox" v-model="form.ripping_paused" data-testid="ripping-paused" />
        pause ripping (no new rips will start while checked)
      </label>
    </div>
    <div class="row" style="margin-bottom: 12px">
      <label class="row" style="gap: 6px">
        <input
          type="checkbox"
          v-model="form.notifications_enabled"
          data-testid="notifications-enabled"
        />
        Enable notifications (Apprise)
      </label>
    </div>
    <div class="row">
      <button :disabled="submitting" type="submit">{{ submitting ? 'Saving…' : 'Save' }}</button>
      <span v-if="saved" class="muted">Saved.</span>
    </div>
  </form>
</template>
