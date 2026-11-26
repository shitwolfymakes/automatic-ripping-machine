import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/handbrake-schema', () => ({
	fetchHandbrakeSchema: vi.fn(),
	refreshHandbrakeSchema: vi.fn()
}));

import { fetchHandbrakeSchema, refreshHandbrakeSchema } from '$lib/api/handbrake-schema';
import { ApiError } from '$lib/api/client';
import type { HandbrakeSchemaSlimView } from '$lib/types/api.gen';
import { handbrakeSchema } from '../handbrake-schema.svelte';

const SCHEMA = { handbrake_tag: '1.11.1' } as HandbrakeSchemaSlimView;

beforeEach(() => {
	vi.clearAllMocks();
	handbrakeSchema.reset();
});

describe('handbrakeSchema store', () => {
	it('starts idle', () => {
		expect(handbrakeSchema.state).toBe('idle');
		expect(handbrakeSchema.schema).toBeNull();
	});

	it('loads into ready', async () => {
		vi.mocked(fetchHandbrakeSchema).mockResolvedValue(SCHEMA);
		const p = handbrakeSchema.load();
		expect(handbrakeSchema.state).toBe('loading');
		await p;
		expect(handbrakeSchema.state).toBe('ready');
		expect(handbrakeSchema.schema).toEqual(SCHEMA);
		expect(handbrakeSchema.error).toBeNull();
	});

	it('goes unavailable with the 503 message', async () => {
		vi.mocked(fetchHandbrakeSchema).mockRejectedValue(
			new ApiError(503, 'No HandBrake schema loaded yet', { detail: 'No HandBrake schema loaded yet' })
		);
		await handbrakeSchema.load();
		expect(handbrakeSchema.state).toBe('unavailable');
		expect(handbrakeSchema.error).toBe('No HandBrake schema loaded yet');
		expect(handbrakeSchema.schema).toBeNull();
	});

	it('stringifies a non-Error failure', async () => {
		vi.mocked(fetchHandbrakeSchema).mockRejectedValue('boom');
		await handbrakeSchema.load();
		expect(handbrakeSchema.error).toBe('boom');
	});

	it('retry refreshes, then loads', async () => {
		const order: string[] = [];
		vi.mocked(refreshHandbrakeSchema).mockImplementation(async () => {
			order.push('refresh');
			return { ok: true, error: null };
		});
		vi.mocked(fetchHandbrakeSchema).mockImplementation(async () => {
			order.push('load');
			return SCHEMA;
		});
		await handbrakeSchema.retry();
		expect(order).toEqual(['refresh', 'load']);
		expect(handbrakeSchema.state).toBe('ready');
	});

	it('retry reports a failed refresh and still tries to load', async () => {
		vi.mocked(refreshHandbrakeSchema).mockResolvedValue({ ok: false, error: 'offline' });
		vi.mocked(fetchHandbrakeSchema).mockRejectedValue(new Error('No HandBrake schema loaded yet'));
		await handbrakeSchema.retry();
		expect(handbrakeSchema.state).toBe('unavailable');
		expect(handbrakeSchema.error).toBe('offline');
	});

	it('retry survives a refresh that throws', async () => {
		vi.mocked(refreshHandbrakeSchema).mockRejectedValue(new Error('net'));
		vi.mocked(fetchHandbrakeSchema).mockResolvedValue(SCHEMA);
		await handbrakeSchema.retry();
		expect(handbrakeSchema.state).toBe('ready');
	});
});
