import { defineStore } from 'pinia'
import { api } from '../api/client'
import type { JobView } from '../api/types'

const POLL_INTERVAL_MS = Number(import.meta.env.VITE_JOBS_POLL_MS ?? 5000)

interface JobsState {
  jobs: JobView[]
  loading: boolean
  error: string | null
  _timer: number | null
}

export const useJobsStore = defineStore('jobs', {
  state: (): JobsState => ({
    jobs: [],
    loading: false,
    error: null,
    _timer: null,
  }),
  actions: {
    async fetchJobs(): Promise<void> {
      this.loading = true
      try {
        this.jobs = await api.get<JobView[]>('/api/jobs')
        this.error = null
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      } finally {
        this.loading = false
      }
    },
    startPolling(): void {
      if (this._timer !== null) return
      void this.fetchJobs()
      this._timer = window.setInterval(() => {
        void this.fetchJobs()
      }, POLL_INTERVAL_MS)
    },
    stopPolling(): void {
      if (this._timer !== null) {
        window.clearInterval(this._timer)
        this._timer = null
      }
    },
  },
})
