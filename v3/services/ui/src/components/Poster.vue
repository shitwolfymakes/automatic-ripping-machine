<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { JobView } from '../api/types'

const props = withDefaults(
  defineProps<{
    job: JobView
    width?: number
  }>(),
  { width: 120 },
)

// User override wins over the auto-detected URL. If neither is set, or if
// the configured URL fails to load (404, broken host, CSP block), fall
// back to a per-disctype emoji placeholder so the layout doesn't shift.
const url = computed(() => props.job.poster_url_manual || props.job.poster_url || null)
const failed = ref(false)

watch(url, () => {
  failed.value = false
})

const placeholder = computed(() => {
  switch (props.job.disc_type) {
    case 'cd':
      return '💿'
    case 'bluray':
      return '🎞️'
    case 'data':
      return '💾'
    default:
      return '📀'
  }
})
</script>

<template>
  <div class="poster" :style="{ width: `${width}px`, height: `${Math.round(width * 1.5)}px` }">
    <img
      v-if="url && !failed"
      :src="url"
      :alt="job.title ?? 'poster'"
      :width="width"
      loading="lazy"
      @error="failed = true"
    />
    <span v-else class="placeholder">{{ placeholder }}</span>
  </div>
</template>

<style scoped>
.poster {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--c-border, #ddd);
  border-radius: 4px;
  overflow: hidden;
  flex-shrink: 0;
}
.poster img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.placeholder {
  font-size: 48px;
  opacity: 0.5;
  user-select: none;
}
</style>
