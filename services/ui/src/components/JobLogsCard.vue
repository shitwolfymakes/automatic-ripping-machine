<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import type { LogLine } from '../api/types'
import { downloadJobLogsZip, fetchJobLogs } from '../api/logs'
import { wsClient, type WSEnvelope } from '../api/ws'

const props = defineProps<{ jobId: string }>()

// Hard cap on how many lines we keep in the pane to bound memory if a
// session pushes thousands of lines. Earlier lines are still in the zip.
const MAX_PANE_LINES = 2000

const lines = ref<LogLine[]>([])
const error = ref<string | null>(null)
const downloading = ref(false)
let unsubscribe: (() => void) | null = null

function appendLine(line: LogLine): void {
  lines.value.push(line)
  if (lines.value.length > MAX_PANE_LINES) {
    lines.value = lines.value.slice(-MAX_PANE_LINES)
  }
}

function format(line: LogLine): string {
  // One-line summary; the full record is available via the zip download.
  const ts = line.ts.replace('T', ' ').replace(/\.\d+/, '').replace('+00:00', 'Z')
  const lvl = line.level.toUpperCase().padEnd(5)
  return `${ts} ${lvl} [${line.service}] ${line.msg}`
}

async function load(): Promise<void> {
  try {
    const seed = await fetchJobLogs(props.jobId, 200)
    lines.value = seed
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'failed to load logs'
  }
}

function onWSEvent(env: WSEnvelope): void {
  if (env.event_type !== 'log.line') return
  const payload = env.payload as Partial<LogLine> | undefined
  if (!payload || typeof payload.ts !== 'string') return
  appendLine(payload as LogLine)
}

async function onDownload(): Promise<void> {
  downloading.value = true
  try {
    await downloadJobLogsZip(props.jobId)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'download failed'
  } finally {
    downloading.value = false
  }
}

onMounted(async () => {
  await load()
  wsClient.start()
  unsubscribe = wsClient.subscribe(`logs.${props.jobId}`, onWSEvent)
})

onUnmounted(() => {
  if (unsubscribe !== null) {
    unsubscribe()
    unsubscribe = null
  }
})
</script>

<template>
  <div class="card">
    <div class="row" style="justify-content: space-between; align-items: center">
      <h3 style="margin: 0">Logs</h3>
      <button
        type="button"
        :disabled="downloading"
        data-testid="logs-download-zip"
        @click="onDownload"
      >
        {{ downloading ? 'Downloading…' : 'Download zip' }}
      </button>
    </div>
    <p class="muted">Live tail — earlier lines are available via the download button.</p>
    <p v-if="error" class="error">{{ error }}</p>
    <pre v-if="lines.length > 0" class="log-pane" data-testid="logs-pane">{{
      lines.map(format).join('\n')
    }}</pre>
    <p v-else class="muted">No log lines yet.</p>
  </div>
</template>

<style scoped>
.log-pane {
  background: #111;
  color: #ddd;
  padding: 12px;
  border-radius: 4px;
  max-height: 360px;
  overflow: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}
</style>
