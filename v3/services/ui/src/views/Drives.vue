<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, ApiError } from "../api/client";
import type { DriveView } from "../api/types";

const drives = ref<DriveView[]>([]);
const error = ref<string | null>(null);

onMounted(async () => {
  try {
    drives.value = await api.get<DriveView[]>("/api/drives");
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Failed to load";
  }
});
</script>

<template>
  <h2>Drives</h2>
  <div class="card">
    <p v-if="error" class="error">{{ error }}</p>
    <table v-if="drives.length">
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
          <td><code>{{ d.device_path }}</code></td>
          <td>{{ d.display_name ?? "—" }}</td>
          <td><span class="badge">{{ d.status }}</span></td>
          <td>{{ d.last_seen_at ?? "—" }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">No drives registered yet.</p>
  </div>
</template>
