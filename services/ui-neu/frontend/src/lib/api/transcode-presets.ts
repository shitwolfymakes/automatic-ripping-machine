import type {
	ImportParseResponse,
	MediaType,
	TranscodePresetView,
	TranscodePresetCreateRequest,
	TranscodePresetUpdateRequest
} from '$lib/types/api.gen';
import { apiFetch, get, post, patch, del } from './client';

export function fetchTranscodePresets(mediaType?: MediaType): Promise<TranscodePresetView[]> {
	const query = mediaType ? `?media_type=${mediaType}` : '';
	return get<TranscodePresetView[]>(`/api/transcode-presets${query}`);
}

export function fetchTranscodePreset(id: string): Promise<TranscodePresetView> {
	return get<TranscodePresetView>(`/api/transcode-presets/${id}`);
}

export function createTranscodePreset(body: TranscodePresetCreateRequest): Promise<TranscodePresetView> {
	return post<TranscodePresetView>('/api/transcode-presets', body);
}

export function updateTranscodePreset(id: string, body: TranscodePresetUpdateRequest): Promise<TranscodePresetView> {
	return patch<TranscodePresetView>(`/api/transcode-presets/${id}`, body);
}

export function deleteTranscodePreset(id: string): Promise<void> {
	return del(`/api/transcode-presets/${id}`);
}

// The body is the HandBrake export text itself (already JSON), sent as-is rather
// than JSON-encoded a second time.
export function parseHandbrakeImport(body: string): Promise<ImportParseResponse> {
	return apiFetch<ImportParseResponse>('/api/transcode-presets/import/parse', { method: 'POST', body });
}
