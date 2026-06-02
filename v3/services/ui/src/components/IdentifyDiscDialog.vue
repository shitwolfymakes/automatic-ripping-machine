<script setup lang="ts">
import { computed, ref } from 'vue'
import { ApiError } from '../api/client'
import { useJobsStore } from '../stores/jobs'
import type { JobView, ResolveResponse } from '../api/types'

const props = defineProps<{ job: JobView }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'identified', resp: ResolveResponse): void
}>()

const jobs = useJobsStore()

// `isCd` switches the form body between the two-field (title + year)
// video shape and the structured-music shape. The music path template
// requires `{artist}`, `{album}`, and per-track `{track_title}` — none
// of which a title-only resolve can populate.
const isCd = computed(() => props.job.disc_type === 'cd')

// CD-only: per-track count comes from the preserved scan_result on the
// job's metadata_json (the identify endpoint preserves scan_result
// across the resolve flow). If the scan_result is somehow absent (e.g.
// older job, manual seed), we skip the per-track inputs and show a
// helper line; the resolve still succeeds but `track_title` will
// resolve empty when transcode tasks fan out.
const scanTrackCount = computed<number>(() => {
  const titles = (props.job.metadata_json?.scan_result as { titles?: unknown[] } | undefined)
    ?.titles
  return Array.isArray(titles) ? titles.length : 0
})

// Video / DVD / BD / data fields.
const title = ref<string>(props.job.title ?? '')
const year = ref<number | null>(props.job.year)

// CD fields.
const album = ref<string>(props.job.title ?? '')
const artist = ref<string>('')
const trackTitles = ref<string[]>(Array.from({ length: scanTrackCount.value }, () => ''))

const submitting = ref(false)
const error = ref<string | null>(null)

const canSubmit = computed<boolean>(() => {
  if (submitting.value) return false
  if (isCd.value) {
    return album.value.trim().length > 0 && artist.value.trim().length > 0
  }
  return title.value.trim().length > 0
})

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  submitting.value = true
  error.value = null
  try {
    const payload = isCd.value
      ? {
          title: album.value.trim(),
          year: year.value ?? null,
          metadata: {
            artist: artist.value.trim(),
            album: album.value.trim(),
            tracks: trackTitles.value.map((t) => ({ title: t.trim() })),
          },
        }
      : {
          title: title.value.trim(),
          year: year.value ?? null,
        }
    const resp = await jobs.resolve(props.job.id, payload)
    emit('identified', resp)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Identify failed'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="card" style="max-width: 560px; margin-top: 16px">
    <h3 style="margin-top: 0">Identify this disc</h3>
    <p v-if="error" class="error">{{ error }}</p>
    <p>
      The disc on drive <code>{{ job.drive_id }}</code> couldn't be identified automatically. Fill
      in the details so ARM can proceed. Any session you've already applied will pick up the
      resolved metadata and queue its transcode tasks.
    </p>
    <form @submit.prevent="submit">
      <template v-if="isCd">
        <div class="row" style="margin-bottom: 12px; gap: 8px">
          <label style="flex: 2 1 0">
            Album
            <input
              v-model="album"
              type="text"
              required
              data-testid="identify-album"
              :disabled="submitting"
              style="width: 100%"
            />
          </label>
          <label style="flex: 1 1 0">
            Year
            <input
              v-model.number="year"
              type="number"
              min="1888"
              max="2100"
              data-testid="identify-year"
              :disabled="submitting"
              style="width: 100%"
            />
          </label>
        </div>
        <div class="row" style="margin-bottom: 12px">
          <label style="flex: 1 1 0">
            Artist
            <input
              v-model="artist"
              type="text"
              required
              data-testid="identify-artist"
              :disabled="submitting"
              style="width: 100%"
            />
          </label>
        </div>
        <div v-if="scanTrackCount > 0" style="margin-bottom: 12px">
          <div class="muted" style="margin-bottom: 4px">Track titles</div>
          <div
            v-for="(_t, idx) in trackTitles"
            :key="idx"
            class="row"
            style="margin-bottom: 4px; gap: 8px; align-items: center"
          >
            <span class="muted" style="width: 32px; text-align: right">{{
              String(idx + 1).padStart(2, '0')
            }}</span>
            <input
              v-model="trackTitles[idx]"
              type="text"
              :data-testid="`identify-track-${idx + 1}`"
              :disabled="submitting"
              style="flex: 1"
            />
          </div>
        </div>
        <p v-else class="muted" style="margin-bottom: 12px">
          Track count couldn't be determined from the scan; transcoded filenames will fall back to
          generic names.
        </p>
      </template>
      <template v-else>
        <div class="row" style="margin-bottom: 12px; gap: 8px">
          <label style="flex: 2 1 0">
            Title
            <input
              v-model="title"
              type="text"
              required
              data-testid="identify-title"
              :disabled="submitting"
              style="width: 100%"
            />
          </label>
          <label style="flex: 1 1 0">
            Year
            <input
              v-model.number="year"
              type="number"
              min="1888"
              max="2100"
              data-testid="identify-year"
              :disabled="submitting"
              style="width: 100%"
            />
          </label>
        </div>
      </template>
      <div class="row" style="gap: 8px">
        <button type="submit" :disabled="!canSubmit" data-testid="identify-submit">
          {{ submitting ? 'Saving…' : 'Identify' }}
        </button>
        <button type="button" class="secondary" :disabled="submitting" @click="emit('close')">
          Cancel
        </button>
      </div>
    </form>
  </div>
</template>
