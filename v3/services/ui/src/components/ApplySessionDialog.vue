<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ApiError } from '../api/client'
import { useSessionsStore } from '../stores/sessions'
import type {
  ApplySessionResponse,
  CollisionInfo,
  CollisionReason,
  JobView,
  MediaType,
} from '../api/types'

const props = defineProps<{ job: JobView }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'applied', resp: ApplySessionResponse): void
}>()

const sessions = useSessionsStore()
const selected = ref<string>('')
const collisions = ref<CollisionInfo[]>([])
const error = ref<string | null>(null)
const submitting = ref(false)

function collisionLabel(reason: CollisionReason): string {
  if (reason === 'existing_task') return 'queued/done in DB'
  if (reason === 'on_disk') return 'exists on disk'
  return 'duplicate within this apply'
}

const hasDuplicateInRequest = computed(() =>
  collisions.value.some((c) => c.reason === 'duplicate_in_request'),
)

function discTypeToMediaType(dt: string): MediaType | null {
  if (dt === 'dvd' || dt === 'bluray') return 'movie'
  if (dt === 'cd') return 'music'
  if (dt === 'data') return 'data'
  return null
}

const candidateSessions = computed(() => {
  const mt = discTypeToMediaType(props.job.disc_type)
  return sessions.sessions.filter(
    (s) => mt === null || s.media_type === mt || s.media_type === 'tv',
  )
})

onMounted(async () => {
  await sessions.fetchAll()
})

async function applyOnce(overwrite: boolean): Promise<void> {
  submitting.value = true
  error.value = null
  try {
    const resp = await sessions.apply(props.job.id, { session_id: selected.value, overwrite })
    emit('applied', resp)
  } catch (e) {
    if (e instanceof ApiError && e.status === 409 && e.body && typeof e.body === 'object') {
      const detail = (e.body as { detail?: { collisions?: CollisionInfo[] } }).detail
      if (detail?.collisions) {
        collisions.value = detail.collisions
        return
      }
    }
    error.value = e instanceof ApiError ? e.message : 'Apply failed'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="card" style="max-width: 560px; margin-top: 16px">
    <h3 style="margin-top: 0">Apply session to job</h3>
    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="collisions.length === 0">
      <div class="field">
        <label>Session</label>
        <select v-model="selected">
          <option value="" disabled>Choose…</option>
          <option v-for="s in candidateSessions" :key="s.id" :value="s.id">
            {{ s.name }} ({{ s.media_type }})
          </option>
        </select>
      </div>
      <div class="row" style="gap: 8px">
        <button :disabled="!selected || submitting" @click="applyOnce(false)">
          {{ submitting ? 'Applying…' : 'Apply' }}
        </button>
        <button class="secondary" @click="emit('close')">Cancel</button>
      </div>
    </div>

    <div v-else>
      <p>This session can't be applied because of path collisions:</p>
      <ul>
        <li v-for="c in collisions" :key="c.output_path + c.reason">
          <code>{{ c.output_path }}</code>
          <span class="muted">({{ collisionLabel(c.reason) }})</span>
        </li>
      </ul>
      <p v-if="hasDuplicateInRequest" class="muted">
        Two or more tracks resolve to the same output path — the session's template doesn't
        differentiate per track. Pick a session whose template includes <code>{track}</code> (e.g.
        <em>Movie → Archive MKV</em>), or rip with a single-track preset.
        <strong>Overwrite</strong> won't help here.
      </p>
      <p v-else class="muted">
        Confirm <strong>Overwrite</strong> to queue anyway. The transcoder writes to
        <code>.arm-inprogress</code> first, so partial writes never replace the existing file.
      </p>
      <div class="row" style="gap: 8px">
        <button v-if="!hasDuplicateInRequest" :disabled="submitting" @click="applyOnce(true)">
          {{ submitting ? 'Applying…' : 'Overwrite' }}
        </button>
        <button class="secondary" @click="emit('close')">Cancel</button>
      </div>
    </div>
  </div>
</template>
