<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { api, ApiError } from "../api/client";
import type { JobDetailView } from "../api/types";

const route = useRoute();
const detail = ref<JobDetailView | null>(null);
const error = ref<string | null>(null);

onMounted(async () => {
  try {
    const id = route.params.id as string;
    detail.value = await api.get<JobDetailView>(`/api/jobs/${id}`);
  } catch (e) {
    error.value =
      e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Failed to load";
  }
});
</script>

<template>
  <h2>Job detail</h2>
  <p v-if="error" class="error">{{ error }}</p>
  <div v-if="detail" class="card">
    <div class="row" style="gap: 24px; flex-wrap: wrap">
      <div>
        <div class="muted">Job ID</div>
        <div><code>{{ detail.job.id }}</code></div>
      </div>
      <div>
        <div class="muted">Status</div>
        <div><span class="badge">{{ detail.job.status }}</span></div>
      </div>
      <div>
        <div class="muted">Disc type</div>
        <div>{{ detail.job.disc_type }}</div>
      </div>
      <div>
        <div class="muted">Title</div>
        <div>{{ detail.job.title ?? "—" }}<span v-if="detail.job.year"> ({{ detail.job.year }})</span></div>
      </div>
    </div>
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
          <td><span class="badge">{{ t.status }}</span></td>
          <td>{{ t.output_path ?? "—" }}</td>
          <td>{{ t.size_bytes ? `${Math.round(t.size_bytes / 1024 / 1024)} MB` : "—" }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
