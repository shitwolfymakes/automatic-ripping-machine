import { describe, it, expect, afterEach, vi } from 'vitest';
import { mount, unmount } from 'svelte';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import TranscoderOfflineBanner from '../TranscoderOfflineBanner.svelte';

// jsdom cannot run Web Animations, so an outro would never finish; a
// transition with no duration finishes synchronously.
vi.mock('svelte/transition', () => ({
	fade: () => ({ duration: 0 })
}));

afterEach(() => {
	cleanup();
});

describe('TranscoderOfflineBanner', () => {
	it('shows the Transcoder Offline title', () => {
		renderComponent(TranscoderOfflineBanner);
		expect(screen.getByText('Transcoder Offline')).toBeInTheDocument();
	});

	it('shows the not-responding subtitle', () => {
		renderComponent(TranscoderOfflineBanner);
		expect(
			screen.getByText('The transcoder service is not responding. Transcoding features are unavailable.')
		).toBeInTheDocument();
	});

	it('shows the status dot', () => {
		const { container } = renderComponent(TranscoderOfflineBanner);
		expect(container.querySelector('.transcoder-page-offline-dot')).toBeInTheDocument();
	});

	it('fades out when it is unmounted with an outro', async () => {
		const target = document.createElement('div');
		document.body.appendChild(target);
		const component = mount(TranscoderOfflineBanner, { target });
		await unmount(component, { outro: true });
		expect(target.textContent).toBe('');
		target.remove();
	});
});
