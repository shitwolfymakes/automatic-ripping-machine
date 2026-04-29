import { defineStore } from "pinia";
import { api } from "../api/client";
import type {
  MediaType,
  TranscodePresetCreateRequest,
  TranscodePresetUpdateRequest,
  TranscodePresetView,
} from "../api/types";

interface TranscodePresetsState {
  presets: TranscodePresetView[];
  loading: boolean;
  error: string | null;
}

export const useTranscodePresetsStore = defineStore("transcodePresets", {
  state: (): TranscodePresetsState => ({
    presets: [],
    loading: false,
    error: null,
  }),
  getters: {
    byMediaType: (state) => (mt: MediaType) => state.presets.filter((p) => p.media_type === mt),
  },
  actions: {
    async fetchAll(): Promise<void> {
      this.loading = true;
      try {
        this.presets = await api.get<TranscodePresetView[]>("/api/transcode-presets");
        this.error = null;
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e);
      } finally {
        this.loading = false;
      }
    },
    async getById(id: string): Promise<TranscodePresetView> {
      return await api.get<TranscodePresetView>(`/api/transcode-presets/${id}`);
    },
    async create(req: TranscodePresetCreateRequest): Promise<TranscodePresetView> {
      const created = await api.post<TranscodePresetView>("/api/transcode-presets", req);
      this.presets = [...this.presets, created].sort((a, b) => a.name.localeCompare(b.name));
      return created;
    },
    async update(id: string, req: TranscodePresetUpdateRequest): Promise<TranscodePresetView> {
      const updated = await api.patch<TranscodePresetView>(`/api/transcode-presets/${id}`, req);
      this.presets = this.presets.map((p) => (p.id === id ? updated : p));
      return updated;
    },
    async remove(id: string): Promise<void> {
      await api.del(`/api/transcode-presets/${id}`);
      this.presets = this.presets.filter((p) => p.id !== id);
    },
  },
});
