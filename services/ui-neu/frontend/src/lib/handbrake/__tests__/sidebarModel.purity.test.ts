import { describe, expect, it, vi } from 'vitest';

const evaluated = vi.hoisted(() => ({ store: false }));

vi.mock('$lib/stores/encoders.svelte', () => {
	evaluated.store = true;
	return {};
});

describe('sidebarModel purity', () => {
	it('loads without evaluating the encoders store', async () => {
		const model = await import('../sidebarModel');
		expect(model).toBeDefined();
		expect(evaluated.store).toBe(false);
	});
});
