<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import DeleteAllJobsDialog from '../components/DeleteAllJobsDialog.vue'
import { useJobsStore } from '../stores/jobs'
import { isTerminalJobStatus } from '../utils/jobStatus'
import type { BulkDeleteJobsResponse } from '../api/types'

const store = useJobsStore()

const showDeleteAll = ref(false)
const deleteAllResult = ref<BulkDeleteJobsResponse | null>(null)
// API only deletes terminal jobs; hide the button when there's nothing
// it could act on (avoids a confirm dialog that would do nothing).
const hasTerminalJobs = computed(() => store.jobs.some((j) => isTerminalJobStatus(j.status)))

function onDeleteAll(result: BulkDeleteJobsResponse): void {
  deleteAllResult.value = result
  showDeleteAll.value = false
  void store.fetchJobs()
}

onMounted(() => {
  store.startPolling()
})
onUnmounted(() => {
  store.stopPolling()
})
</script>

<template>
  <div class="row" style="align-items: center; gap: 8px; margin-bottom: 8px">
    <h2 style="margin: 0">Jobs</h2>
    <span class="spacer" />
    <button
      v-if="hasTerminalJobs && !showDeleteAll"
      class="secondary"
      type="button"
      data-testid="delete-all-jobs"
      @click="showDeleteAll = true"
    >
      Delete all jobs…
    </button>
    <RouterLink to="/jobs/manual">
      <button type="button">+ Manual rip</button>
    </RouterLink>
  </div>

  <div
    v-if="deleteAllResult"
    class="card"
    style="border-color: var(--c-accent, #0aa)"
    data-testid="delete-all-result"
  >
    <h3 style="margin-top: 0">Bulk delete complete</h3>
    <p>
      Deleted <strong>{{ deleteAllResult.deleted_ids.length }}</strong> job(s).
      <span v-if="deleteAllResult.skipped_non_terminal.length > 0">
        Skipped <strong>{{ deleteAllResult.skipped_non_terminal.length }}</strong> still in flight
        (abandon them first to delete).
      </span>
    </p>
    <button class="secondary" type="button" @click="deleteAllResult = null">Dismiss</button>
  </div>

  <DeleteAllJobsDialog v-if="showDeleteAll" @close="showDeleteAll = false" @deleted="onDeleteAll" />

  <div class="card">
    <p v-if="store.error" class="error">{{ store.error }}</p>
    <p v-if="store.jobs.length === 0 && !store.loading" class="muted">
      No jobs yet. Insert a disc — or click "+ Manual rip" — to start one.
    </p>
    <table v-else>
      <thead>
        <tr>
          <th>ID</th>
          <th>Title</th>
          <th>Disc</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="j in store.jobs" :key="j.id">
          <td>
            <RouterLink :to="`/jobs/${j.id}`">{{ j.id.slice(0, 12) }}…</RouterLink>
          </td>
          <td>
            {{ j.title ?? '—' }}<span v-if="j.year"> ({{ j.year }})</span>
          </td>
          <td>{{ j.disc_type }}</td>
          <td>
            <span class="badge">{{ j.status }}</span>
            <span
              v-if="j.resumed_from_crash && !isTerminalJobStatus(j.status)"
              :data-testid="`resumed-badge-${j.id}`"
              class="badge"
              style="margin-left: 4px"
              >resumed from crash</span
            >
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <p class="muted" style="font-size: 12px">Auto-refreshes every 5 seconds.</p>
</template>

<script lang="ts">
import { RouterLink } from 'vue-router'
export default { components: { RouterLink } }
</script>
