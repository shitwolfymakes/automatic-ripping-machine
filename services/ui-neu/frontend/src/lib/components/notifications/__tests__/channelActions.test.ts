import { describe, it, expect, vi, beforeEach } from 'vitest';

const createChannel = vi.fn((b: unknown) => Promise.resolve({ id: 1, ...(b as object) }));
const testConfig = vi.fn((_b?: unknown) => Promise.resolve({ ok: true }));
vi.mock('$lib/api/channels', () => ({
	createChannel: (b: unknown) => createChannel(b),
	testConfig: (b: unknown) => testConfig(b)
}));

import { toConfig, createChannelFromBody, testUnsavedBody } from '../channelActions';

const body = {
	type: 'apprise',
	name: 'ntfy',
	enabled: true,
	config: { topic: 'arm' },
	subscribed_events: ['rip.completed'],
	templates: {},
	serviceId: 'ntfy'
};

describe('channelActions', () => {
	beforeEach(() => vi.clearAllMocks());

	it('composes an apprise config server-side from the service id and fields', () => {
		expect(toConfig(body)).toEqual({ type: 'apprise', url: '', service_id: 'ntfy', fields: { topic: 'arm' } });
		expect(toConfig({ type: 'webhook', config: { url: 'https://x' }, serviceId: null })).toEqual({
			type: 'webhook',
			url: 'https://x'
		});
	});

	it('creates and tests a channel from a form body', async () => {
		await createChannelFromBody(body);
		expect(createChannel).toHaveBeenCalledWith({
			type: 'apprise',
			name: 'ntfy',
			enabled: true,
			config: { type: 'apprise', url: '', service_id: 'ntfy', fields: { topic: 'arm' } },
			subscribed_events: ['rip.completed'],
			templates: {}
		});
		await testUnsavedBody(body, 'rip.failed');
		expect(testConfig).toHaveBeenCalledWith({
			type: 'apprise',
			config: { type: 'apprise', url: '', service_id: 'ntfy', fields: { topic: 'arm' } },
			event_type: 'rip.failed'
		});
	});
});
