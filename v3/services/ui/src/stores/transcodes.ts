import { defineStore } from 'pinia'
import { api } from '../api/client'
import { wsClient, type WSEnvelope } from '../api/ws'
import type {
  TranscodeProgressPayload,
  TranscodeSessionEventPayload,
  TranscodeTaskEventPayload,
  TranscodeTaskStatus,
  TranscodeTaskView,
} from '../api/types'

interface TranscodesState {
  tasks: TranscodeTaskView[]
  loading: boolean
  error: string | null
  // Live progress shadow keyed by task_id; merged into the rendered row's
  // progress_pct without writing back to `tasks` so list re-fetches don't
  // clobber an in-flight tick.
  liveProgress: Record<string, { progress_pct: number; current_pass: string | null }>
  // Subscription handles, keyed by `task_id`; used to unsubscribe when a
  // task transitions to terminal.
  _progressUnsubs: Record<string, () => void>
  _eventsUnsub: (() => void) | null
}

export const useTranscodesStore = defineStore('transcodes', {
  state: (): TranscodesState => ({
    tasks: [],
    loading: false,
    error: null,
    liveProgress: {},
    _progressUnsubs: {},
    _eventsUnsub: null,
  }),
  actions: {
    async fetchAll(filters?: {
      status?: TranscodeTaskStatus
      sessionApplicationId?: string
    }): Promise<void> {
      this.loading = true
      try {
        const params = new URLSearchParams()
        if (filters?.status) params.set('status', filters.status)
        if (filters?.sessionApplicationId)
          params.set('session_application_id', filters.sessionApplicationId)
        const qs = params.toString()
        this.tasks = await api.get<TranscodeTaskView[]>(`/api/transcodes${qs ? `?${qs}` : ''}`)
        this.error = null
        this.reconcileSubscriptions()
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      } finally {
        this.loading = false
      }
    },
    async cancel(id: string): Promise<void> {
      await api.del(`/api/transcodes/${id}`)
      // Cancel = delete: backend removed the row (synchronously for
      // QUEUED/terminal, async for IN_PROGRESS via cancel_running's tail).
      // Drop locally now so the UI updates immediately; the `task.deleted`
      // WS event reconciles for tabs that didn't initiate the action.
      this._dropTask(id)
    },
    _dropTask(id: string): void {
      this.tasks = this.tasks.filter((t) => t.id !== id)
      const unsub = this._progressUnsubs[id]
      if (unsub !== undefined) {
        unsub()
        delete this._progressUnsubs[id]
      }
      delete this.liveProgress[id]
    },
    startWS(): void {
      wsClient.start()
      if (this._eventsUnsub === null) {
        this._eventsUnsub = wsClient.subscribe('transcode.events', this.onEvent)
      }
      this.reconcileSubscriptions()
    },
    stopWS(): void {
      if (this._eventsUnsub !== null) {
        this._eventsUnsub()
        this._eventsUnsub = null
      }
      for (const id of Object.keys(this._progressUnsubs)) {
        this._progressUnsubs[id]()
      }
      this._progressUnsubs = {}
      this.liveProgress = {}
    },
    reconcileSubscriptions(): void {
      const inProgressIds = new Set(
        this.tasks.filter((t) => t.status === 'in_progress').map((t) => t.id),
      )
      for (const id of Object.keys(this._progressUnsubs)) {
        if (!inProgressIds.has(id)) {
          this._progressUnsubs[id]()
          delete this._progressUnsubs[id]
          delete this.liveProgress[id]
        }
      }
      for (const id of inProgressIds) {
        if (!(id in this._progressUnsubs)) {
          this._progressUnsubs[id] = wsClient.subscribe(`transcode.progress.${id}`, this.onProgress)
        }
      }
    },
    onProgress(env: WSEnvelope): void {
      const payload = env.payload as unknown as TranscodeProgressPayload
      this.liveProgress[payload.task_id] = {
        progress_pct: payload.progress_pct,
        current_pass: payload.current_pass,
      }
    },
    onEvent(env: WSEnvelope): void {
      switch (env.event_type) {
        case 'task.started': {
          const p = env.payload as unknown as TranscodeTaskEventPayload
          const task = this.tasks.find((t) => t.id === p.task_id)
          if (task !== undefined) {
            task.status = 'in_progress'
            this.reconcileSubscriptions()
          }
          break
        }
        case 'task.completed': {
          const p = env.payload as unknown as TranscodeTaskEventPayload
          const task = this.tasks.find((t) => t.id === p.task_id)
          if (task !== undefined) {
            task.status = 'done'
            task.progress_pct = 100
            if (p.output_path) task.output_path = p.output_path
            this.reconcileSubscriptions()
          }
          break
        }
        case 'task.failed': {
          const p = env.payload as unknown as TranscodeTaskEventPayload
          const task = this.tasks.find((t) => t.id === p.task_id)
          if (task !== undefined) {
            task.status = 'failed'
            if (p.last_error) task.last_error = p.last_error
            this.reconcileSubscriptions()
          }
          break
        }
        case 'task.deleted': {
          const p = env.payload as unknown as TranscodeTaskEventPayload
          this._dropTask(p.task_id)
          break
        }
        case 'session.started':
        case 'session.completed':
        case 'session.partial':
        case 'session.failed': {
          // Session-application events are consumed by other stores
          // (e.g. JobDetail's sessionApplications panel). No-op here.
          const _p = env.payload as unknown as TranscodeSessionEventPayload
          void _p
          break
        }
      }
    },
  },
})
