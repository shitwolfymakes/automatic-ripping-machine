import { describe, it, expect, afterEach, vi } from 'vitest';
import { createRawSnippet } from 'svelte';
import { renderComponent, cleanup } from '$lib/testing/render';
import DashboardSection from '../DashboardSection.svelte';

// jsdom cannot run Web Animations; a transition with no duration finishes
// synchronously.
vi.mock('svelte/transition', () => ({
	fade: () => ({ duration: 0 })
}));

interface Item {
	id: string;
	name: string;
}

const ITEMS: Item[] = [
	{ id: 'a', name: 'Alpha' },
	{ id: 'b', name: 'Beta' }
];

const row = createRawSnippet<[Item]>((item) => ({
	render: () => `<span data-testid="row">${item().name}</span>`
}));

function renderSection(props: Record<string, unknown> = {}) {
	return renderComponent(DashboardSection, {
		items: ITEMS,
		key: (item: Item) => item.id,
		accent: 'var(--color-primary)',
		label: 'THINGS - 2',
		row,
		...props
	});
}

describe('DashboardSection', () => {
	afterEach(() => cleanup());

	it('renders nothing when the list is empty', () => {
		const { container } = renderSection({ items: [] });
		expect(container.querySelector('section')).toBeNull();
	});

	it('shows the label and accent on the frame', () => {
		const { container } = renderSection();
		const frame = container.querySelector('section > *') as HTMLElement;
		expect(frame.textContent).toContain('THINGS - 2');
		expect(frame.getAttribute('style')).toContain('var(--color-primary)');
	});

	it('marks the frame as emphasised when emphasis is given', () => {
		const { container } = renderSection({ emphasis: true });
		expect(container.querySelector('[data-frame-emphasis]')).not.toBeNull();
	});

	it('leaves the frame unemphasised when emphasis is not given', () => {
		const { container } = renderSection();
		expect(container.querySelector('[data-frame-emphasis]')).toBeNull();
	});

	it('lays rows out with space-y-2 by default', () => {
		const { container } = renderSection();
		expect(container.querySelector('.space-y-2')).not.toBeNull();
	});

	it('uses a custom list class when given', () => {
		const { container } = renderSection({ listClass: 'grid grid-cols-1 gap-4' });
		expect(container.querySelector('.grid.grid-cols-1.gap-4')).not.toBeNull();
		expect(container.querySelector('.space-y-2')).toBeNull();
	});

	it('renders one row per item in order', () => {
		const { getAllByTestId } = renderSection();
		expect(getAllByTestId('row').map((el) => el.textContent)).toEqual(['Alpha', 'Beta']);
	});
});
