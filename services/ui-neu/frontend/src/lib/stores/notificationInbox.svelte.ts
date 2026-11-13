// The Notifications page's inbox: its rows, the loading and error state, the
// in-flight dismissals, the purge flag, the feedback line and the cleared count.
import {
	fetchNotifications,
	fetchNotificationCount,
	dismissNotification,
	dismissAllNotifications,
	purgeNotifications
} from '$lib/api/notifications';
import type { NotificationInboxView } from '$lib/types/api.gen';
import { SvelteSet } from 'svelte/reactivity';
import { errorMessage } from '$lib/utils/errors';

/** A row as a dismiss leaves it: seen and cleared. */
function markCleared(n: NotificationInboxView): NotificationInboxView {
	return { ...n, seen: true, cleared: true };
}

export class NotificationInbox {
	rows = $state<NotificationInboxView[]>([]);
	loading = $state(true);
	error = $state<Error | null>(null);
	dismissing = $state<Set<string>>(new SvelteSet());
	purging = $state(false);
	feedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);
	// Purge deletes cleared rows, which the inbox list omits, so this comes from the count endpoint.
	clearedCount = $state(0);
	unseenCount = $derived(this.rows.filter((n) => !n.seen).length);

	load = async (): Promise<void> => {
		this.loading = true;
		this.error = null;
		try {
			const [rows, counts] = await Promise.all([fetchNotifications(), fetchNotificationCount().catch(() => null)]);
			this.rows = rows;
			this.clearedCount = counts?.cleared ?? 0;
		} catch (e) {
			this.error = e instanceof Error ? e : new Error('Failed to load notifications');
		} finally {
			this.loading = false;
		}
	};

	dismiss = async (id: string): Promise<void> => {
		this.dismissing = new SvelteSet([...this.dismissing, id]);
		try {
			await dismissNotification(id);
			if (this.rows.some((n) => n.id === id && !n.cleared)) this.clearedCount += 1;
			this.rows = this.rows.map((n) => (n.id === id ? markCleared(n) : n));
		} catch {
			// next refresh will reconcile
		} finally {
			// copy-on-write: reassigning the $state field triggers updates
			const next = new SvelteSet(this.dismissing);
			next.delete(id);
			this.dismissing = next;
		}
	};

	dismissAll = async (): Promise<void> => {
		const ids = this.rows.filter((n) => !n.seen).map((n) => n.id);
		if (ids.length === 0) return;
		this.dismissing = new SvelteSet(ids);
		try {
			const result = await dismissAllNotifications();
			// Like a per-row dismiss: every not-yet-cleared row ends up seen and cleared.
			this.clearedCount += result.updated;
			this.rows = this.rows.map((n) => (n.cleared ? n : markCleared(n)));
		} catch (e) {
			this.feedback = { type: 'error', message: errorMessage(e, 'Dismiss all failed') };
		} finally {
			this.dismissing = new SvelteSet();
		}
	};

	purge = async (): Promise<void> => {
		this.purging = true;
		try {
			const result = await purgeNotifications();
			this.feedback = {
				type: 'success',
				message: `Purged ${result.deleted} cleared notification${result.deleted !== 1 ? 's' : ''}`
			};
			await this.load();
		} catch (e) {
			this.feedback = { type: 'error', message: errorMessage(e, 'Purge failed') };
		}
		this.purging = false;
	};

	clearFeedback = (): void => {
		this.feedback = null;
	};
}
