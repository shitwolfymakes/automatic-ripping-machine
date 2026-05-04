<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, ApiError } from '../api/client'
import AbandonJobDialog from '../components/AbandonJobDialog.vue'
import ApplySessionDialog from '../components/ApplySessionDialog.vue'
import JobLogsCard from '../components/JobLogsCard.vue'
import { useTranscodesStore } from '../stores/transcodes'
import type { ApplySessionResponse, JobDetailView, JobStatus, JobView } from '../api/types'
import { isTerminalJobStatus } from '../utils/jobStatus'

const route = useRoute()
const detail = ref<JobDetailView | null>(null)
const error = ref<string | null>(null)
const showApply = ref(false)
const showAbandon = ref(false)
const lastApplied = ref<ApplySessionResponse | null>(null)
const transcodes = useTranscodesStore()

const APPLY_OK: JobStatus[] = ['identified', 'ripped', 'ripped_partial', 'awaiting_user_id']
const canApply = computed(() => detail.value !== null && APPLY_OK.includes(detail.value.job.status))
const canAbandon = computed(
  () => detail.value !== null && !isTerminalJobStatus(detail.value.job.status),
)

const jobTasks = computed(() => {
  if (detail.value === null) return []
  const trackIds = new Set(detail.value.tracks.map((t) => t.id))
  return transcodes.tasks.filter((t) => trackIds.has(t.source_track_id))
})

function progressOf(taskId: string, fallback: number): number {
  return transcodes.liveProgress[taskId]?.progress_pct ?? fallback
}

async function load(): Promise<void> {
  try {
    const id = route.params.id as string
    detail.value = await api.get<JobDetailView>(`/api/jobs/${id}`)
    await transcodes.fetchAll()
    transcodes.startWS()
  } catch (e) {
    error.value =
      e instanceof ApiError ? e.message : e instanceof Error ? e.message : 'Failed to load'
  }
}

async function cancelTask(id: string): Promise<void> {
  try {
    await transcodes.cancel(id)
  } catch (e) {
    error.value =
      e instanceof ApiError ? e.message : e instanceof Error ? e.message : 'Cancel failed'
  }
}

onMounted(load)
onUnmounted(() => {
  transcodes.stopWS()
})

function onApplied(resp: ApplySessionResponse): void {
  lastApplied.value = resp
  showApply.value = false
  void transcodes.fetchAll()
}

function onAbandoned(updated: JobView): void {
  if (detail.value) detail.value = { ...detail.value, job: updated }
  showAbandon.value = false
}
</script>

<template>
  <h2>Job detail</h2>
  <p v-if="error" class="error">{{ error }}</p>
  <div v-if="detail" class="card">
    <div class="row" style="gap: 24px; flex-wrap: wrap">
      <div>
        <div class="muted">Job ID</div>
        <div>
          <code>{{ detail.job.id }}</code>
        </div>
      </div>
      <div>
        <div class="muted">Status</div>
        <div>
          <span class="badge">{{ detail.job.status }}</span>
          <span
            v-if="detail.job.resumed_from_crash && !isTerminalJobStatus(detail.job.status)"
            data-testid="resumed-badge"
            class="badge"
            style="margin-left: 4px"
            >resumed from crash</span
          >
        </div>
      </div>
      <div>
        <div class="muted">Disc type</div>
        <div>{{ detail.job.disc_type }}</div>
      </div>
      <div>
        <div class="muted">Title</div>
        <div>
          {{ detail.job.title ?? '—' }}<span v-if="detail.job.year"> ({{ detail.job.year }})</span>
        </div>
      </div>
      <div class="spacer" />
      <button v-if="canApply && !showApply" @click="showApply = true">Apply session</button>
      <button
        v-if="canAbandon && !showAbandon"
        class="secondary"
        data-testid="abandon-job"
        @click="showAbandon = true"
      >
        Abandon job
      </button>
    </div>
  </div>

  <AbandonJobDialog
    v-if="detail && showAbandon"
    :job="detail.job"
    @close="showAbandon = false"
    @abandoned="onAbandoned"
  />

  <ApplySessionDialog
    v-if="detail && showApply"
    :job="detail.job"
    @close="showApply = false"
    @applied="onApplied"
  />

  <div v-if="lastApplied" class="card">
    <h3 style="margin-top: 0">
      Session queued
      <span v-if="lastApplied.idempotent" class="muted"
        >(already applied — same response returned)</span
      >
    </h3>
    <p>
      Application <code>{{ lastApplied.session_application.id }}</code> in status
      <strong>{{ lastApplied.session_application.status }}</strong>
      with {{ lastApplied.tasks.length }} task(s) queued.
    </p>
    <ul>
      <li v-for="t in lastApplied.tasks" :key="t.id">
        <code>{{ t.output_path }}</code> — {{ t.status }}
      </li>
    </ul>
  </div>

  <div v-if="detail && jobTasks.length > 0" class="card">
    <h3 style="margin-top: 0">Transcode tasks</h3>
    <table>
      <thead>
        <tr>
          <th>Task</th>
          <th>Status</th>
          <th>Progress</th>
          <th>Output</th>
          <th>Attempts</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="t in jobTasks" :key="t.id">
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
            <span v-else-if="t.status === 'done'">100%</span>
            <span v-else class="muted">—</span>
          </td>
          <td>
            <code>{{ t.output_path ?? '—' }}</code>
          </td>
          <td>{{ t.attempts }}</td>
          <td>
            <button
              v-if="t.status === 'queued' || t.status === 'in_progress'"
              @click="cancelTask(t.id)"
            >
              Cancel
            </button>
            <span v-else-if="t.last_error" class="muted" :title="t.last_error">error</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <div v-if="detail" class="card">
    <h3 style="margin-top: 0">Tracks</h3>
    <p v-if="detail.tracks.length === 0" class="muted">No tracks yet.</p>
    <table v-else>
      <thead>
        <tr>
          <th>#</th>
          <th>Kind</th>
          <th>Source</th>
          <th>Status</th>
          <th>Output</th>
          <th>Size</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="t in detail.tracks" :key="t.id">
          <td>{{ t.index }}</td>
          <td>{{ t.kind }}</td>
          <td>{{ t.source_ref }}</td>
          <td>
            <span class="badge">{{ t.status }}</span>
          </td>
          <td>{{ t.output_path ?? '—' }}</td>
          <td>{{ t.size_bytes ? `${Math.round(t.size_bytes / 1024 / 1024)} MB` : '—' }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <JobLogsCard v-if="detail" :job-id="detail.job.id" />
</template>

<style scoped>
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
