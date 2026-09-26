import type { GpuView } from '$lib/types/api.gen';
import { get, post, patch, del } from './client';

export function fetchGpus(): Promise<GpuView[]> {
	return get<GpuView[]>('/api/gpus');
}

export function updateGpu(gpuId: string, enabled: boolean): Promise<GpuView> {
	return patch<GpuView>(`/api/gpus/${gpuId}`, { enabled });
}

export function deleteGpu(gpuId: string): Promise<void> {
	return del(`/api/gpus/${gpuId}`);
}

// 202 on success; the backend answers 409 (with a detail string) when the
// device is claimed by a running transcode, isn't capable, or is already
// probing. ApiError.message carries that detail.
export function probeGpu(gpuId: string): Promise<void> {
	return post<void>(`/api/gpus/${gpuId}/probe`);
}

export function probeAllGpus(): Promise<void> {
	return post<void>('/api/gpus/probe');
}
