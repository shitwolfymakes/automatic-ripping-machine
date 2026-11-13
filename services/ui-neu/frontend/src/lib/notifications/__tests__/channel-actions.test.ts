import { describe, it, expect, vi, beforeEach } from 'vitest';

const createChannel = vi.fn((b: unknown) => Promise.resolve({ id: 1, ...(b as object) }));
const testConfig = vi.fn((_b?: unknown) => Promise.resolve({ ok: true }));
vi.mock('$lib/api/channels', () => ({
	createChannel: (b: unknown) => createChannel(b),
	testConfig: (b: unknown) => testConfig(b)
}));

import { toConfig, createChannelFromBody, testUnsavedBody, runTest, type AddChannelBody } from '../channel-actions';

const body: AddChannelBody = {
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

	describe('runTest', () => {
		it('reports a delivered send as ok', async () => {
			expect(await runTest(() => Promise.resolve({ ok: true }))).toEqual({ ok: true });
		});

		it('reports a failed send with the error the server gave', async () => {
			expect(await runTest(() => Promise.resolve({ ok: false, error: 'boom' }))).toEqual({
				ok: false,
				detail: 'boom'
			});
		});

		it('reports a failed send with a null error as no detail', async () => {
			expect(await runTest(() => Promise.resolve({ ok: false, error: null }))).toEqual({
				ok: false,
				detail: null
			});
		});

		it('reports a failed send with no error key as no detail', async () => {
			expect(await runTest(() => Promise.resolve({ ok: false }))).toEqual({ ok: false, detail: null });
		});

		it('reports a send that throws an Error with its message', async () => {
			expect(await runTest(() => Promise.reject(new Error('offline')))).toEqual({
				ok: false,
				detail: 'offline'
			});
		});

		it('reports a send that throws something else as no detail', async () => {
			expect(await runTest(() => Promise.reject('nope'))).toEqual({ ok: false, detail: null });
		});
	});
});
