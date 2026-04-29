import { defineStore } from "pinia";
import { api } from "../api/client";
import type { TranscodeTaskStatus, TranscodeTaskView } from "../api/types";

interface TranscodesState {
  tasks: TranscodeTaskView[];
  loading: boolean;
  error: string | null;
}

export const useTranscodesStore = defineStore("transcodes", {
  state: (): TranscodesState => ({
    tasks: [],
    loading: false,
    error: null,
  }),
  actions: {
    async fetchAll(filters?: { status?: TranscodeTaskStatus; sessionApplicationId?: string }): Promise<void> {
      this.loading = true;
      try {
        const params = new URLSearchParams();
        if (filters?.status) params.set("status", filters.status);
        if (filters?.sessionApplicationId) params.set("session_application_id", filters.sessionApplicationId);
        const qs = params.toString();
        this.tasks = await api.get<TranscodeTaskView[]>(`/api/transcodes${qs ? `?${qs}` : ""}`);
        this.error = null;
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e);
      } finally {
        this.loading = false;
      }
    },
    async cancel(id: string): Promise<void> {
      await api.del(`/api/transcodes/${id}`);
      this.tasks = this.tasks.filter((t) => t.id !== id);
    },
  },
});
