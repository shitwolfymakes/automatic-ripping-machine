<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '../api/client'
import { useTranscodePresetsStore } from '../stores/transcodePresets'
import type {
  ContainerFormat,
  HwPreference,
  MediaType,
  TranscodePresetView,
  TranscodeTool,
} from '../api/types'

const route = useRoute()
const router = useRouter()
const tcPresets = useTranscodePresetsStore()

const editing = computed(() => typeof route.params.id === 'string')
const editId = computed(() => (editing.value ? (route.params.id as string) : null))

const name = ref('')
const mediaType = ref<MediaType>('movie')
const tool = ref<TranscodeTool>('handbrake')
const presetRef = ref<string>('')
const container = ref<ContainerFormat>('mkv')
const hwPreference = ref<HwPreference | ''>('')
const extraArgs = ref<string>('')
const isBuiltin = ref(false)

const error = ref<string | null>(null)
const saving = ref(false)

onMounted(async () => {
  if (editing.value && editId.value) {
    try {
      const p: TranscodePresetView = await tcPresets.getById(editId.value)
      name.value = p.name
      mediaType.value = p.media_type
      tool.value = p.tool
      presetRef.value = p.preset_ref ?? ''
      container.value = p.container
      hwPreference.value = p.hw_preference ?? ''
      extraArgs.value = p.extra_args ?? ''
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
    if (editing.value && editId.value) {
      const payload = isBuiltin.value
        ? { name: name.value }
        : {
            name: name.value,
            tool: tool.value,
            preset_ref: presetRef.value || null,
            container: container.value,
            hw_preference: (hwPreference.value || null) as HwPreference | null,
            extra_args: extraArgs.value || null,
          }
      await tcPresets.update(editId.value, payload)
    } else {
      await tcPresets.create({
        name: name.value,
        media_type: mediaType.value,
        tool: tool.value,
        preset_ref: presetRef.value || null,
        container: container.value,
        hw_preference: (hwPreference.value || null) as HwPreference | null,
        extra_args: extraArgs.value || null,
      })
    }
    await router.push('/transcode-presets')
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Save failed'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <h2>{{ editing ? 'Edit transcode preset' : 'New transcode preset' }}</h2>
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
      <label>Tool</label>
      <select v-model="tool" :disabled="isBuiltin">
        <option value="handbrake">HandBrake</option>
        <option value="abcde">abcde</option>
        <option value="none">None (passthrough)</option>
      </select>
    </div>
    <div class="field">
      <label>Preset ref (HandBrake/abcde profile name)</label>
      <input v-model="presetRef" :disabled="isBuiltin" />
    </div>
    <div class="field">
      <label>Container</label>
      <select v-model="container" :disabled="isBuiltin">
        <option value="mkv">MKV</option>
        <option value="mp4">MP4</option>
        <option value="webm">WebM</option>
        <option value="flac">FLAC</option>
        <option value="mp3">MP3</option>
        <option value="ogg">OGG</option>
        <option value="iso">ISO</option>
        <option value="none">None</option>
      </select>
    </div>
    <div class="field">
      <label>Hardware preference</label>
      <select v-model="hwPreference" :disabled="isBuiltin">
        <option value="">(unset)</option>
        <option value="cpu_only">CPU only</option>
        <option value="any">Any</option>
      </select>
    </div>
    <div class="field">
      <label>Extra args</label>
      <input v-model="extraArgs" :disabled="isBuiltin" />
    </div>
    <div class="row" style="gap: 8px">
      <button type="submit" :disabled="saving || !name">{{ saving ? 'Saving…' : 'Save' }}</button>
      <RouterLink to="/transcode-presets"
        ><button class="secondary" type="button">Cancel</button></RouterLink
      >
    </div>
  </form>
</template>
