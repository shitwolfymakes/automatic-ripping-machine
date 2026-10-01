import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent, waitFor, within } from '$lib/test-utils';
import { ApiError } from '$lib/api/client';
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

afterEach(() => cleanup());

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

	it('opens a folder with Enter and goes up with Backspace', async () => {
		renderComponent(IsoPicker, { props: defaultProps() });
		await waitFor(() => expect(screen.getByRole('option', { name: 'Movies' })).toBeInTheDocument());

		await fireEvent.keyDown(screen.getByRole('option', { name: 'Movies' }), { key: 'Enter' });
		await waitFor(() => expect(screen.getByRole('option', { name: 'inner.iso' })).toBeInTheDocument());
		expect(screen.getByText('Movies')).toBeInTheDocument();

		await fireEvent.keyDown(screen.getByRole('option', { name: 'inner.iso' }), { key: 'Backspace' });
		await waitFor(() => expect(screen.getByRole('option', { name: 'Movies' })).toBeInTheDocument());
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
});
