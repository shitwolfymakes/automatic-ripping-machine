import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, cleanup } from '$lib/testing/render';
import TranscoderStatsSkeleton from '../TranscoderStatsSkeleton.svelte';

afterEach(() => {
	cleanup();
});

describe('TranscoderStatsSkeleton', () => {
	it('renders one header panel with a title and a subtitle placeholder', () => {
		const { container } = renderComponent(TranscoderStatsSkeleton);
		const headerPanel = container.querySelector('.stack > .panel');
		expect(headerPanel).not.toBeNull();
		expect(headerPanel?.querySelectorAll('.transcoder-page-skeleton-title')).toHaveLength(1);
		expect(headerPanel?.querySelectorAll('.transcoder-page-skeleton-subtitle')).toHaveLength(1);
	});

	it('renders five tile panels each with a label and a value placeholder', () => {
		const { container } = renderComponent(TranscoderStatsSkeleton);
		const tiles = container.querySelectorAll('.grid > .panel');
		expect(tiles).toHaveLength(5);
		for (const tile of tiles) {
			expect(tile.querySelectorAll('.transcoder-page-skeleton-label')).toHaveLength(1);
			expect(tile.querySelectorAll('.transcoder-page-skeleton-value')).toHaveLength(1);
		}
	});
});
