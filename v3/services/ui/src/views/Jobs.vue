<script setup lang="ts">
import { onMounted, onUnmounted } from "vue";
import { useJobsStore } from "../stores/jobs";

const store = useJobsStore();

onMounted(() => {
  store.startPolling();
});
onUnmounted(() => {
  store.stopPolling();
});
</script>

<template>
  <h2>Jobs</h2>
  <div class="card">
    <p v-if="store.error" class="error">{{ store.error }}</p>
    <p v-if="store.jobs.length === 0 && !store.loading" class="muted">
      No jobs yet. Insert a disc to start one.
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
          <td><RouterLink :to="`/jobs/${j.id}`">{{ j.id.slice(0, 12) }}…</RouterLink></td>
          <td>{{ j.title ?? "—" }}<span v-if="j.year"> ({{ j.year }})</span></td>
          <td>{{ j.disc_type }}</td>
          <td><span class="badge">{{ j.status }}</span></td>
        </tr>
      </tbody>
    </table>
  </div>
  <p class="muted" style="font-size: 12px">Auto-refreshes every 5 seconds.</p>
</template>

<script lang="ts">
import { RouterLink } from "vue-router";
export default { components: { RouterLink } };
</script>
