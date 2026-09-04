<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api, ApiError } from '../api/client'
import { listDrives, unenrollDrive } from '../api/drives'
import type { DriveUpdateRequest, DriveView, SessionView } from '../api/types'
import {
  DETACHED_LABEL,
  driveStatusLabel,
  identityLine,
  isRipping,
  partitionDrives,
} from '../utils/drives'

// The backend emits no drive events over the WebSocket; a slow poll keeps the
// current node / presence honest while the page is open (the scanner tick
// itself is 30 s by default).
const POLL_MS = 10_000

const drives = ref<DriveView[]>([])
const sessions = ref<SessionView[]>([])
const error = ref<string | null>(null)
const busy = ref<string | null>(null) // drive id with an action in flight
let timer: number | null = null

const parts = computed(() => partitionDrives(drives.value))

function describe(e: unknown, fallback: string): string {
  return e instanceof ApiError ? e.message : fallback
}

async function reload(): Promise<void> {
  drives.value = await listDrives()
}

onMounted(async () => {
  try {
    const [d, s] = await Promise.all([listDrives(), api.get<SessionView[]>('/api/sessions')])
    drives.value = d
    sessions.value = s
  } catch (e) {
    error.value = describe(e, 'Failed to load')
  }
  timer = window.setInterval(() => {
    reload().catch(() => {
      /* transient; the next tick retries */
    })
  }, POLL_MS)
})

onUnmounted(() => {
  if (timer !== null) window.clearInterval(timer)
})

async function run(
  driveId: string,
  action: () => Promise<unknown>,
  fallback: string,
): Promise<void> {
  error.value = null
  busy.value = driveId
  try {
    await action()
    await reload()
  } catch (e) {
    error.value = describe(e, fallback)
  } finally {
    busy.value = null
  }
}

function onUnenroll(d: DriveView): void {
  const name = d.display_name ?? d.model ?? d.hostname
  if (
    !window.confirm(
      `Unenroll ${name}? Its ripper container is stopped and removed; the drive will reappear on the next rescan as detected.`,
    )
  )
    return
  void run(d.id, () => unenrollDrive(d.id), 'Failed to unenroll drive')
}

async function onDefaultSessionChange(drive: DriveView, event: Event) {
  const target = event.target as HTMLSelectElement
  const newId = target.value === '' ? null : target.value
  const body: DriveUpdateRequest = { default_session_id: newId }
  try {
    const updated = await api.patch<DriveView>(`/api/drives/${drive.id}`, body)
    const idx = drives.value.findIndex((d) => d.id === updated.id)
    if (idx >= 0) drives.value[idx] = updated
  } catch (e) {
    error.value = describe(e, 'Failed to update drive')
    target.value = drive.default_session_id ?? ''
  }
}

function statusClass(d: DriveView): string[] {
  if (driveStatusLabel(d) === DETACHED_LABEL) return ['badge', 'detached']
  if (d.status === 'error') return ['badge', 'error']
  return ['badge']
}
</script>

<template>
  <h2>Drives</h2>
  <p v-if="error" class="error" data-testid="drives-error">{{ error }}</p>

  <div class="card">
    <h3 style="margin-top: 0">Enrolled</h3>
    <table v-if="parts.enrolled.length">
      <thead>
        <tr>
          <th>Drive</th>
          <th>Default session</th>
          <th>Status</th>
          <th>Last seen</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="d in parts.enrolled"
          :key="d.id"
          :data-testid="`enrolled-row-${d.id}`"
          :class="{ detached: statusClass(d).includes('detached') }"
        >
          <td :data-testid="`identity-${d.id}`">{{ identityLine(d) }}</td>
          <td>
            <select
              :value="d.default_session_id ?? ''"
              :data-testid="`default-session-${d.id}`"
              @change="onDefaultSessionChange(d, $event)"
            >
              <option value="">— none —</option>
              <option v-for="s in sessions" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
          </td>
          <td>
            <span :class="statusClass(d)" :data-testid="`status-${d.id}`">{{
              driveStatusLabel(d)
            }}</span>
          </td>
          <td>{{ d.last_seen_at ?? '—' }}</td>
          <td>
            <button
              class="secondary"
              :data-testid="`unenroll-${d.id}`"
              :disabled="isRipping(d) || busy === d.id"
              :title="isRipping(d) ? 'Cannot unenroll while ripping' : ''"
              @click="onUnenroll(d)"
            >
              Unenroll
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">No enrolled drives.</p>
  </div>
</template>
