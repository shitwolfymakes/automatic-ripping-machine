import type { Channel, ChannelCreate } from '$lib/types/notifications';
import type { NotificationTestResult } from '$lib/api/channels';
import { createChannel, testConfig } from '$lib/api/channels';

// The add-a-channel calls, shared by Settings > Notifications and the setup
// walkthrough's quick add (setup spec D5: one implementation per feature).

export interface ChannelBodyLike {
	type: string;
	name: string;
	enabled: boolean;
	config: Record<string, unknown>;
	subscribed_events: string[];
	templates: ChannelCreate['templates'];
	serviceId: string | null;
}

/** The wire config for a new channel. Apprise URLs are composed server-side from {service_id, fields}. */
export function toConfig(body: Pick<ChannelBodyLike, 'type' | 'config' | 'serviceId'>): Record<string, unknown> {
	if (body.type === 'apprise' && body.serviceId) {
		return { type: 'apprise', url: '', service_id: body.serviceId, fields: body.config };
	}
	return { type: body.type, ...body.config };
}

export function createChannelFromBody(body: ChannelBodyLike): Promise<Channel> {
	const payload: ChannelCreate = {
		type: body.type as ChannelCreate['type'],
		name: body.name,
		enabled: body.enabled,
		config: toConfig(body) as unknown as ChannelCreate['config'],
		subscribed_events: body.subscribed_events,
		templates: body.templates
	};
	return createChannel(payload);
}

export function testUnsavedBody(body: ChannelBodyLike, eventType: string): Promise<NotificationTestResult> {
	return testConfig({ type: body.type, config: toConfig(body), event_type: eventType });
}
