<script setup lang="ts">
import { computed } from 'vue'
import type { TrackFilters } from '../api/types'

const props = defineProps<{ modelValue: TrackFilters }>()
const emit = defineEmits<(e: 'update:modelValue', v: TrackFilters) => void>()

function update<K extends keyof TrackFilters>(key: K, value: TrackFilters[K]): void {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}

const allowList = computed({
  get: () => (props.modelValue.title_indices ?? []).join(', '),
  set: (v: string) => {
    const parsed = v
      .split(/[ ,]+/)
      .map((s) => Number(s))
      .filter((n) => Number.isInteger(n) && n > 0)
    update('title_indices', parsed.length ? parsed : null)
  },
})

const blockList = computed({
  get: () => (props.modelValue.title_indices_exclude ?? []).join(', '),
  set: (v: string) => {
    const parsed = v
      .split(/[ ,]+/)
      .map((s) => Number(s))
      .filter((n) => Number.isInteger(n) && n > 0)
    update('title_indices_exclude', parsed.length ? parsed : null)
  },
})
</script>

<template>
  <div class="card" style="background: rgba(255, 255, 255, 0.02); margin-top: 8px">
    <h4 style="margin-top: 0">Custom track filters</h4>
    <p class="muted" style="font-size: 12px; margin-top: 0">
      All conditions are ANDed. Indices come from the rip log's MakeMKV title list.
    </p>
    <div class="field">
      <label>Min duration (seconds)</label>
      <input
        type="number"
        :value="modelValue.min_duration_seconds ?? ''"
        @input="
          (e) =>
            update(
              'min_duration_seconds',
              (e.target as HTMLInputElement).value
                ? Number((e.target as HTMLInputElement).value)
                : null,
            )
        "
      />
    </div>
    <div class="field">
      <label>Max duration (seconds)</label>
      <input
        type="number"
        :value="modelValue.max_duration_seconds ?? ''"
        @input="
          (e) =>
            update(
              'max_duration_seconds',
              (e.target as HTMLInputElement).value
                ? Number((e.target as HTMLInputElement).value)
                : null,
            )
        "
      />
    </div>
    <div class="field">
      <label>Title indices (allowlist)</label>
      <input v-model="allowList" placeholder="e.g. 1, 3, 5" />
    </div>
    <div class="field">
      <label>Title indices (blocklist)</label>
      <input v-model="blockList" placeholder="e.g. 2, 4" />
    </div>
  </div>
</template>
