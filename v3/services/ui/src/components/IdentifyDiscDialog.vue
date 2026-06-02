<script setup lang="ts">
import { ref } from 'vue'
import { ApiError } from '../api/client'
import { useJobsStore } from '../stores/jobs'
import type { JobView, ResolveResponse } from '../api/types'

const props = defineProps<{ job: JobView }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'identified', resp: ResolveResponse): void
}>()

const jobs = useJobsStore()
const title = ref<string>(props.job.title ?? '')
const year = ref<number | null>(props.job.year)
const submitting = ref(false)
const error = ref<string | null>(null)

async function submit(): Promise<void> {
  const trimmed = title.value.trim()
  if (!trimmed) return
  submitting.value = true
  error.value = null
  try {
    const resp = await jobs.resolve(props.job.id, {
      title: trimmed,
      year: year.value ?? null,
    })
    emit('identified', resp)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Identify failed'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="card" style="max-width: 560px; margin-top: 16px">
    <h3 style="margin-top: 0">Identify this disc</h3>
    <p v-if="error" class="error">{{ error }}</p>
    <p>
      The disc on drive <code>{{ job.drive_id }}</code> couldn't be identified automatically. Enter
      the title and (optionally) the year so ARM can proceed. Any session you've already applied
      will pick up the resolved title and queue its transcode tasks.
    </p>
    <form @submit.prevent="submit">
      <div class="row" style="margin-bottom: 12px; gap: 8px">
        <label style="flex: 2 1 0">
          Title
          <input
            v-model="title"
            type="text"
            required
            data-testid="identify-title"
            :disabled="submitting"
            style="width: 100%"
          />
        </label>
        <label style="flex: 1 1 0">
          Year
          <input
            v-model.number="year"
            type="number"
            min="1888"
            max="2100"
            data-testid="identify-year"
            :disabled="submitting"
            style="width: 100%"
          />
        </label>
      </div>
      <div class="row" style="gap: 8px">
        <button type="submit" :disabled="!title.trim() || submitting" data-testid="identify-submit">
          {{ submitting ? 'Saving…' : 'Identify' }}
        </button>
        <button type="button" class="secondary" :disabled="submitting" @click="emit('close')">
          Cancel
        </button>
      </div>
    </form>
  </div>
</template>
