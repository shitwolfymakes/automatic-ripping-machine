import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent, waitFor, within } from '$lib/test-utils';
import { ApiError } from '$lib/api/client';
import { toasts, dismissToast } from '$lib/stores/toast.svelte';
import IsoPicker from '../IsoPicker.svelte';

const fetchIsoLibraryMock = vi.fn();
const startIsoRipMock = vi.fn();
const cancelIsoRipMock = vi.fn();
vi.mock('$lib/api/iso', () => ({
	fetchIsoLibrary: (...args: unknown[]) => fetchIsoLibraryMock(...args),
	startIsoRip: (...args: unknown[]) => startIsoRipMock(...args),
	cancelIsoRip: (...args: unknown[]) => cancelIsoRipMock(...args)
}));

const fetchSessionsMock = vi.fn();
vi.mock('$lib/api/sessions', () => ({
	fetchSessions: (...args: unknown[]) => fetchSessionsMock(...args)
}));

const ROOT_LISTING = {
	host_path: '/mnt/nas/iso',
	subpath: '',
	parent_subpath: null,
	entries: [
		{ name: 'Movies', kind: 'folder', size_bytes: null, modified_at: null, ripping: false },
		{ name: 'a.iso', kind: 'iso', size_bytes: 1073741824, modified_at: '2026-08-14T00:00:00Z', ripping: false },
		{ name: 'b.iso', kind: 'iso', size_bytes: 500000000, modified_at: '2026-09-03T00:00:00Z', ripping: true },
		{ name: 'c.iso', kind: 'iso', size_bytes: 300000000, modified_at: '2026-02-17T00:00:00Z', ripping: false }
	]
};

const MOVIES_LISTING = {
	host_path: '/mnt/nas/iso',
	subpath: 'Movies',
	parent_subpath: '',
	entries: [
		{ name: 'inner.iso', kind: 'iso', size_bytes: 2000000000, modified_at: '2026-01-01T00:00:00Z', ripping: false }
	]
};

const SESSIONS = [
	{ id: 'ses_1', name: 'Movie to Archive MKV', media_type: 'movie', is_builtin: false },
	{ id: 'ses_2', name: 'TV: Plex', media_type: 'tv', is_builtin: false }
];

function defaultProps() {
	return {
		open: true,
		onclose: vi.fn(),
		onstarted: vi.fn()
	};
}

beforeEach(() => {
	fetchIsoLibraryMock.mockReset();
	startIsoRipMock.mockReset();
	cancelIsoRipMock.mockReset();
	fetchSessionsMock.mockReset();
	fetchSessionsMock.mockResolvedValue(SESSIONS);
	fetchIsoLibraryMock.mockImplementation((subpath?: string) => {
		if (!subpath) return Promise.resolve(ROOT_LISTING);
		if (subpath === 'Movies') return Promise.resolve(MOVIES_LISTING);
		return Promise.reject(new Error(`unexpected subpath: ${subpath}`));
	});
});

afterEach(() => {
	for (const t of toasts.value) dismissToast(t.id);
	cleanup();
});

describe('IsoPicker', () => {
	it('lists folders then ISOs and selects an ISO by click and by keyboard', async () => {
		renderComponent(IsoPicker, { props: defaultProps() });
		await waitFor(() => expect(screen.getByRole('option', { name: 'a.iso' })).toBeInTheDocument());

		const options = within(screen.getByRole('listbox')).getAllByRole('option');
		expect(options.map((o) => o.getAttribute('aria-label'))).toEqual(['Movies', 'a.iso', 'b.iso', 'c.iso']);

		// Selects by click.
		await fireEvent.click(screen.getByRole('option', { name: 'a.iso' }));
		expect(screen.getByRole('option', { name: 'a.iso' })).toHaveAttribute('aria-selected', 'true');
		expect(screen.getByText('Selected: a.iso')).toBeInTheDocument();

		// Selects a different row by keyboard (Enter), moving the selection off a.iso.
		await fireEvent.keyDown(screen.getByRole('option', { name: 'c.iso' }), { key: 'Enter' });
		expect(screen.getByRole('option', { name: 'c.iso' })).toHaveAttribute('aria-selected', 'true');
		expect(screen.getByRole('option', { name: 'a.iso' })).toHaveAttribute('aria-selected', 'false');
		expect(screen.getByText('Selected: c.iso')).toBeInTheDocument();
	});

	it('opens a folder with Enter and goes up with Backspace, restoring keyboard focus each time', async () => {
		renderComponent(IsoPicker, { props: defaultProps() });
		await waitFor(() => expect(screen.getByRole('option', { name: 'Movies' })).toBeInTheDocument());

		await fireEvent.keyDown(screen.getByRole('option', { name: 'Movies' }), { key: 'Enter' });
		await waitFor(() => expect(screen.getByRole('option', { name: 'inner.iso' })).toBeInTheDocument());
		expect(screen.getByText('Movies')).toBeInTheDocument();
		// The loading skeleton unmounted the "Movies" row that held focus — the
		// first row of the new (Movies) listing must now hold it.
		await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('option', { name: 'inner.iso' })));

		await fireEvent.keyDown(screen.getByRole('option', { name: 'inner.iso' }), { key: 'Backspace' });
		await waitFor(() => expect(screen.getByRole('option', { name: 'Movies' })).toBeInTheDocument());
		await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('option', { name: 'Movies' })));
	});

	it('announces the selection', async () => {
		renderComponent(IsoPicker, { props: defaultProps() });
		await waitFor(() => expect(screen.getByRole('option', { name: 'a.iso' })).toBeInTheDocument());

		await fireEvent.click(screen.getByRole('option', { name: 'a.iso' }));
		await waitFor(() => expect(screen.getByText('Selected a.iso, 1.0 GB.')).toBeInTheDocument());
	});

	it('disables a ripping ISO', async () => {
		renderComponent(IsoPicker, { props: defaultProps() });
		await waitFor(() => expect(screen.getByRole('option', { name: 'b.iso' })).toBeInTheDocument());

		const row = screen.getByRole('option', { name: 'b.iso' });
		expect(row).toHaveAttribute('aria-disabled', 'true');
		expect(row).toHaveAttribute('data-state', 'ripping');
		expect(screen.getByText('Ripping')).toBeInTheDocument();

		await fireEvent.click(row);
		expect(row).toHaveAttribute('aria-selected', 'false');
		expect(screen.getByText('Pick an ISO to start.')).toBeInTheDocument();
	});

	it('keeps Start rip disabled until an ISO is selected', async () => {
		renderComponent(IsoPicker, { props: defaultProps() });
		await waitFor(() => expect(screen.getByRole('option', { name: 'a.iso' })).toBeInTheDocument());

		expect(screen.getByRole('button', { name: 'Start rip' })).toBeDisabled();
		await fireEvent.click(screen.getByRole('option', { name: 'a.iso' }));
		expect(screen.getByRole('button', { name: 'Start rip' })).toBeEnabled();
	});

	it('starts with the chosen session and closes', async () => {
		startIsoRipMock.mockResolvedValue({ drive_id: 'drv_iso1' });
		const props = defaultProps();
		renderComponent(IsoPicker, { props });
		await waitFor(() => expect(screen.getByRole('option', { name: 'a.iso' })).toBeInTheDocument());

		await fireEvent.click(screen.getByRole('option', { name: 'a.iso' }));
		await fireEvent.change(screen.getByRole('combobox'), { target: { value: 'ses_1' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Start rip' }));

		await waitFor(() => expect(startIsoRipMock).toHaveBeenCalledWith('a.iso', 'ses_1'));
		expect(props.onstarted).toHaveBeenCalledWith('drv_iso1');

		// The success notice links to the new card (spec 7.2 / design frame 1n).
		const toast = toasts.value.at(-1);
		expect(toast).toMatchObject({
			tone: 'success',
			title: 'ISO rip started',
			body: 'a.iso is in the ripping queue.',
			link: { href: '/', label: 'View card' }
		});
	});

	it('shows the server message and stays open on 409', async () => {
		startIsoRipMock.mockRejectedValue(new Error('This ISO is already being ripped.'));
		const props = defaultProps();
		renderComponent(IsoPicker, { props });
		await waitFor(() => expect(screen.getByRole('option', { name: 'a.iso' })).toBeInTheDocument());

		await fireEvent.click(screen.getByRole('option', { name: 'a.iso' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Start rip' }));

		await waitFor(() => expect(screen.getByText("Couldn't start the rip")).toBeInTheDocument());
		expect(screen.getByText('This ISO is already being ripped.')).toBeInTheDocument();
		expect(props.onstarted).not.toHaveBeenCalled();
	});

	it('shows the setup note when the library is not configured', async () => {
		fetchIsoLibraryMock.mockRejectedValue(new ApiError(503, 'the ISO library is not configured', null));
		renderComponent(IsoPicker, { props: defaultProps() });

		await waitFor(() => expect(screen.getByText('Set up your ISO library first')).toBeInTheDocument());
		expect(screen.getByText(/bash devtools\/setup-dev\.sh up/)).toBeInTheDocument();
		expect(screen.getByText('Open Rip from ISO again and pick a file.')).toBeInTheDocument();
		expect(screen.getByText('Nothing to pick until the library is set up.')).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Start rip' })).not.toBeInTheDocument();
	});

	it('shows the empty-folder sentence', async () => {
		fetchIsoLibraryMock.mockResolvedValue({
			host_path: '/mnt/nas/iso',
			subpath: 'Extras',
			parent_subpath: '',
			entries: []
		});
		renderComponent(IsoPicker, { props: defaultProps() });

		await waitFor(() => expect(screen.getByText('This folder has no ISO files or folders.')).toBeInTheDocument());
	});

	it('shows a retryable error (not a spinning skeleton) when the library fails to load', async () => {
		fetchIsoLibraryMock.mockRejectedValueOnce(new Error('boom'));
		renderComponent(IsoPicker, { props: defaultProps() });

		await waitFor(() => expect(screen.getByText("Couldn't load the library")).toBeInTheDocument());
		expect(screen.getByText('boom')).toBeInTheDocument();

		// Retry reuses the refresh action; the base mock implementation (set in
		// beforeEach) resolves the next call normally.
		await fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
		await waitFor(() => expect(screen.getByRole('option', { name: 'a.iso' })).toBeInTheDocument());
		expect(screen.queryByText("Couldn't load the library")).not.toBeInTheDocument();
	});

	it('discards a stale response and keeps the rip path in sync with the displayed listing', async () => {
		let resolveMovies: (value: unknown) => void = () => {};
		let callCount = 0;
		fetchIsoLibraryMock.mockImplementation(() => {
			callCount += 1;
			if (callCount === 1) return Promise.resolve(ROOT_LISTING); // the initial root load
			if (callCount === 2) {
				// The "Movies" navigation — left pending so it resolves LAST.
				return new Promise((resolve) => {
					resolveMovies = resolve;
				});
			}
			// The third call: navigating back to Library while Movies is still in flight.
			return Promise.resolve(ROOT_LISTING);
		});
		startIsoRipMock.mockResolvedValue({ drive_id: 'drv_iso1' });

		renderComponent(IsoPicker, { props: defaultProps() });
		await waitFor(() => expect(screen.getByRole('option', { name: 'Movies' })).toBeInTheDocument());

		await fireEvent.click(screen.getByRole('option', { name: 'Movies' })); // call #2, pending
		await waitFor(() => expect(screen.getByText('Library')).toBeInTheDocument());
		await fireEvent.click(screen.getByText('Library')); // call #3, resolves immediately -> back to root
		await waitFor(() => expect(screen.getByRole('option', { name: 'a.iso' })).toBeInTheDocument());

		// The stale "Movies" response finally resolves — it must be discarded,
		// not clobber the (correct, newer) root listing already on screen.
		resolveMovies(MOVIES_LISTING);
		await new Promise((r) => setTimeout(r, 0));
		expect(screen.getByRole('option', { name: 'a.iso' })).toBeInTheDocument();
		expect(screen.queryByRole('option', { name: 'inner.iso' })).not.toBeInTheDocument();

		// Selecting from the (correctly) displayed root listing sends a path
		// built from the server's own subpath, not any stale local state.
		await fireEvent.click(screen.getByRole('option', { name: 'a.iso' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Start rip' }));
		await waitFor(() => expect(startIsoRipMock).toHaveBeenCalledWith('a.iso', null));
	});
});
