<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import Poster from './Poster.vue'
import { formatEta } from '../stores/rips'
import type { JobView } from '../api/types'

const props = defineProps<{
  job: JobView
  driveLabel: string
  liveProgressPct: number | null
  liveEtaSeconds: number | null
}>()

const isRipping = computed(() => props.job.status === 'ripping')
const trackOf = computed(() => {
  const rp = props.job.rip_progress
  if (!rp || rp.current_track_index === null) return null
  return `${rp.current_track_index} / ${rp.tracks_total}`
})
const progressPct = computed(() => Math.max(0, Math.min(100, props.liveProgressPct ?? 0)))
const progressLabel = computed(() => `${progressPct.value.toFixed(1)}%`)
const etaLabel = computed(() => {
  if (props.liveEtaSeconds === null) return null
  return formatEta(props.liveEtaSeconds)
})
</script>

<template>
  <div class="job-card">
    <div class="poster-col">
      <Poster :job="job" :width="120" />
    </div>
    <div class="info-col">
      <div class="title-line">
        <span class="title">{{ job.title ?? 'Unidentified disc' }}</span>
        <span v-if="job.year" class="year">({{ job.year }})</span>
      </div>
      <div class="meta-line">
        <span class="meta-label">Disc:</span>
        <span>{{ job.disc_type }}</span>
      </div>
      <div class="meta-line">
        <span class="meta-label">Drive:</span>
        <span>{{ driveLabel }}</span>
      </div>
      <div class="badge-row">
        <span class="badge">{{ job.status }}</span>
        <span v-if="job.resumed_from_crash" class="badge" :data-testid="`resumed-badge-${job.id}`"
          >resumed from crash</span
        >
      </div>
      <div v-if="isRipping" class="progress-block" :data-testid="`rip-progress-${job.id}`">
        <div class="progress-meta">
          <span v-if="trackOf">Track {{ trackOf }}</span>
          <span v-else class="muted">queued for next track</span>
          <span class="progress-pct">{{ progressLabel }}</span>
          <span v-if="etaLabel" class="eta">ETA {{ etaLabel }}</span>
        </div>
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: `${progressPct}%` }" />
        </div>
      </div>
    </div>
    <div class="actions-col">
      <RouterLink :to="`/jobs/${job.id}`" class="open-link">Open →</RouterLink>
      <code class="job-id">{{ job.id.slice(-8) }}</code>
    </div>
  </div>
</template>

<style scoped>
.job-card {
  display: grid;
  grid-template-columns: 120px 1fr auto;
  gap: 16px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel-2);
}
.poster-col {
  display: flex;
  align-items: flex-start;
}
.info-col {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.title-line {
  font-size: 16px;
  font-weight: 600;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
}
.title {
  overflow: hidden;
  text-overflow: ellipsis;
}
.year {
  color: var(--muted);
  font-weight: 400;
}
.meta-line {
  display: flex;
  gap: 6px;
  font-size: 13px;
}
.meta-label {
  color: var(--muted);
}
.badge-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}
.progress-block {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.progress-meta {
  display: flex;
  gap: 12px;
  font-size: 13px;
  align-items: baseline;
}
.progress-pct {
  font-variant-numeric: tabular-nums;
}
.eta {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.progress-bar {
  height: 8px;
  background: var(--border);
  border-radius: 4px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: var(--accent);
  transition: width 200ms linear;
}
.actions-col {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}
.open-link {
  font-weight: 500;
  text-decoration: none;
}
.job-id {
  font-size: 11px;
  color: var(--muted);
}
.muted {
  color: var(--muted);
}
</style>
