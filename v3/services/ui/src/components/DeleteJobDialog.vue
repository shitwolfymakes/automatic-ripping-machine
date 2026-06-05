<script setup lang="ts">
import { ref } from 'vue'
import { ApiError } from '../api/client'
import { useJobsStore } from '../stores/jobs'
import type { JobView } from '../api/types'

const props = defineProps<{ job: JobView }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'deleted', jobId: string): void
}>()

const jobs = useJobsStore()
const deleteRaw = ref(false)
const submitting = ref(false)
const error = ref<string | null>(null)

async function confirm(): Promise<void> {
  submitting.value = true
  error.value = null
  try {
    await jobs.deleteJob(props.job.id, { deleteRaw: deleteRaw.value })
    emit('deleted', props.job.id)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Delete failed'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="card" style="max-width: 560px; margin-top: 16px">
    <h3 style="margin-top: 0">Delete this job?</h3>
    <p v-if="error" class="error">{{ error }}</p>
    <p>
      The job <code>{{ job.id.slice(0, 12) }}…</code> will be permanently removed from the database
      along with its tracks, fingerprints, and any session applications. This can't be undone.
    </p>
    <div class="row" style="margin-bottom: 12px">
      <label class="row" style="gap: 6px">
        <input
          v-model="deleteRaw"
          type="checkbox"
          data-testid="delete-job-delete-raw"
          :disabled="submitting"
        />
        Also delete raw rip files at <code>/raw/{{ job.id }}/</code>
      </label>
    </div>
    <div class="row" style="gap: 8px">
      <button
        :disabled="submitting"
        data-testid="delete-job-confirm"
        type="button"
        @click="confirm"
      >
        {{ submitting ? 'Deleting…' : 'Delete job' }}
      </button>
      <button class="secondary" :disabled="submitting" type="button" @click="emit('close')">
        Cancel
      </button>
    </div>
  </div>
</template>
