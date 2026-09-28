import type {
	NotificationInboxView,
	NotificationInboxCountView,
	NotificationInboxUpdateRequest
} from '$lib/types/api.gen';
import { get, patch, post } from './client';

// v3 notifications inbox. The BFF's flat /api/notifications + numeric ids are
// gone; v3 exposes an inbox of NotificationInboxView rows keyed by string id.

export function fetchNotifications(): Promise<NotificationInboxView[]> {
	return get<NotificationInboxView[]>('/api/notifications/inbox');
}

export function fetchNotificationCount(): Promise<NotificationInboxCountView> {
	return get<NotificationInboxCountView>('/api/notifications/inbox/count');
}

// "Dismiss" in the UI == mark the row seen + cleared. v3 PATCHes the inbox row
// with the NotificationInboxUpdateRequest flags (id is a string in v3).
export function dismissNotification(id: string): Promise<NotificationInboxView> {
	const body: NotificationInboxUpdateRequest = { seen: true, cleared: true };
	return patch<NotificationInboxView>(`/api/notifications/inbox/${id}`, body);
}

export interface NotificationDismissAllResult {
	updated: number;
}

export interface NotificationPurgeResult {
	deleted: number;
}

// Marks every unseen row seen. It does NOT clear them, so they are not purgeable.
export function dismissAllNotifications(): Promise<NotificationDismissAllResult> {
	return post<NotificationDismissAllResult>('/api/notifications/inbox/dismiss-all');
}

// Deletes every cleared row.
export function purgeNotifications(): Promise<NotificationPurgeResult> {
	return post<NotificationPurgeResult>('/api/notifications/inbox/purge');
}
