import { defineStore } from "pinia";
import { api } from "../api/client";
import type {
  ApplySessionRequest,
  ApplySessionResponse,
  SessionCloneRequest,
  SessionCreateRequest,
  SessionUpdateRequest,
  SessionView,
  TemplatePreviewRequest,
  TemplatePreviewResponse,
} from "../api/types";

interface SessionsState {
  sessions: SessionView[];
  loading: boolean;
  error: string | null;
}

export const useSessionsStore = defineStore("sessions", {
  state: (): SessionsState => ({
    sessions: [],
    loading: false,
    error: null,
  }),
  actions: {
    async fetchAll(): Promise<void> {
      this.loading = true;
      try {
        this.sessions = await api.get<SessionView[]>("/api/sessions");
        this.error = null;
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e);
      } finally {
        this.loading = false;
      }
    },
    async getById(id: string): Promise<SessionView> {
      return await api.get<SessionView>(`/api/sessions/${id}`);
    },
    async create(req: SessionCreateRequest): Promise<SessionView> {
      const created = await api.post<SessionView>("/api/sessions", req);
      this.sessions = [...this.sessions, created].sort((a, b) => a.name.localeCompare(b.name));
      return created;
    },
    async update(id: string, req: SessionUpdateRequest): Promise<SessionView> {
      const updated = await api.patch<SessionView>(`/api/sessions/${id}`, req);
      this.sessions = this.sessions.map((s) => (s.id === id ? updated : s));
      return updated;
    },
    async remove(id: string): Promise<void> {
      await api.del(`/api/sessions/${id}`);
      this.sessions = this.sessions.filter((s) => s.id !== id);
    },
    async clone(id: string, req: SessionCloneRequest): Promise<SessionView> {
      const created = await api.post<SessionView>(`/api/sessions/${id}/clone`, req);
      this.sessions = [...this.sessions, created].sort((a, b) => a.name.localeCompare(b.name));
      return created;
    },
    async previewTemplate(req: TemplatePreviewRequest): Promise<TemplatePreviewResponse> {
      return await api.post<TemplatePreviewResponse>("/api/sessions/preview", req);
    },
    async apply(jobId: string, req: ApplySessionRequest): Promise<ApplySessionResponse> {
      return await api.post<ApplySessionResponse>(`/api/jobs/${jobId}/transcode`, req);
    },
  },
});
