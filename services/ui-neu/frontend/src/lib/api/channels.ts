import { apiFetch } from './client';
import type {
	Channel, ChannelCreate, ChannelUpdate, Catalog,
	DispatchRow
} from '$lib/types/notifications';
import type { EventTypeInfo as _EventTypeInfo, NotificationTestResult } from '$lib/types/api.gen';

export type { NotificationTestResult };

export type EventTypeInfo = _EventTypeInfo;

export function fetchChannels(): Promise<Channel[]> {
	return apiFetch<Channel[]>('/api/notifications/channels');
}

export function fetchChannel(id: number): Promise<Channel> {
	return apiFetch<Channel>(`/api/notifications/channels/${id}`);
}

export function createChannel(body: ChannelCreate): Promise<Channel> {
	return apiFetch<Channel>('/api/notifications/channels', {
		method: 'POST',
		body: JSON.stringify(body)
	});
}

export function updateChannel(id: number, body: ChannelUpdate): Promise<Channel> {
	return apiFetch<Channel>(`/api/notifications/channels/${id}`, {
		method: 'PATCH',
		body: JSON.stringify(body)
	});
}

export function deleteChannel(id: number): Promise<unknown> {
	return apiFetch<unknown>(`/api/notifications/channels/${id}`, { method: 'DELETE' });
}

export function testSendChannel(id: number, eventType: string): Promise<NotificationTestResult> {
	return apiFetch<NotificationTestResult>(`/api/notifications/channels/${id}/test`, {
		method: 'POST',
		body: JSON.stringify({ event_type: eventType })
	});
}

export function fetchDispatches(params?: {
	channelId?: number;
	status?: string;
	limit?: number;
}): Promise<DispatchRow[]> {
	const query = new URLSearchParams();
	if (params?.channelId !== undefined) query.set('channel_id', String(params.channelId));
	if (params?.status) query.set('status', params.status);
	if (params?.limit !== undefined) query.set('limit', String(params.limit));
	const qs = query.toString();
	return apiFetch<DispatchRow[]>(`/api/notifications/dispatches${qs ? `?${qs}` : ''}`);
}

export function fetchServices(): Promise<Catalog> {
	return apiFetch<Catalog>('/api/notifications/services');
}

export function fetchEventTypes(): Promise<EventTypeInfo[]> {
	return apiFetch<EventTypeInfo[]>('/api/notifications/event-types');
}

export function composeUrl(
	serviceId: string,
	required: Record<string, unknown>,
	advanced: Record<string, unknown>
): Promise<{ url: string }> {
	return apiFetch<{ url: string }>(`/api/notifications/services/${serviceId}/compose-url`, {
		method: 'POST',
		body: JSON.stringify({ required, advanced })
	});
}

export function testConfig(body:
	| { type: string; config: Record<string, unknown>; event_type?: string }
	| { channel_id: number; fields: Record<string, unknown>; event_type?: string }
): Promise<NotificationTestResult> {
	return apiFetch<NotificationTestResult>('/api/notifications/test', {
		method: 'POST',
		body: JSON.stringify(body)
	});
}
