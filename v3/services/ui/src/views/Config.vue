<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, ApiError } from '../api/client'
import type { ConfigUpdateRequest, ConfigView } from '../api/types'

const cfg = ref<ConfigView | null>(null)
const error = ref<string | null>(null)
const saved = ref(false)
const submitting = ref(false)

const form = ref<ConfigUpdateRequest>({})
const appriseInput = ref<string>('')

async function reload() {
  cfg.value = await api.get<ConfigView>('/api/config')
  form.value = {
    tmdb_api_key: cfg.value.tmdb_api_key,
    omdb_api_key: cfg.value.omdb_api_key,
    musicbrainz_user_agent: cfg.value.musicbrainz_user_agent,
    auto_transcode_on_idle: cfg.value.auto_transcode_on_idle,
    block_on_miss: cfg.value.block_on_miss,
    default_retention_policy: cfg.value.default_retention_policy,
    notification_apprise_urls: [...cfg.value.notification_apprise_urls],
  }
  appriseInput.value = (cfg.value.notification_apprise_urls ?? []).join('\n')
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
    form.value.notification_apprise_urls = appriseInput.value
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)
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
      <label>MusicBrainz user agent</label>
      <input v-model="form.musicbrainz_user_agent" placeholder="my-arm/1.0 (you@example.com)" />
    </div>
    <div class="field">
      <label>Default retention policy</label>
      <select v-model="form.default_retention_policy">
        <option value="keep_forever">keep_forever</option>
        <option value="prune_after_session">prune_after_session</option>
        <option value="custom">custom</option>
      </select>
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
    <div class="field">
      <label>Apprise URLs (one per line)</label>
      <textarea v-model="appriseInput" rows="4" />
    </div>
    <div class="row">
      <button :disabled="submitting" type="submit">{{ submitting ? 'Saving…' : 'Save' }}</button>
      <span v-if="saved" class="muted">Saved.</span>
    </div>
  </form>
</template>
