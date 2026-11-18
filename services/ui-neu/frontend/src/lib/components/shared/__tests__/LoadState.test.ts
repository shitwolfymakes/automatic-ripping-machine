// Every branch of LoadState's own code is covered. The coverage tool still
// reports one open arm that is Svelte's: `{view.error.message}` compiles to
// `(...) ?? ''`, and an Error's message is always a string.
import { describe, it, expect, afterEach, vi } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import { createRawSnippet } from 'svelte';
import LoadState from '../LoadState.svelte';

function textSnippet(text: string) {
	return createRawSnippet(() => ({ render: () => `<span>${text}</span>` }));
}

function valueSnippet() {
	return createRawSnippet((get: () => unknown) => ({
		render: () => `<span>ready:${JSON.stringify(get())}</span>`
	}));
}

describe('LoadState', () => {
	afterEach(() => cleanup());

	it('renders the loading snippet after minDelay when loading=true and no data', async () => {
		vi.useFakeTimers();
		renderComponent(LoadState, {
			props: {
				data: null,
				loading: true,
				loadingSlot: textSnippet('LOADING'),
				ready: valueSnippet()
			}
		});
		// Before minDelay (300ms) the skeleton is in flow (space reserved) but hidden.
		expect(screen.getByText('LOADING').closest('[aria-hidden="true"]')).not.toBeNull();
		await vi.advanceTimersByTimeAsync(299);
		expect(screen.getByText('LOADING').closest('[aria-hidden="true"]')).not.toBeNull();
		await vi.advanceTimersByTimeAsync(1);
		expect(screen.getByText('LOADING').closest('[aria-hidden="true"]')).toBeNull();
		vi.useRealTimers();
	});

	it('waits rather than showing the skeleton before a load has started', () => {
		renderComponent(LoadState, {
			props: { data: null, loading: false, loadingSlot: textSnippet('LOADING'), ready: valueSnippet() }
		});
		expect(screen.getByText('LOADING').closest('[aria-hidden="true"]')).not.toBeNull();
	});

	it('keeps a shown skeleton up for the minimum time once the data lands', async () => {
		vi.useFakeTimers();
		const props = {
			data: null as number[] | null,
			loading: true,
			loadingSlot: textSnippet('LOADING'),
			ready: valueSnippet()
		};
		const { rerender } = renderComponent(LoadState, { props });
		await vi.advanceTimersByTimeAsync(300);
		await rerender({ ...props, data: [1], loading: false });
		expect(screen.getByText('LOADING')).toBeInTheDocument();
		expect(screen.queryByText(/^ready:/)).toBeNull();
		await vi.advanceTimersByTimeAsync(300);
		expect(screen.getByText(/^ready:/)).toBeInTheDocument();
		vi.useRealTimers();
	});

	it('swaps straight to the data with minDelay=0 (no hold)', async () => {
		const props = {
			data: null as number[] | null,
			loading: true,
			minDelay: 0,
			loadingSlot: textSnippet('LOADING'),
			ready: valueSnippet()
		};
		const { rerender } = renderComponent(LoadState, { props });
		await rerender({ ...props, data: [1], loading: false });
		expect(screen.getByText(/^ready:/)).toBeInTheDocument();
	});

	it('renders the ready snippet when loading=false and data is non-empty', () => {
		renderComponent(LoadState, {
			props: {
				data: [1, 2, 3],
				loading: false,
				loadingSlot: textSnippet('LOADING'),
				ready: valueSnippet()
			}
		});
		expect(screen.getByText(/^ready:/)).toBeInTheDocument();
	});

	it('renders the empty snippet when loading=false and data is an empty array', () => {
		renderComponent(LoadState, {
			props: {
				data: [],
				loading: false,
				loadingSlot: textSnippet('LOADING'),
				ready: valueSnippet(),
				empty: textSnippet('EMPTY')
			}
		});
		expect(screen.getByText('EMPTY')).toBeInTheDocument();
	});

	it('uses a custom isEmpty predicate when provided', () => {
		renderComponent(LoadState, {
			props: {
				data: { items: [] },
				loading: false,
				isEmpty: (d: { items: unknown[] }) => d.items.length === 0,
				loadingSlot: textSnippet('LOADING'),
				ready: valueSnippet(),
				empty: textSnippet('CUSTOM_EMPTY')
			}
		});
		expect(screen.getByText('CUSTOM_EMPTY')).toBeInTheDocument();
	});

	it('renders the error snippet when error prop is non-null', () => {
		renderComponent(LoadState, {
			props: {
				data: [1],
				loading: false,
				error: new Error('boom'),
				loadingSlot: textSnippet('LOADING'),
				ready: valueSnippet(),
				errorSlot: createRawSnippet((get: () => Error) => ({
					render: () => `<span>ERR:${get().message}</span>`
				}))
			}
		});
		expect(screen.getByText('ERR:boom')).toBeInTheDocument();
	});

	it('renders a default error message when errorSlot is not provided', () => {
		renderComponent(LoadState, {
			props: {
				data: null,
				loading: false,
				error: new Error('fatal'),
				loadingSlot: textSnippet('LOADING'),
				ready: valueSnippet()
			}
		});
		expect(screen.getByText(/fatal/)).toBeInTheDocument();
	});

	it('respects a custom minDelay', async () => {
		vi.useFakeTimers();
		renderComponent(LoadState, {
			props: {
				data: null,
				loading: true,
				minDelay: 500,
				loadingSlot: textSnippet('LOADING'),
				ready: valueSnippet()
			}
		});
		await vi.advanceTimersByTimeAsync(300);
		expect(screen.getByText('LOADING').closest('[aria-hidden="true"]')).not.toBeNull();
		await vi.advanceTimersByTimeAsync(300);
		expect(screen.getByText('LOADING').closest('[aria-hidden="true"]')).toBeNull();
		vi.useRealTimers();
	});

	it('renders loading immediately when minDelay=0', () => {
		renderComponent(LoadState, {
			props: {
				data: null,
				loading: true,
				minDelay: 0,
				loadingSlot: textSnippet('INSTANT'),
				ready: valueSnippet()
			}
		});
		expect(screen.getByText('INSTANT')).toBeInTheDocument();
	});
});
