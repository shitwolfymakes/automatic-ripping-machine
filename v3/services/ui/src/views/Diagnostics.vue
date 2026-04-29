<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, ApiError } from "../api/client";
import type { DiagnosticsResponse } from "../api/types";

const data = ref<DiagnosticsResponse | null>(null);
const error = ref<string | null>(null);

onMounted(async () => {
  try {
    data.value = await api.get<DiagnosticsResponse>("/api/diagnostics");
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Failed to load";
  }
});
</script>

<template>
  <h2>Diagnostics</h2>
  <p class="muted">
    Read-only view of the backend's runtime knobs. Per-service log streaming
    and the bug-report zip endpoint will land in a later phase.
  </p>
  <div class="card">
    <p v-if="error" class="error">{{ error }}</p>
    <table v-if="data">
      <thead>
        <tr><th>Service</th><th>Log level</th></tr>
      </thead>
      <tbody>
        <tr v-for="s in data.services" :key="s.name">
          <td>{{ s.name }}</td>
          <td><span class="badge">{{ s.log_level }}</span></td>
        </tr>
      </tbody>
    </table>
    <p class="muted" style="font-size: 12px; margin-top: 8px">
      To change a level, set <code>ARM_LOG_LEVEL</code> in <code>.env</code> and
      restart the service.
    </p>
  </div>
</template>
