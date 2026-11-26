// Loading/failure states of the encoder picker's GET /api/encoders fetch,
// isolated in its own file so the shared encoders store's module-level
// cache (src/lib/stores/encoders.svelte.ts) starts fresh (Vitest isolates
// modules per test file) and a single controlled fetch can be driven
// through loading and then failure within one render.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, waitFor, cleanup } from '$lib/test-utils';
import { initialDraft } from '$lib/handbrake/sidebarModel';
import PresetBlock from '../PresetBlock.svelte';

let rejectFetch: (e: unknown) => void = () => {};
vi.mock('$lib/api/encoders', () => ({
	fetchEncoders: () =>
		new Promise((_resolve, reject) => {
			rejectFetch = reject;
		})
}));

// The encoders store follows transcode.events; keep jsdom off a real socket.
vi.mock('$lib/api/ws', () => ({
	wsClient: { start: vi.fn(), subscribe: vi.fn(() => () => {}) }
}));

afterEach(() => cleanup());

describe('PresetBlock encoder catalog loading and failure', () => {
	it('shows a loading placeholder, then an inline error on failure, keeping the current encoder selected', async () => {
		renderComponent(PresetBlock, {
			props: {
				draft: { ...initialDraft(null), encoder: 'any_h265' },
				readonly: false,
				editing: true,
				builtinNames: [],
				issues: [],
				onfield: vi.fn()
			}
		});

		const encoder = screen.getByTestId('tp-encoder') as HTMLSelectElement;
		await waitFor(() => expect(encoder).toBeDisabled());
		expect(screen.getByText('Loading encoders...')).toBeInTheDocument();
		expect(encoder.value).toBe('any_h265');
		expect(screen.queryByTestId('tp-encoder-error')).not.toBeInTheDocument();

		rejectFetch(new Error('network down'));

		await waitFor(() =>
			expect(screen.getByTestId('tp-encoder-error').textContent).toBe(
				'Could not load encoders; the current encoder is kept.'
			)
		);
		expect(encoder).not.toBeDisabled();
		expect(encoder.value).toBe('any_h265');
	});
});
