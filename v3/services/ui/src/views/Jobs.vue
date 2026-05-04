<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useJobsStore } from '../stores/jobs'
import { isTerminalJobStatus } from '../utils/jobStatus'

const store = useJobsStore()

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
    <RouterLink to="/jobs/manual">
      <button type="button">+ Manual rip</button>
    </RouterLink>
  </div>
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
