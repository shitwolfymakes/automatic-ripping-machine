<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api, ApiError } from '../api/client'
import { useTranscodesStore } from '../stores/transcodes'
import type {
  DiagnosticsResponse,
  DriveView,
  JobStatus,
  JobView,
  TranscodeTaskStatus,
} from '../api/types'
import { isTerminalJobStatus } from '../utils/jobStatus'

const REFRESH_MS = Number(import.meta.env.VITE_DASHBOARD_REFRESH_MS ?? 5000)
const ACTIVE_JOB_STATUSES: JobStatus[] = ['created', 'awaiting_user_id', 'identified', 'ripping']
const ACTIVE_TASK_STATUSES: TranscodeTaskStatus[] = ['queued', 'in_progress']

const drives = ref<DriveView[]>([])
const jobs = ref<JobView[]>([])
const diagnostics = ref<DiagnosticsResponse | null>(null)
const error = ref<string | null>(null)
const loading = ref(true)
const transcodes = useTranscodesStore()

let timer: number | null = null

const activeJobs = computed(() => jobs.value.filter((j) => ACTIVE_JOB_STATUSES.includes(j.status)))
const recentTerminalJobs = computed(() =>
  jobs.value.filter((j) => isTerminalJobStatus(j.status)).slice(0, 5),
)
const activeTranscodes = computed(() =>
  transcodes.tasks.filter((t) => ACTIVE_TASK_STATUSES.includes(t.status)),
)
const onlineDriveCount = computed(() => drives.value.filter((d) => d.status !== 'offline').length)

function progressOf(taskId: string, fallback: number): number {
  return transcodes.liveProgress[taskId]?.progress_pct ?? fallback
}

function jobDriveLabel(driveId: string): string {
  const d = drives.value.find((x) => x.id === driveId)
  if (!d) return driveId.slice(0, 8) + '…'
  return d.display_name ?? d.hostname
}

async function refresh(): Promise<void> {
  try {
    const [d, j, diag] = await Promise.all([
      api.get<DriveView[]>('/api/drives'),
      api.get<JobView[]>('/api/jobs?limit=50'),
      api.get<DiagnosticsResponse>('/api/diagnostics'),
    ])
    drives.value = d
    jobs.value = j
    diagnostics.value = diag
    await transcodes.fetchAll()
    error.value = null
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Failed to refresh'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void refresh()
  transcodes.startWS()
  timer = window.setInterval(() => void refresh(), REFRESH_MS)
})

onUnmounted(() => {
  if (timer !== null) window.clearInterval(timer)
  transcodes.stopWS()
})
</script>

<template>
  <h2>Dashboard</h2>
  <p v-if="error" class="error">{{ error }}</p>
  <p v-if="loading" class="muted">Loading…</p>

  <div class="row" style="gap: 12px; flex-wrap: wrap; margin-bottom: 12px">
    <div class="card stat">
      <div class="muted">Drives online</div>
      <div class="stat-value">{{ onlineDriveCount }} / {{ drives.length }}</div>
    </div>
    <div class="card stat">
      <div class="muted">Active rips</div>
      <div class="stat-value">{{ activeJobs.length }}</div>
    </div>
    <div class="card stat">
      <div class="muted">Active transcodes</div>
      <div class="stat-value">{{ activeTranscodes.length }}</div>
    </div>
    <div class="spacer" />
    <RouterLink to="/jobs/manual">
      <button type="button">+ Manual rip</button>
    </RouterLink>
  </div>

  <div class="card">
    <h3 style="margin-top: 0">Active rips</h3>
    <p v-if="activeJobs.length === 0" class="muted">
      No rips in flight. Insert a disc — or click "+ Manual rip" — to start one.
    </p>
    <table v-else>
      <thead>
        <tr>
          <th>Job</th>
          <th>Title</th>
          <th>Disc</th>
          <th>Drive</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="j in activeJobs" :key="j.id">
          <td>
            <RouterLink :to="`/jobs/${j.id}`">{{ j.id.slice(0, 12) }}…</RouterLink>
          </td>
          <td>
            {{ j.title ?? '—' }}<span v-if="j.year"> ({{ j.year }})</span>
          </td>
          <td>{{ j.disc_type }}</td>
          <td>{{ jobDriveLabel(j.drive_id) }}</td>
          <td>
            <span class="badge">{{ j.status }}</span>
            <span
              v-if="j.resumed_from_crash"
              class="badge"
              style="margin-left: 4px"
              :data-testid="`resumed-badge-${j.id}`"
              >resumed from crash</span
            >
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <div v-if="activeTranscodes.length > 0" class="card">
    <h3 style="margin-top: 0">Active transcodes</h3>
    <table>
      <thead>
        <tr>
          <th>Task</th>
          <th>Status</th>
          <th>Progress</th>
          <th>Output</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="t in activeTranscodes" :key="t.id">
          <td>
            <code>{{ t.id.slice(-12) }}</code>
          </td>
          <td>
            <span class="badge">{{ t.status }}</span>
          </td>
          <td>
            <div v-if="t.status === 'in_progress'" class="progress-cell">
              <div class="progress-bar">
                <div
                  class="progress-fill"
                  :style="{ width: `${progressOf(t.id, t.progress_pct)}%` }"
                />
              </div>
              <span>{{ progressOf(t.id, t.progress_pct) }}%</span>
            </div>
            <span v-else class="muted">—</span>
          </td>
          <td>
            <code>{{ t.output_path ?? '—' }}</code>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="card">
    <h3 style="margin-top: 0">Drives</h3>
    <p v-if="drives.length === 0" class="muted">No drives registered yet.</p>
    <table v-else>
      <thead>
        <tr>
          <th>Hostname</th>
          <th>Device</th>
          <th>Display name</th>
          <th>Status</th>
          <th>Last seen</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="d in drives" :key="d.id">
          <td>{{ d.hostname }}</td>
          <td>
            <code>{{ d.device_path }}</code>
          </td>
          <td>{{ d.display_name ?? '—' }}</td>
          <td>
            <span class="badge">{{ d.status }}</span>
          </td>
          <td>{{ d.last_seen_at ?? '—' }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div v-if="diagnostics" class="card">
    <h3 style="margin-top: 0">Service health</h3>
    <table>
      <thead>
        <tr>
          <th>Service</th>
          <th>Log level</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in diagnostics.services" :key="s.name">
          <td>
            <code>{{ s.name }}</code>
          </td>
          <td>{{ s.log_level }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div v-if="recentTerminalJobs.length > 0" class="card">
    <h3 style="margin-top: 0">Recent jobs</h3>
    <table>
      <thead>
        <tr>
          <th>Job</th>
          <th>Title</th>
          <th>Disc</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="j in recentTerminalJobs" :key="j.id">
          <td>
            <RouterLink :to="`/jobs/${j.id}`">{{ j.id.slice(0, 12) }}…</RouterLink>
          </td>
          <td>
            {{ j.title ?? '—' }}<span v-if="j.year"> ({{ j.year }})</span>
          </td>
          <td>{{ j.disc_type }}</td>
          <td>
            <span class="badge">{{ j.status }}</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <p class="muted" style="font-size: 12px">Auto-refreshes every {{ REFRESH_MS / 1000 }} seconds.</p>
</template>

<style scoped>
.stat {
  min-width: 140px;
  padding: 12px 16px;
}
.stat-value {
  font-size: 28px;
  font-weight: 600;
  margin-top: 4px;
}
.progress-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}
.progress-bar {
  flex: 1;
  height: 8px;
  background: var(--c-border, #ddd);
  border-radius: 4px;
  overflow: hidden;
  min-width: 80px;
}
.progress-fill {
  height: 100%;
  background: var(--c-accent, #0aa);
  transition: width 200ms linear;
}
</style>
