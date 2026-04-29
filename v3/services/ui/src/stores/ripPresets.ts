import { defineStore } from "pinia";
import { api } from "../api/client";
import type {
  MediaType,
  RipPresetCreateRequest,
  RipPresetUpdateRequest,
  RipPresetView,
} from "../api/types";

interface RipPresetsState {
  presets: RipPresetView[];
  loading: boolean;
  error: string | null;
}

export const useRipPresetsStore = defineStore("ripPresets", {
  state: (): RipPresetsState => ({
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
        this.presets = await api.get<RipPresetView[]>("/api/rip-presets");
        this.error = null;
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e);
      } finally {
        this.loading = false;
      }
    },
    async getById(id: string): Promise<RipPresetView> {
      return await api.get<RipPresetView>(`/api/rip-presets/${id}`);
    },
    async create(req: RipPresetCreateRequest): Promise<RipPresetView> {
      const created = await api.post<RipPresetView>("/api/rip-presets", req);
      this.presets = [...this.presets, created].sort((a, b) => a.name.localeCompare(b.name));
      return created;
    },
    async update(id: string, req: RipPresetUpdateRequest): Promise<RipPresetView> {
      const updated = await api.patch<RipPresetView>(`/api/rip-presets/${id}`, req);
      this.presets = this.presets.map((p) => (p.id === id ? updated : p));
      return updated;
    },
    async remove(id: string): Promise<void> {
      await api.del(`/api/rip-presets/${id}`);
      this.presets = this.presets.filter((p) => p.id !== id);
    },
  },
});
