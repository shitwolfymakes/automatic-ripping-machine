import { describe, it, expect } from 'vitest';
import { editorPatch, editorTestPayload, type EditorBody } from '../channel-edits';
import { appriseChannel, webhookChannel } from '../../components/notifications/__tests__/apprise-fixtures';

function editorBody(overrides: Partial<EditorBody> = {}): EditorBody {
	return {
		name: 'Renamed',
		enabled: false,
		config: { type: 'webhook', url: 'https://edited' },
		subscribed_events: ['rip.completed'],
		templates: { 'rip.completed': { title: 't', body: 'b' } } as EditorBody['templates'],
		appriseFields: {},
		serviceId: 'discord',
		...overrides
	};
}

describe('editorPatch', () => {
	it('carries the body name, enabled, events and templates', () => {
		const body = editorBody();
		expect(editorPatch(webhookChannel(), body)).toMatchObject({
			name: 'Renamed',
			enabled: false,
			subscribed_events: ['rip.completed'],
			templates: body.templates
		});
	});

	it('sends a webhook channel its edited config', () => {
		const body = editorBody();
		expect(editorPatch(webhookChannel(), body).config).toEqual(body.config);
	});

	it('sends an apprise channel its changed fields with the service id', () => {
		const patch = editorPatch(appriseChannel(), editorBody({ appriseFields: { webhook_id: '9' } }));
		expect(patch.config).toEqual({
			type: 'apprise',
			url: '',
			service_id: 'discord',
			fields: { webhook_id: '9' }
		});
	});

	it('omits config for changed apprise fields with no service id', () => {
		const patch = editorPatch(appriseChannel(), editorBody({ appriseFields: { webhook_id: '9' }, serviceId: null }));
		expect('config' in patch).toBe(false);
	});

	it('omits config for unchanged apprise fields', () => {
		const channel = appriseChannel({
			config: { type: 'apprise', url: 'discord://1/2', service_id: 'discord', fields: { a: '1' } }
		});
		const patch = editorPatch(channel, editorBody({ appriseFields: { a: '1' } }));
		expect('config' in patch).toBe(false);
	});

	it('counts empty fields as unchanged when the stored config has no fields', () => {
		const channel = appriseChannel({ config: { type: 'apprise', url: 'discord://1/2', service_id: 'discord' } });
		const patch = editorPatch(channel, editorBody({ appriseFields: {} }));
		expect('config' in patch).toBe(false);
	});
});

describe('editorTestPayload', () => {
	it('tests an apprise channel with its changed fields', () => {
		const payload = editorTestPayload(
			appriseChannel(),
			editorBody({ appriseFields: { webhook_id: '9' } }),
			'job.started'
		);
		expect(payload).toEqual({ channel_id: 1, fields: { webhook_id: '9' }, event_type: 'job.started' });
	});

	it('gives null for an apprise channel with unchanged fields', () => {
		expect(editorTestPayload(appriseChannel(), editorBody({ appriseFields: {} }), 'job.started')).toBeNull();
	});

	it('tests a webhook channel with its edited config', () => {
		const body = editorBody();
		expect(editorTestPayload(webhookChannel(), body, 'job.started')).toEqual({
			type: 'webhook',
			config: body.config,
			event_type: 'job.started'
		});
	});
});
