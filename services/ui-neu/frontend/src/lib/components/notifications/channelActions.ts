import type { Channel, ChannelCreate, ChannelTemplate, ChannelType } from '$lib/types/notifications';
import type { NotificationTestResult } from '$lib/api/channels';
import { createChannel, testConfig } from '$lib/api/channels';

// The add-a-channel and test-send calls, shared by Settings > Notifications
// and the setup walkthrough's quick add (setup spec D5: one implementation
// per feature).

/** A channel as the add form builds it: its fields, with the picked
 * Apprise service kept apart from its config. */
export interface AddChannelBody {
	type: ChannelType;
	name: string;
	enabled: boolean;
	config: Record<string, unknown>;
	subscribed_events: string[];
	templates: Record<string, ChannelTemplate>;
	serviceId: string | null;
}

/** The wire config for a new channel. Apprise URLs are composed server-side from {service_id, fields}. */
export function toConfig(body: Pick<AddChannelBody, 'type' | 'config' | 'serviceId'>): Record<string, unknown> {
	if (body.type === 'apprise' && body.serviceId) {
		return { type: 'apprise', url: '', service_id: body.serviceId, fields: body.config };
	}
	return { type: body.type, ...body.config };
}

export function createChannelFromBody(body: AddChannelBody): Promise<Channel> {
	const payload: ChannelCreate = {
		type: body.type,
		name: body.name,
		enabled: body.enabled,
		config: toConfig(body) as unknown as ChannelCreate['config'],
		subscribed_events: body.subscribed_events,
		templates: body.templates
	};
	return createChannel(payload);
}

export function testUnsavedBody(body: AddChannelBody, eventType: string): Promise<NotificationTestResult> {
	return testConfig({ type: body.type, config: toConfig(body), event_type: eventType });
}

/** How a test send went: delivered, or failed with what the server or
 * the request said, if anything. */
export type TestOutcome = { ok: true } | { ok: false; detail: string | null };

/** Runs a test send. A send that throws failed too, with the error's
 * message as the detail. */
export async function runTest(send: () => Promise<NotificationTestResult>): Promise<TestOutcome> {
	try {
		const res = await send();
		return res.ok ? { ok: true } : { ok: false, detail: res.error ?? null };
	} catch (e) {
		return { ok: false, detail: e instanceof Error ? e.message : null };
	}
}
