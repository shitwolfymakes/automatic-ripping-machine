import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { formatEta, useRipsStore } from '../stores/rips'
import { wsClient, type WSEnvelope } from '../api/ws'

function progressEnv(jobId: string, trackId: string, pct: number): WSEnvelope {
  return {
    op: 'event',
    event_id: `evt_${pct}`,
    event_type: 'ripper.progress',
    emitted_at: 'now',
    topic: `ripper.progress.${jobId}`,
    job_id: jobId,
    track_id: trackId,
    payload: { track_id: trackId, progress_pct: pct },
  }
}

describe('rips store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.setItem('arm_token', 'aaa.bbb.ccc')
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-05-05T00:00:00Z'))
  })

  afterEach(() => {
    wsClient.stop()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('first tick of a track sets progress and leaves ETA null', () => {
    const store = useRipsStore()
    store.onProgress('job_a', progressEnv('job_a', 'trk_1', 5))
    expect(store.liveProgress['job_a']).toEqual({
      track_id: 'trk_1',
      progress_pct: 5,
      eta_seconds: null,
    })
  })

  it('computes ETA once enough has elapsed and progressed', () => {
    const store = useRipsStore()
    store.onProgress('job_a', progressEnv('job_a', 'trk_1', 5))
    // Advance 10s and arrive at 25% — that's 20% in 10s → 2% per 1s →
    // 75% remaining → ETA ≈ 38s.
    vi.advanceTimersByTime(10_000)
    store.onProgress('job_a', progressEnv('job_a', 'trk_1', 25))
    expect(store.liveProgress['job_a'].progress_pct).toBe(25)
    expect(store.liveProgress['job_a'].eta_seconds).toBe(38)
  })

  it('keeps ETA null when the elapsed window is too short', () => {
    const store = useRipsStore()
    store.onProgress('job_a', progressEnv('job_a', 'trk_1', 5))
    // Only 2s of elapsed time — below the masking threshold.
    vi.advanceTimersByTime(2_000)
    store.onProgress('job_a', progressEnv('job_a', 'trk_1', 9))
    expect(store.liveProgress['job_a'].eta_seconds).toBeNull()
  })

  it('resets the ETA baseline when the track changes', () => {
    const store = useRipsStore()
    store.onProgress('job_a', progressEnv('job_a', 'trk_1', 5))
    vi.advanceTimersByTime(10_000)
    store.onProgress('job_a', progressEnv('job_a', 'trk_1', 50))
    // Track 1 has a defined ETA at this point.
    expect(store.liveProgress['job_a'].eta_seconds).not.toBeNull()
    // Switch to track 2: first tick on the new track → ETA blanks again.
    store.onProgress('job_a', progressEnv('job_a', 'trk_2', 0))
    expect(store.liveProgress['job_a']).toEqual({
      track_id: 'trk_2',
      progress_pct: 0,
      eta_seconds: null,
    })
  })

  it('reconcileSubscriptions drops state for jobs no longer ripping', () => {
    const store = useRipsStore()
    // Seed live state for a job that's about to leave the active set.
    store.onProgress('job_a', progressEnv('job_a', 'trk_1', 30))
    store._progressUnsubs['job_a'] = vi.fn() as unknown as () => void
    store.reconcileSubscriptions([])
    expect(store.liveProgress['job_a']).toBeUndefined()
    expect(store._progressUnsubs['job_a']).toBeUndefined()
  })
})

describe('formatEta', () => {
  it('returns "< 1m" for sub-minute', () => {
    expect(formatEta(45)).toBe('< 1m')
  })
  it('returns minutes+seconds for under 5 minutes', () => {
    expect(formatEta(150)).toBe('2m 30s')
  })
  it('returns whole minutes for 5+ minute ETAs', () => {
    expect(formatEta(720)).toBe('12m')
  })
  it('returns hours+minutes when over an hour', () => {
    expect(formatEta(4_350)).toBe('1h 12m')
  })
})
