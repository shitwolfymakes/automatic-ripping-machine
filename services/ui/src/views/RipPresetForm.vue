<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '../api/client'
import TrackFiltersEditor from '../components/TrackFiltersEditor.vue'
import { useRipPresetsStore } from '../stores/ripPresets'
import type {
  IdentificationMode,
  MediaType,
  OutputMode,
  RipPresetView,
  TrackFilters,
  TrackSelection,
} from '../api/types'

const route = useRoute()
const router = useRouter()
const ripPresets = useRipPresetsStore()

const editing = computed(() => typeof route.params.id === 'string')
const editId = computed(() => (editing.value ? (route.params.id as string) : null))

const name = ref('')
const mediaType = ref<MediaType>('movie')
const trackSelection = ref<TrackSelection>('main_feature')
const identificationMode = ref<IdentificationMode>('required')
const outputMode = ref<OutputMode>('tracks')
const filters = ref<TrackFilters>({})
const isBuiltin = ref(false)

const error = ref<string | null>(null)
const saving = ref(false)

onMounted(async () => {
  if (editing.value && editId.value) {
    try {
      const p: RipPresetView = await ripPresets.getById(editId.value)
      name.value = p.name
      mediaType.value = p.media_type
      trackSelection.value = p.track_selection
      identificationMode.value = p.identification_mode
      outputMode.value = p.output_mode
      filters.value = p.track_filters_json ?? {}
      isBuiltin.value = p.is_builtin
    } catch (e) {
      error.value = e instanceof ApiError ? e.message : 'Failed to load'
    }
  }
})

async function save(): Promise<void> {
  saving.value = true
  error.value = null
  try {
    const trackFilters =
      trackSelection.value === 'custom'
        ? Object.fromEntries(
            Object.entries(filters.value).filter(([, v]) => v !== null && v !== undefined),
          )
        : null
    if (editing.value && editId.value) {
      const payload = isBuiltin.value
        ? { name: name.value }
        : {
            name: name.value,
            track_selection: trackSelection.value,
            identification_mode: identificationMode.value,
            output_mode: outputMode.value,
            track_filters_json: trackFilters as TrackFilters | null,
          }
      await ripPresets.update(editId.value, payload)
    } else {
      await ripPresets.create({
        name: name.value,
        media_type: mediaType.value,
        track_selection: trackSelection.value,
        identification_mode: identificationMode.value,
        output_mode: outputMode.value,
        track_filters_json: trackFilters as TrackFilters | null,
      })
    }
    await router.push('/rip-presets')
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Save failed'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <h2>{{ editing ? 'Edit rip preset' : 'New rip preset' }}</h2>
  <p v-if="isBuiltin" class="muted">Built-in preset — only the name is editable.</p>
  <p v-if="error" class="error">{{ error }}</p>
  <form class="card" style="max-width: 720px" @submit.prevent="save">
    <div class="field">
      <label>Name</label>
      <input v-model="name" required />
    </div>
    <div class="field">
      <label>Media type</label>
      <select v-model="mediaType" :disabled="editing">
        <option value="movie">Movie</option>
        <option value="tv">TV</option>
        <option value="music">Music</option>
        <option value="data">Data</option>
        <option value="iso">ISO</option>
      </select>
    </div>
    <div class="field">
      <label>Track selection</label>
      <select v-model="trackSelection" :disabled="isBuiltin">
        <option value="main_feature">Main feature (longest ≥ 45 min)</option>
        <option value="all_tracks">All tracks (≥ 60 s)</option>
        <option value="archive">Archive (every track)</option>
        <option value="custom">Custom</option>
      </select>
    </div>
    <div class="field">
      <label>Identification mode</label>
      <select v-model="identificationMode" :disabled="isBuiltin">
        <option value="required">Required</option>
        <option value="skip">Skip</option>
        <option value="deferred_placeholder">Deferred placeholder</option>
      </select>
    </div>
    <div class="field">
      <label>Output mode</label>
      <select v-model="outputMode" :disabled="isBuiltin">
        <option value="tracks">Tracks</option>
        <option value="iso">ISO</option>
        <option value="data_copy">Data copy</option>
      </select>
    </div>
    <TrackFiltersEditor v-if="trackSelection === 'custom' && !isBuiltin" v-model="filters" />
    <div class="row" style="gap: 8px; margin-top: 12px">
      <button type="submit" :disabled="saving || !name">{{ saving ? 'Saving…' : 'Save' }}</button>
      <RouterLink to="/rip-presets"
        ><button class="secondary" type="button">Cancel</button></RouterLink
      >
    </div>
  </form>
</template>
