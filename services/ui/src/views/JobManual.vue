<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { api, ApiError } from '../api/client'
import { useJobsStore } from '../stores/jobs'
import type { DriveView, SessionView } from '../api/types'

const router = useRouter()
const jobs = useJobsStore()

const drives = ref<DriveView[]>([])
const sessions = ref<SessionView[]>([])
const driveId = ref('')
const sessionId = ref<string | ''>('')
const error = ref<string | null>(null)
const submitting = ref(false)

const onlineDrives = computed(() => drives.value.filter((d) => d.status !== 'offline'))

onMounted(async () => {
  try {
    const [d, s] = await Promise.all([
      api.get<DriveView[]>('/api/drives'),
      api.get<SessionView[]>('/api/sessions'),
    ])
    drives.value = d
    sessions.value = s
    if (onlineDrives.value.length === 1) driveId.value = onlineDrives.value[0].id
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Failed to load drives'
  }
})

async function submit(): Promise<void> {
  if (!driveId.value) return
  submitting.value = true
  error.value = null
  try {
    await jobs.triggerManual({
      drive_id: driveId.value,
      session_id: sessionId.value || null,
    })
    await router.push('/dashboard')
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Trigger failed'
  } finally {
    submitting.value = false
  }
}

function driveLabel(d: DriveView): string {
  const name = d.display_name ?? d.hostname
  return `${name} (${d.device_path}) — ${d.status}`
}
</script>

<template>
  <h2>Manual rip</h2>
  <p class="muted">
    Kicks off a rip on a drive that already has a disc in the tray. The ripper runs the normal scan
    / identify / rip flow; if a session is selected, it auto-applies once the rip completes.
  </p>
  <p v-if="error" class="error">{{ error }}</p>
  <form class="card" style="max-width: 560px" @submit.prevent="submit">
    <div class="field">
      <label for="drive">Drive</label>
      <select id="drive" v-model="driveId" required>
        <option value="" disabled>Choose a drive…</option>
        <option v-for="d in drives" :key="d.id" :value="d.id">
          {{ driveLabel(d) }}
        </option>
      </select>
      <p v-if="!drives.length" class="muted" style="font-size: 12px; margin-top: 4px">
        No drives registered yet — start a ripper container first.
      </p>
    </div>

    <div class="field">
      <label for="session">Session (optional)</label>
      <select id="session" v-model="sessionId">
        <option value="">— none —</option>
        <option v-for="s in sessions" :key="s.id" :value="s.id">
          {{ s.name }}{{ s.is_builtin ? ' (built-in)' : '' }}
        </option>
      </select>
      <p class="muted" style="font-size: 12px; margin-top: 4px">
        Applied automatically when the rip completes. Leave blank to rip-only.
      </p>
    </div>

    <div class="row" style="gap: 8px">
      <button type="submit" :disabled="submitting || !driveId">
        {{ submitting ? 'Triggering…' : 'Start rip' }}
      </button>
      <RouterLink to="/jobs"><button class="secondary" type="button">Cancel</button></RouterLink>
    </div>
  </form>
</template>
