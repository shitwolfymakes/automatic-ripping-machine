import type { GpuView } from '$lib/types/api.gen';
import { get, patch, del } from './client';

export function fetchGpus(): Promise<GpuView[]> {
	return get<GpuView[]>('/api/gpus');
}

export function updateGpu(gpuId: string, enabled: boolean): Promise<GpuView> {
	return patch<GpuView>(`/api/gpus/${gpuId}`, { enabled });
}

export function deleteGpu(gpuId: string): Promise<void> {
	return del(`/api/gpus/${gpuId}`);
}
