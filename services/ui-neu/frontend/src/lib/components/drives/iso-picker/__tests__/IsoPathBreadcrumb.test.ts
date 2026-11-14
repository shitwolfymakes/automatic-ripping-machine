import { describe, it, expect, afterEach, vi } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import IsoPathBreadcrumb from '../IsoPathBreadcrumb.svelte';

const trail = [
	{ label: 'Library', path: '' },
	{ label: 'Movies', path: 'Movies' },
	{ label: '2024', path: 'Movies/2024' }
];

describe('IsoPathBreadcrumb', () => {
	afterEach(() => cleanup());

	it('shows only the current folder when the trail has one item', () => {
		const { container } = renderComponent(IsoPathBreadcrumb, {
			items: [trail[0]],
			onnavigate: vi.fn()
		});
		expect(screen.getByText('Library')).toHaveAttribute('aria-current', 'page');
		expect(screen.queryByRole('button')).not.toBeInTheDocument();
		expect(container.querySelector('.iso-picker-breadcrumb-sep')).toBeNull();
	});

	it('links every folder but the last and puts a chevron before each item after the first', () => {
		const { container } = renderComponent(IsoPathBreadcrumb, {
			items: trail,
			onnavigate: vi.fn()
		});
		const links = screen.getAllByRole('button');
		expect(links.map((l) => l.textContent?.trim())).toEqual(['Library', 'Movies']);
		expect(screen.getByText('2024')).toHaveAttribute('aria-current', 'page');
		expect(container.querySelectorAll('.iso-picker-breadcrumb-sep')).toHaveLength(2);
	});

	it('calls onnavigate with the path of the clicked link', async () => {
		const onnavigate = vi.fn();
		renderComponent(IsoPathBreadcrumb, { items: trail, onnavigate });
		await fireEvent.click(screen.getByRole('button', { name: 'Movies' }));
		expect(onnavigate).toHaveBeenCalledExactlyOnceWith('Movies');
	});
});
