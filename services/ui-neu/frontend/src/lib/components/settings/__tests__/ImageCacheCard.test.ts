import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/testing/render';
import { ImageCache } from '$lib/stores/image-cache.svelte';
import ImageCacheCard from '../ImageCacheCard.svelte';

vi.mock('$lib/api/maintenance', () => ({
	fetchImageCacheStats: vi.fn(),
	clearImageCache: vi.fn()
}));

afterEach(cleanup);

function render(setup: (cache: ImageCache) => void = () => {}) {
	const cache = new ImageCache();
	setup(cache);
	renderComponent(ImageCacheCard, { cache });
	return cache;
}

const clearButton = () => screen.getByRole('button', { name: 'Clear Cache' }) as HTMLButtonElement;

describe('ImageCacheCard', () => {
	it('shows Loading... while the cache loads', () => {
		render((c) => (c.loading = true));
		expect(screen.getByText(/Loading\.\.\./)).toBeInTheDocument();
	});

	it('shows the count, singular wording and size for one image', () => {
		render((c) => (c.stats = { count: 1, size_mb: 0.5 } as never));
		expect(screen.getByText(/1 cached image \(0\.5\s+MB\)/)).toBeInTheDocument();
	});

	it('shows the count, plural wording and size for several images', () => {
		render((c) => (c.stats = { count: 3, size_mb: 12.4 } as never));
		expect(screen.getByText(/3 cached images \(12\.4\s+MB\)/)).toBeInTheDocument();
	});

	it('shows Unable to load cache stats when there are no stats', () => {
		render();
		expect(screen.getByText(/Unable to load cache stats/)).toBeInTheDocument();
	});

	it('disables Clear Cache while busy', () => {
		render((c) => {
			c.stats = { count: 2, size_mb: 1 } as never;
			c.busy = true;
		});
		expect(clearButton()).toBeDisabled();
	});

	it('disables Clear Cache with a zero count', () => {
		render((c) => (c.stats = { count: 0, size_mb: 0 } as never));
		expect(clearButton()).toBeDisabled();
	});

	it('disables Clear Cache with no stats', () => {
		render();
		expect(clearButton()).toBeDisabled();
	});

	it('enables Clear Cache when idle with cached images', () => {
		render((c) => (c.stats = { count: 2, size_mb: 1 } as never));
		expect(clearButton()).toBeEnabled();
	});

	it('opens the confirmation when Clear Cache is clicked', async () => {
		const cache = render((c) => (c.stats = { count: 2, size_mb: 1 } as never));
		await fireEvent.click(clearButton());
		expect(cache.confirmOpen).toBe(true);
	});

	it('renders no feedback line without feedback', () => {
		const { container } = renderComponent(ImageCacheCard, { cache: new ImageCache() });
		expect(container.querySelector('.settings-page-feedback')).toBeNull();
	});

	it('marks a success feedback line as not an error', () => {
		render((c) => (c.feedback = { type: 'success', message: 'Cleared 2 cached images' }));
		expect(screen.getByText('Cleared 2 cached images')).toHaveAttribute('data-error', 'false');
	});

	it('marks an error feedback line as an error', () => {
		render((c) => (c.feedback = { type: 'error', message: 'Failed to clear cache' }));
		expect(screen.getByText('Failed to clear cache')).toHaveAttribute('data-error', 'true');
	});
});
