<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { api, ApiError } from "../api/client";
import ApplySessionDialog from "../components/ApplySessionDialog.vue";
import type { ApplySessionResponse, JobDetailView, JobStatus } from "../api/types";

const route = useRoute();
const detail = ref<JobDetailView | null>(null);
const error = ref<string | null>(null);
const showApply = ref(false);
const lastApplied = ref<ApplySessionResponse | null>(null);

const APPLY_OK: JobStatus[] = ["identified", "ripped", "ripped_partial", "awaiting_user_id"];
const canApply = computed(() => detail.value !== null && APPLY_OK.includes(detail.value.job.status));

async function load(): Promise<void> {
  try {
    const id = route.params.id as string;
    detail.value = await api.get<JobDetailView>(`/api/jobs/${id}`);
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Failed to load";
  }
}

onMounted(load);

function onApplied(resp: ApplySessionResponse): void {
  lastApplied.value = resp;
  showApply.value = false;
}
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
      <div class="spacer" />
      <button v-if="canApply && !showApply" @click="showApply = true">Apply session</button>
    </div>
  </div>

  <ApplySessionDialog
    v-if="detail && showApply"
    :job="detail.job"
    @close="showApply = false"
    @applied="onApplied"
  />

  <div v-if="lastApplied" class="card">
    <h3 style="margin-top: 0">
      Session queued
      <span v-if="lastApplied.idempotent" class="muted">(already applied — same response returned)</span>
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
