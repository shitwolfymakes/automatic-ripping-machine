import { describe, expect, it, vi } from 'vitest';

const evaluated = vi.hoisted(() => ({ store: false, client: false }));

vi.mock('$lib/stores/encoders.svelte', () => {
	evaluated.store = true;
	return {};
});
vi.mock('$lib/api/client', () => {
	evaluated.client = true;
	return {};
});

const MODULES = ['../draft', '../draft-rules', '../base-values', '../visibility', '../display', '../panel-view'];

describe('preset sidebar logic purity', () => {
	it.each(MODULES)('%s loads without the encoders store or the API client', async (path) => {
		const model = await import(/* @vite-ignore */ path);
		expect(model).toBeDefined();
		expect(evaluated.store).toBe(false);
		expect(evaluated.client).toBe(false);
	});
});
