<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api, ApiError } from '../api/client'
import {
  enrollDrive,
  ignoreDrive,
  listDrives,
  rescanDrives,
  unenrollDrive,
  unignoreDrive,
} from '../api/drives'
import type {
  ConfigView,
  DriveRescanResponse,
  DriveUpdateRequest,
  DriveView,
  SessionView,
} from '../api/types'
import {
  DETACHED_LABEL,
  driveStatusLabel,
  identityLine,
  isRipping,
  partitionDrives,
  serialLabel,
} from '../utils/drives'

// The backend emits no drive events over the WebSocket; a slow poll keeps the
// current node / presence honest while the page is open (the scanner tick
// itself is 30 s by default).
const POLL_MS = 10_000

const drives = ref<DriveView[]>([])
const sessions = ref<SessionView[]>([])
const error = ref<string | null>(null)
const busy = ref<string | null>(null) // drive id with an action in flight
const scanInterval = ref<string>('a minute')
const ignoredOpen = ref(false)
const scanning = ref(false)
const rescanSummary = ref<string | null>(null)
let timer: number | null = null

const parts = computed(() => partitionDrives(drives.value))

function describe(e: unknown, fallback: string): string {
  return e instanceof ApiError ? e.message : fallback
}

async function reload(): Promise<void> {
  drives.value = await listDrives()
}

// Best-effort: /api/config is admin-only; a guest sees the fallback wording.
async function loadScanInterval(): Promise<void> {
  try {
    const cfg = await api.get<ConfigView>('/api/config')
    if (typeof cfg.drive_scan_interval_seconds === 'number')
      scanInterval.value = `${cfg.drive_scan_interval_seconds}s`
  } catch {
    /* keep the fallback */
  }
}

onMounted(async () => {
  try {
    const [d, s] = await Promise.all([listDrives(), api.get<SessionView[]>('/api/sessions')])
    drives.value = d
    sessions.value = s
    void loadScanInterval()
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

function onEnroll(d: DriveView): void {
  void run(d.id, () => enrollDrive(d.id), 'Failed to enroll drive')
}
function onIgnore(d: DriveView): void {
  void run(d.id, () => ignoreDrive(d.id), 'Failed to ignore drive')
}
function onUnignore(d: DriveView): void {
  void run(d.id, () => unignoreDrive(d.id), 'Failed to un-ignore drive')
}

async function onRescan(): Promise<void> {
  error.value = null
  scanning.value = true
  rescanSummary.value = null
  try {
    const r: DriveRescanResponse = await rescanDrives()
    rescanSummary.value = `${r.detected} detected · ${r.enrolled} enrolled · ${r.ignored} ignored`
    await reload()
  } catch (e) {
    error.value = describe(e, 'Rescan failed')
  } finally {
    scanning.value = false
  }
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

  <div class="row" style="align-items: center; gap: 12px; margin-bottom: 12px">
    <button class="secondary" data-testid="rescan" :disabled="scanning" @click="onRescan">
      {{ scanning ? 'Scanning…' : 'Rescan' }}
    </button>
    <span v-if="rescanSummary" class="muted" data-testid="rescan-summary">{{ rescanSummary }}</span>
  </div>

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

  <div class="card">
    <h3 style="margin-top: 0">Detected</h3>
    <table v-if="parts.detected.length">
      <thead>
        <tr>
          <th>Model</th>
          <th>Serial</th>
          <th>Node</th>
          <th>Last seen</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="d in parts.detected" :key="d.id" :data-testid="`detected-row-${d.id}`">
          <td>{{ d.model ?? d.hostname }}</td>
          <td :class="{ warn: serialLabel(d).warn }" :data-testid="`serial-${d.id}`">
            {{ serialLabel(d).text }}
          </td>
          <td>
            <code>{{ d.device_path }}</code>
          </td>
          <td>{{ d.last_seen_at ?? '—' }}</td>
          <td>
            <button :data-testid="`enroll-${d.id}`" :disabled="busy === d.id" @click="onEnroll(d)">
              Enroll
            </button>
            <button
              class="secondary"
              :data-testid="`ignore-${d.id}`"
              :disabled="busy === d.id"
              @click="onIgnore(d)"
            >
              Ignore
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted" data-testid="detected-empty">
      No unenrolled drives. Plug one in — it appears here within {{ scanInterval }}.
    </p>
  </div>

  <div v-if="parts.ignored.length" class="card">
    <button class="secondary" data-testid="ignored-toggle" @click="ignoredOpen = !ignoredOpen">
      Ignored ({{ parts.ignored.length }}) {{ ignoredOpen ? '▾' : '▸' }}
    </button>
    <table v-if="ignoredOpen" style="margin-top: 12px">
      <thead>
        <tr>
          <th>Model</th>
          <th>Serial</th>
          <th>Node</th>
          <th>Last seen</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="d in parts.ignored" :key="d.id" :data-testid="`ignored-row-${d.id}`">
          <td>{{ d.model ?? d.hostname }}</td>
          <td :class="{ warn: serialLabel(d).warn }" :data-testid="`serial-${d.id}`">
            {{ serialLabel(d).text }}
          </td>
          <td>
            <code>{{ d.device_path }}</code>
          </td>
          <td>{{ d.last_seen_at ?? '—' }}</td>
          <td>
            <button
              class="secondary"
              :data-testid="`unignore-${d.id}`"
              :disabled="busy === d.id"
              @click="onUnignore(d)"
            >
              Un-ignore
            </button>
            <button :data-testid="`enroll-${d.id}`" :disabled="busy === d.id" @click="onEnroll(d)">
              Enroll
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
