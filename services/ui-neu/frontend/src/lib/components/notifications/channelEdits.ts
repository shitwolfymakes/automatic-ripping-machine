// What the inline channel editor on Settings > Notifications emits, and
// the requests its Save and Send test build from it. An apprise channel
// whose fields are unchanged sends no config, so the backend keeps its
// stored URL.
import type { AppriseConfig, Channel, ChannelTemplate, ChannelUpdate } from '$lib/types/notifications';
import type { testConfig } from '$lib/api/channels';

export interface EditorBody {
	name: string;
	enabled: boolean;
	config: Record<string, unknown>;
	subscribed_events: string[];
	templates: Record<string, ChannelTemplate>;
	appriseFields: Record<string, unknown>;
	serviceId: string | null;
}

/** What testConfig sends. */
type TestPayload = Parameters<typeof testConfig>[0];

// Has the editor changed the apprise field map vs what's stored? When
// false the editor handlers omit `config` from the PATCH (save) or
// fall through to the saved-channel test path so neu keeps the
// stored url + recompose state intact.
function appriseFieldsDirty(c: Channel, body: EditorBody): boolean {
	const stored = ((c.config as AppriseConfig).fields ?? {}) as Record<string, unknown>;
	return JSON.stringify(body.appriseFields) !== JSON.stringify(stored);
}

/**
 * Save's PATCH body. A webhook or bash channel sends its edited config;
 * an apprise channel sends its fields only when they changed and a
 * service is set.
 */
export function editorPatch(c: Channel, body: EditorBody): ChannelUpdate {
	const patch: Record<string, unknown> = {
		name: body.name,
		enabled: body.enabled,
		subscribed_events: body.subscribed_events,
		templates: body.templates
	};
	if (c.type === 'apprise') {
		if (appriseFieldsDirty(c, body) && body.serviceId) {
			patch.config = {
				type: 'apprise',
				url: '',
				service_id: body.serviceId,
				fields: body.appriseFields
			};
		}
		// not dirty -> omit config -> neu keeps stored url + fields
	} else {
		patch.config = body.config as unknown as Channel['config'];
	}
	return patch as ChannelUpdate;
}

/**
 * What Send test checks: an apprise channel's edited fields, or a webhook
 * or bash channel's edited config. Null for an apprise channel whose
 * fields are unchanged: the caller tests the saved channel instead.
 */
export function editorTestPayload(c: Channel, body: EditorBody, eventType: string): TestPayload | null {
	if (c.type === 'apprise') {
		if (appriseFieldsDirty(c, body)) {
			return { channel_id: c.id, fields: body.appriseFields, event_type: eventType };
		}
		return null;
	}
	// Webhook/bash: test the edited config directly via the unsaved-config
	// endpoint so the user tests their current edits, not the last-saved state.
	return { type: c.type, config: body.config, event_type: eventType };
}
