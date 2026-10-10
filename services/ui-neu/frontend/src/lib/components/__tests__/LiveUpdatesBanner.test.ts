import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/svelte';

// Replace the real WS client module with a controllable status store so the
// test drives the banner through every state without a socket.
vi.mock('$lib/api/ws', async () => {
	const { writable } = await import('svelte/store');
	const status = writable<'idle' | 'connecting' | 'online' | 'offline'>('idle');
	return {
		wsStatus: { subscribe: status.subscribe },
		__setStatus: (s: 'idle' | 'connecting' | 'online' | 'offline') => status.set(s)
	};
});

import * as wsModule from '$lib/api/ws';
import LiveUpdatesBanner from '../LiveUpdatesBanner.svelte';

const setStatus = (wsModule as unknown as { __setStatus: (s: string) => void }).__setStatus;

afterEach(() => cleanup());

describe('LiveUpdatesBanner', () => {
	it('renders nothing while idle, connecting or online', () => {
		for (const s of ['idle', 'connecting', 'online']) {
			setStatus(s);
			const { unmount } = render(LiveUpdatesBanner);
			expect(screen.queryByRole('status')).not.toBeInTheDocument();
			unmount();
		}
	});

	it('shows the warning once the connection is offline', () => {
		setStatus('offline');
		render(LiveUpdatesBanner);
		const banner = screen.getByRole('status');
		expect(banner).toHaveTextContent('Live updates unavailable');
		expect(banner.className).toContain('alert-warning');
	});

	it('clears when the connection recovers', async () => {
		setStatus('offline');
		render(LiveUpdatesBanner);
		expect(screen.getByRole('status')).toBeInTheDocument();
		setStatus('online');
		await vi.waitFor(() => {
			expect(screen.queryByRole('status')).not.toBeInTheDocument();
		});
	});
});
