<script setup lang="ts">
import { ref } from 'vue'
import { ApiError } from '../api/client'
import { useJobsStore } from '../stores/jobs'
import type { BulkDeleteJobsResponse } from '../api/types'

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'deleted', result: BulkDeleteJobsResponse): void
}>()

const jobs = useJobsStore()
const deleteRaw = ref(false)
const submitting = ref(false)
const error = ref<string | null>(null)
// Type-the-phrase guard so a stray click can't wipe the lot.
const confirmText = ref('')
const phrase = 'delete all'

async function confirm(): Promise<void> {
  if (confirmText.value.trim().toLowerCase() !== phrase) return
  submitting.value = true
  error.value = null
  try {
    const result = await jobs.deleteAll({ deleteRaw: deleteRaw.value })
    emit('deleted', result)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Bulk delete failed'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="card" style="max-width: 560px; margin-top: 16px">
    <h3 style="margin-top: 0">Delete every job?</h3>
    <p v-if="error" class="error">{{ error }}</p>
    <p>
      All jobs in a terminal status (<code>ripped</code>, <code>ripped_partial</code>,
      <code>failed</code>, <code>abandoned</code>) will be permanently removed along with their
      tracks, fingerprints, and session applications. Jobs still in flight are left alone.
    </p>
    <div class="row" style="margin-bottom: 12px">
      <label class="row" style="gap: 6px">
        <input
          v-model="deleteRaw"
          type="checkbox"
          data-testid="delete-all-delete-raw"
          :disabled="submitting"
        />
        Also delete all matching <code>/raw/&lt;job_id&gt;/</code> directories on the rippers
      </label>
    </div>
    <div class="row" style="margin-bottom: 12px; gap: 6px; align-items: center">
      <label for="delete-all-confirm"
        >Type <code>{{ phrase }}</code> to confirm:</label
      >
      <input
        id="delete-all-confirm"
        v-model="confirmText"
        type="text"
        autocomplete="off"
        :disabled="submitting"
        data-testid="delete-all-confirm-text"
        style="min-width: 160px"
      />
    </div>
    <div class="row" style="gap: 8px">
      <button
        :disabled="submitting || confirmText.trim().toLowerCase() !== phrase"
        data-testid="delete-all-confirm"
        type="button"
        @click="confirm"
      >
        {{ submitting ? 'Deleting…' : 'Delete all jobs' }}
      </button>
      <button class="secondary" :disabled="submitting" type="button" @click="emit('close')">
        Cancel
      </button>
    </div>
  </div>
</template>
