<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ApiError } from "../api/client";
import { useSessionsStore } from "../stores/sessions";
import type { ApplySessionResponse, CollisionInfo, JobView, MediaType } from "../api/types";

const props = defineProps<{ job: JobView }>();
const emit = defineEmits<{
  (e: "close"): void;
  (e: "applied", resp: ApplySessionResponse): void;
}>();

const sessions = useSessionsStore();
const selected = ref<string>("");
const collisions = ref<CollisionInfo[]>([]);
const error = ref<string | null>(null);
const submitting = ref(false);

function discTypeToMediaType(dt: string): MediaType | null {
  if (dt === "dvd" || dt === "bluray") return "movie";
  if (dt === "cd") return "music";
  if (dt === "data") return "data";
  return null;
}

const candidateSessions = computed(() => {
  const mt = discTypeToMediaType(props.job.disc_type);
  return sessions.sessions.filter((s) => mt === null || s.media_type === mt || s.media_type === "tv");
});

onMounted(async () => {
  await sessions.fetchAll();
});

async function applyOnce(overwrite: boolean): Promise<void> {
  submitting.value = true;
  error.value = null;
  try {
    const resp = await sessions.apply(props.job.id, { session_id: selected.value, overwrite });
    emit("applied", resp);
  } catch (e) {
    if (e instanceof ApiError && e.status === 409 && e.body && typeof e.body === "object") {
      const detail = (e.body as { detail?: { collisions?: CollisionInfo[] } }).detail;
      if (detail?.collisions) {
        collisions.value = detail.collisions;
        return;
      }
    }
    error.value = e instanceof ApiError ? e.message : "Apply failed";
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="card" style="max-width: 560px; margin-top: 16px">
    <h3 style="margin-top: 0">Apply session to job</h3>
    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="collisions.length === 0">
      <div class="field">
        <label>Session</label>
        <select v-model="selected">
          <option value="" disabled>Choose…</option>
          <option v-for="s in candidateSessions" :key="s.id" :value="s.id">
            {{ s.name }} ({{ s.media_type }})
          </option>
        </select>
      </div>
      <div class="row" style="gap: 8px">
        <button :disabled="!selected || submitting" @click="applyOnce(false)">
          {{ submitting ? "Applying…" : "Apply" }}
        </button>
        <button class="secondary" @click="emit('close')">Cancel</button>
      </div>
    </div>

    <div v-else>
      <p>This session would write paths that already exist:</p>
      <ul>
        <li v-for="c in collisions" :key="c.output_path">
          <code>{{ c.output_path }}</code>
          <span class="muted">
            ({{ c.existing_task_id ? "queued/done in DB" : "exists on disk" }})
          </span>
        </li>
      </ul>
      <p class="muted">
        Confirm <strong>Overwrite</strong> to queue anyway. The transcoder writes to
        <code>.arm-inprogress</code> first, so partial writes never replace the existing file.
      </p>
      <div class="row" style="gap: 8px">
        <button :disabled="submitting" @click="applyOnce(true)">
          {{ submitting ? "Applying…" : "Overwrite" }}
        </button>
        <button class="secondary" @click="emit('close')">Cancel</button>
      </div>
    </div>
  </div>
</template>
