import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, cleanup } from '$lib/test-utils';
import SortIndicator from './SortIndicator.svelte';

describe('SortIndicator', () => {
	afterEach(() => cleanup());

	it('renders a chevron-up glyph when dir is asc', () => {
		const { container } = renderComponent(SortIndicator, { props: { dir: 'asc' } });
		const path = container.querySelector('svg path');
		expect(path).toHaveAttribute('d', 'M5 15l7-7 7 7');
	});

	it('renders a chevron-down glyph when dir is desc', () => {
		const { container } = renderComponent(SortIndicator, { props: { dir: 'desc' } });
		const path = container.querySelector('svg path');
		expect(path).toHaveAttribute('d', 'M19 9l-7 7-7-7');
	});

	it('renders nothing when dir is null', () => {
		const { container } = renderComponent(SortIndicator, { props: { dir: null } });
		expect(container.querySelector('svg')).toBeNull();
	});

	it('applies the table-sort-indicator class', () => {
		const { container } = renderComponent(SortIndicator, { props: { dir: 'asc' } });
		const svg = container.querySelector('svg');
		expect(svg).toHaveClass('table-sort-indicator');
	});

	it('appends a custom class', () => {
		const { container } = renderComponent(SortIndicator, { props: { dir: 'asc', class: 'inline' } });
		const svg = container.querySelector('svg');
		expect(svg).toHaveClass('table-sort-indicator', 'inline');
	});
});
