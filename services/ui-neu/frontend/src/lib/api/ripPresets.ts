import type {
	RipPresetView,
	RipPresetCreateRequest,
	RipPresetUpdateRequest
} from '$lib/types/api.gen';
import { get, post, patch, del } from './client';

export function fetchRipPresets(): Promise<RipPresetView[]> {
	return get<RipPresetView[]>('/api/rip-presets');
}

export function fetchRipPreset(id: string): Promise<RipPresetView> {
	return get<RipPresetView>(`/api/rip-presets/${id}`);
}

export function createRipPreset(body: RipPresetCreateRequest): Promise<RipPresetView> {
	return post<RipPresetView>('/api/rip-presets', body);
}

export function updateRipPreset(id: string, body: RipPresetUpdateRequest): Promise<RipPresetView> {
	return patch<RipPresetView>(`/api/rip-presets/${id}`, body);
}

export function deleteRipPreset(id: string): Promise<void> {
	return del(`/api/rip-presets/${id}`);
}
