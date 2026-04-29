<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, ApiError } from "../api/client";
import type { SessionView } from "../api/types";

const sessions = ref<SessionView[]>([]);
const error = ref<string | null>(null);

onMounted(async () => {
  try {
    sessions.value = await api.get<SessionView[]>("/api/sessions");
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Failed to load";
  }
});
</script>

<template>
  <h2>Sessions</h2>
  <p class="muted">Read-only in this build. Editing lands in a later phase.</p>
  <div class="card">
    <p v-if="error" class="error">{{ error }}</p>
    <table v-if="sessions.length">
      <thead>
        <tr>
          <th>Name</th>
          <th>Media</th>
          <th>Built-in</th>
          <th>Output template</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in sessions" :key="s.id">
          <td>{{ s.name }}</td>
          <td>{{ s.media_type }}</td>
          <td>{{ s.is_builtin ? "yes" : "no" }}</td>
          <td><code>{{ s.output_path_template }}</code></td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">No sessions found.</p>
  </div>
</template>
