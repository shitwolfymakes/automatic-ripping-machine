import type {
	SessionView,
	SessionCreateRequest,
	SessionUpdateRequest,
	SessionCloneRequest,
	TemplatePreviewRequest,
	TemplatePreviewResponse
} from '$lib/types/api.gen';
import { get, post, patch, del } from './client';

export function fetchSessions(): Promise<SessionView[]> {
	return get<SessionView[]>('/api/sessions');
}

export function fetchSession(id: string): Promise<SessionView> {
	return get<SessionView>(`/api/sessions/${id}`);
}

export function createSession(body: SessionCreateRequest): Promise<SessionView> {
	return post<SessionView>('/api/sessions', body);
}

export function updateSession(id: string, body: SessionUpdateRequest): Promise<SessionView> {
	return patch<SessionView>(`/api/sessions/${id}`, body);
}

export function deleteSession(id: string): Promise<void> {
	return del(`/api/sessions/${id}`);
}

export function cloneSession(id: string, body: SessionCloneRequest): Promise<SessionView> {
	return post<SessionView>(`/api/sessions/${id}/clone`, body);
}

export function previewTemplate(
	body: TemplatePreviewRequest
): Promise<TemplatePreviewResponse> {
	return post<TemplatePreviewResponse>('/api/sessions/preview', body);
}
