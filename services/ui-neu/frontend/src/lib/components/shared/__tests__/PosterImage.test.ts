import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderComponent, cleanup, fireEvent } from '$lib/testing/render';
import PosterImage from '../PosterImage.svelte';

const URL_A = 'https://img.example/a.jpg';
const URL_B = 'https://img.example/b.jpg';

function poster(container: HTMLElement): HTMLImageElement {
	return container.querySelector('img[data-poster]') as HTMLImageElement;
}

describe('PosterImage', () => {
	afterEach(() => cleanup());

	it('stays transparent until the poster has loaded, then shows it', async () => {
		const { container } = renderComponent(PosterImage, { props: { url: URL_A } });
		const img = poster(container);
		expect(img).toHaveAttribute('data-loaded', 'false');
		expect(img).toHaveAttribute('loading', 'lazy');
		await fireEvent.load(img);
		expect(img).toHaveAttribute('data-loaded', 'true');
	});

	it('hides a new poster again until it loads', async () => {
		const { container, rerender } = renderComponent(PosterImage, { props: { url: URL_A } });
		await fireEvent.load(poster(container));
		await rerender({ url: URL_B });
		expect(poster(container)).toHaveAttribute('data-loaded', 'false');
		await fireEvent.load(poster(container));
		expect(poster(container)).toHaveAttribute('data-loaded', 'true');
	});

	it('shows a poster that loads from the cache at once, without the fade', async () => {
		const now = vi.spyOn(performance, 'now').mockReturnValue(1000);
		try {
			const { container } = renderComponent(PosterImage, { props: { url: URL_A } });
			now.mockReturnValue(1010);
			await fireEvent.load(poster(container));
			expect(poster(container)).toHaveAttribute('data-loaded', 'true');
			expect(poster(container)).toHaveAttribute('data-instant', 'true');
		} finally {
			now.mockRestore();
		}
	});

	it('fades in a poster that took the network, timed from its own url', async () => {
		const now = vi.spyOn(performance, 'now').mockReturnValue(1000);
		try {
			const { container, rerender } = renderComponent(PosterImage, { props: { url: URL_A } });
			now.mockReturnValue(1010);
			await fireEvent.load(poster(container));
			now.mockReturnValue(5000);
			await rerender({ url: URL_B });
			now.mockReturnValue(5400);
			await fireEvent.load(poster(container));
			expect(poster(container)).toHaveAttribute('data-loaded', 'true');
			expect(poster(container)).toHaveAttribute('data-instant', 'false');
		} finally {
			now.mockRestore();
		}
	});

	it('swaps a broken poster for the fallback, and back for a new url', async () => {
		const { container, rerender } = renderComponent(PosterImage, { props: { url: URL_A, class: 'thumb' } });
		await fireEvent.error(poster(container));
		expect(poster(container)).toBeNull();
		expect(container.querySelector('.poster-image-fallback.thumb')).not.toBeNull();
		await rerender({ url: URL_B, class: 'thumb' });
		expect(poster(container)).not.toBeNull();
	});

	it('shows the fallback when there is no url', () => {
		const { container } = renderComponent(PosterImage, { props: { url: null, alt: 'none' } });
		expect(poster(container)).toBeNull();
		expect(container.querySelector('.poster-image-fallback')).not.toBeNull();
	});
});
