import { defineStore } from 'pinia'
import { wsClient, type WSEnvelope } from '../api/ws'
import type { RipperProgressPayload } from '../api/types'

// Live rip progress, keyed by job_id. The dashboard renders the bar from
// `liveProgress[job_id]?.progress_pct`. Backend publishes on
// `ripper.progress.{job_id}` with `{track_id, progress_pct}`; ETA is
// computed on the receiving side (matches v2's logfile-parsed approach).

interface RipBaseline {
  // Anchored on the first tick of a given track, used to compute pct/sec.
  trackId: string
  atMs: number
  atPct: number
}

interface RipLiveProgress {
  track_id: string
  progress_pct: number
  // Null until we've seen ≥1 follow-up tick for the same track and the
  // signal is past the masking threshold (see ETA_MIN_ELAPSED_MS /
  // ETA_MIN_DELTA). Resets to null when the track changes.
  eta_seconds: number | null
}

interface RipsState {
  liveProgress: Record<string, RipLiveProgress>
  // ETA baselines, kept separate from `liveProgress` so the rendered
  // value is a clean read for the template.
  _baseline: Record<string, RipBaseline>
  _progressUnsubs: Record<string, () => void>
}

// Mask early per-track samples — first tick has no rate yet, and the
// second tick can be misleading if the encoder stalls briefly. Match v2's
// "wait a bit before showing ETA" behaviour.
const ETA_MIN_ELAPSED_MS = 5_000
const ETA_MIN_DELTA = 0.5

export const useRipsStore = defineStore('rips', {
  state: (): RipsState => ({
    liveProgress: {},
    _baseline: {},
    _progressUnsubs: {},
  }),
  actions: {
    startWS(): void {
      wsClient.start()
    },
    stopWS(): void {
      for (const id of Object.keys(this._progressUnsubs)) {
        this._progressUnsubs[id]()
      }
      this._progressUnsubs = {}
      this.liveProgress = {}
      this._baseline = {}
    },
    reconcileSubscriptions(activeRippingJobIds: string[]): void {
      const wanted = new Set(activeRippingJobIds)
      for (const id of Object.keys(this._progressUnsubs)) {
        if (!wanted.has(id)) {
          this._progressUnsubs[id]()
          delete this._progressUnsubs[id]
          delete this.liveProgress[id]
          delete this._baseline[id]
        }
      }
      for (const id of wanted) {
        if (!(id in this._progressUnsubs)) {
          this._progressUnsubs[id] = wsClient.subscribe(`ripper.progress.${id}`, (env) =>
            this.onProgress(id, env),
          )
        }
      }
    },
    onProgress(jobId: string, env: WSEnvelope): void {
      const payload = env.payload as unknown as RipperProgressPayload
      const now = Date.now()
      const baseline = this._baseline[jobId]
      // First tick for this track (or track changed) → reset baseline,
      // ETA stays null until enough has accumulated.
      if (baseline === undefined || baseline.trackId !== payload.track_id) {
        this._baseline[jobId] = {
          trackId: payload.track_id,
          atMs: now,
          atPct: payload.progress_pct,
        }
        this.liveProgress[jobId] = {
          track_id: payload.track_id,
          progress_pct: payload.progress_pct,
          eta_seconds: null,
        }
        return
      }
      const elapsedMs = now - baseline.atMs
      const pctDelta = payload.progress_pct - baseline.atPct
      let eta: number | null = null
      if (elapsedMs > ETA_MIN_ELAPSED_MS && pctDelta > ETA_MIN_DELTA) {
        const pctPerMs = pctDelta / elapsedMs
        const remainingPct = Math.max(0, 100 - payload.progress_pct)
        eta = Math.round(remainingPct / pctPerMs / 1000)
      }
      this.liveProgress[jobId] = {
        track_id: payload.track_id,
        progress_pct: payload.progress_pct,
        eta_seconds: eta,
      }
    },
  },
})

export function formatEta(seconds: number): string {
  if (seconds < 60) return '< 1m'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}h ${m}m`
  if (m >= 5) return `${m}m`
  return `${m}m ${s}s`
}
