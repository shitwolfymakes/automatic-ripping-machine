import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent, waitFor } from '$lib/testing/render';
import { toasts, dismissToast } from '$lib/stores/toast.svelte';
import IsoPicker from '../IsoPicker.svelte';

// Branch pins for IsoPicker, beside IsoPicker.test.ts and
// IsoPickerFolders.test.ts. The branches below cannot be reached from the
// rendered picker, so nothing here forces them:
// - The `?? []` fallback behind the ISO rows: it reads `listing`, which is
//   always set once a row exists to be clicked or keyed.
// - The `?? []` fallback behind the filtered folder rows: it is only read from
//   the ready snippet and a row's key handler, and both need a loaded folder
//   listing.
// - Start's guard on an unset selected path: the Start button is disabled until
//   something is selected, and a disabled button never calls the handler. Only
//   the in-flight half of the guard is reachable (two clicks before the DOM
//   disables the button).

const fetchIsoFoldersMock = vi.fn();
const fetchIsoLibraryMock = vi.fn();
const startIsoRipMock = vi.fn();
vi.mock('$lib/api/iso', () => ({
	fetchIsoFolders: (...args: unknown[]) => fetchIsoFoldersMock(...args),
	fetchIsoLibrary: (...args: unknown[]) => fetchIsoLibraryMock(...args),
	startIsoRip: (...args: unknown[]) => startIsoRipMock(...args),
	cancelIsoRip: vi.fn()
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
		{ name: 'Sub', kind: 'folder', size_bytes: null, modified_at: null, ripping: false },
		{ name: 'inner.iso', kind: 'iso', size_bytes: 2000000000, modified_at: '2026-01-01T00:00:00Z', ripping: false }
	]
};

const SUB_LISTING = {
	host_path: '/mnt/nas/iso',
	subpath: 'Movies/Sub',
	parent_subpath: 'Movies',
	entries: [
		{ name: 'deep.iso', kind: 'iso', size_bytes: 1000000000, modified_at: '2026-01-01T00:00:00Z', ripping: false }
	]
};

const FOLDERS = {
	host_path: '/mnt/nas/iso',
	partial: false,
	entries: [
		{ path: 'Half Baked', name: 'Half Baked', parent: '', disc_type: 'dvd', ripping: true },
		{ path: 'LOTR/Disc 1', name: 'Disc 1', parent: 'LOTR', disc_type: 'bluray', ripping: false },
		{ path: 'Movies/MirrorMask', name: 'MirrorMask', parent: 'Movies', disc_type: 'bluray', ripping: false }
	]
};

function isoProps() {
	return { open: true, onclose: vi.fn(), onstarted: vi.fn() };
}

function folderProps() {
	return { open: true, mode: 'folder' as const, onclose: vi.fn(), onstarted: vi.fn() };
}

function option(name: string): HTMLElement {
	return screen.getByRole('option', { name });
}

async function renderIso() {
	const p = isoProps();
	renderComponent(IsoPicker, { props: p });
	await waitFor(() => expect(option('a.iso')).toBeInTheDocument());
	return p;
}

async function renderFolders() {
	const p = folderProps();
	renderComponent(IsoPicker, { props: p });
	await waitFor(() => expect(option('Disc 1')).toBeInTheDocument());
	return p;
}

function deferred<T>() {
	let resolve: (value: T) => void = () => {};
	let reject: (reason: unknown) => void = () => {};
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

async function flush() {
	await new Promise((r) => setTimeout(r, 0));
}

beforeEach(() => {
	fetchIsoFoldersMock.mockReset().mockResolvedValue(FOLDERS);
	startIsoRipMock.mockReset();
	fetchSessionsMock.mockReset().mockResolvedValue([]);
	fetchIsoLibraryMock.mockReset().mockImplementation((subpath?: string) => {
		if (!subpath) return Promise.resolve(ROOT_LISTING);
		if (subpath === 'Movies') return Promise.resolve(MOVIES_LISTING);
		if (subpath === 'Movies/Sub') return Promise.resolve(SUB_LISTING);
		return Promise.reject(new Error(`unexpected subpath: ${subpath}`));
	});
});

afterEach(() => {
	for (const t of toasts.value) dismissToast(t.id);
	cleanup();
});

describe('IsoPicker ISO list keyboard handling', () => {
	it('moves focus down and up, and stays put at the last and first rows', async () => {
		await renderIso();

		await fireEvent.keyDown(option('Movies'), { key: 'ArrowDown' });
		expect(document.activeElement).toBe(option('a.iso'));

		await fireEvent.keyDown(option('c.iso'), { key: 'ArrowDown' });
		expect(document.activeElement).toBe(option('a.iso'));

		await fireEvent.keyDown(option('b.iso'), { key: 'ArrowUp' });
		expect(document.activeElement).toBe(option('a.iso'));

		await fireEvent.keyDown(option('Movies'), { key: 'ArrowUp' });
		expect(document.activeElement).toBe(option('a.iso'));
	});

	it('jumps to the first and last rows with Home and End', async () => {
		await renderIso();

		await fireEvent.keyDown(option('b.iso'), { key: 'End' });
		expect(document.activeElement).toBe(option('c.iso'));

		await fireEvent.keyDown(option('b.iso'), { key: 'Home' });
		expect(document.activeElement).toBe(option('Movies'));
	});

	it('opens a folder with Space and selects an ISO with Space', async () => {
		await renderIso();

		await fireEvent.keyDown(option('a.iso'), { key: ' ' });
		expect(option('a.iso')).toHaveAttribute('aria-selected', 'true');

		await fireEvent.keyDown(option('Movies'), { key: ' ' });
		await waitFor(() => expect(option('inner.iso')).toBeInTheDocument());
		expect(fetchIsoLibraryMock).toHaveBeenLastCalledWith('Movies');
	});

	it('goes up from a folder with ArrowLeft and with Backspace', async () => {
		await renderIso();
		await fireEvent.keyDown(option('Movies'), { key: 'Enter' });
		await waitFor(() => expect(option('inner.iso')).toBeInTheDocument());

		await fireEvent.keyDown(option('inner.iso'), { key: 'ArrowLeft' });
		await waitFor(() => expect(option('a.iso')).toBeInTheDocument());
		expect(fetchIsoLibraryMock).toHaveBeenLastCalledWith('');

		await fireEvent.keyDown(option('Movies'), { key: 'Enter' });
		await waitFor(() => expect(option('inner.iso')).toBeInTheDocument());
		await fireEvent.keyDown(option('inner.iso'), { key: 'Backspace' });
		await waitFor(() => expect(option('a.iso')).toBeInTheDocument());
	});

	it('does nothing on Backspace and ArrowLeft at the library root, where there is no parent', async () => {
		await renderIso();
		const calls = fetchIsoLibraryMock.mock.calls.length;

		const backspace = await fireEvent.keyDown(option('a.iso'), { key: 'Backspace' });
		const left = await fireEvent.keyDown(option('a.iso'), { key: 'ArrowLeft' });
		await flush();

		// The keys are still claimed (default prevented) but load nothing.
		expect(backspace).toBe(false);
		expect(left).toBe(false);
		expect(fetchIsoLibraryMock).toHaveBeenCalledTimes(calls);
	});

	it('ignores a key it does not handle and leaves the default action alone', async () => {
		await renderIso();

		const notPrevented = await fireEvent.keyDown(option('a.iso'), { key: 'x' });

		expect(notPrevented).toBe(true);
		expect(option('a.iso')).toHaveAttribute('aria-selected', 'false');
	});
});

describe('IsoPicker ISO mode states', () => {
	it('shows a ripping ISO with its chip and selects nothing on Enter', async () => {
		await renderIso();
		const row = option('b.iso');
		expect(row).toHaveAttribute('aria-disabled', 'true');
		expect(screen.getByText('Ripping')).toBeInTheDocument();

		await fireEvent.keyDown(row, { key: 'Enter' });

		expect(row).toHaveAttribute('aria-selected', 'false');
		expect(screen.getByText('Pick an ISO to start.')).toBeInTheDocument();
	});

	it('shows -- for an ISO with no size and no date', async () => {
		fetchIsoLibraryMock.mockResolvedValue({
			...ROOT_LISTING,
			entries: [{ name: 'odd.iso', kind: 'iso', size_bytes: null, modified_at: null, ripping: false }]
		});
		renderComponent(IsoPicker, { props: isoProps() });

		expect(await screen.findByText('-- · --')).toBeInTheDocument();
	});

	it('goes back to a parent segment from the breadcrumb', async () => {
		await renderIso();
		await fireEvent.click(option('Movies'));
		await waitFor(() => expect(option('Sub')).toBeInTheDocument());
		await fireEvent.click(option('Sub'));
		await waitFor(() => expect(option('deep.iso')).toBeInTheDocument());
		expect(fetchIsoLibraryMock).toHaveBeenLastCalledWith('Movies/Sub');

		await fireEvent.click(screen.getByRole('button', { name: 'Movies' }));

		await waitFor(() => expect(option('inner.iso')).toBeInTheDocument());
		expect(fetchIsoLibraryMock).toHaveBeenLastCalledWith('Movies');
	});

	it('reloads the current folder with the Refresh button', async () => {
		await renderIso();
		await fireEvent.click(option('Movies'));
		await waitFor(() => expect(option('inner.iso')).toBeInTheDocument());

		await fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));

		await waitFor(() => expect(fetchIsoLibraryMock).toHaveBeenCalledTimes(3));
		expect(fetchIsoLibraryMock).toHaveBeenLastCalledWith('Movies');
	});

	it('updates the session options in place when the picker reopens with fresh session objects', async () => {
		const sessions = [
			{ id: 'ses_1', name: 'Movie', media_type: 'movie', is_builtin: false },
			{ id: 'ses_2', name: 'TV', media_type: 'tv', is_builtin: false }
		];
		fetchSessionsMock.mockResolvedValueOnce(sessions.map((s) => ({ ...s })));
		const p = isoProps();
		const { rerender } = renderComponent(IsoPicker, { props: p });
		await waitFor(() => expect(screen.getByRole('option', { name: 'Movie', hidden: true })).toBeInTheDocument());

		fetchSessionsMock.mockResolvedValueOnce(
			sessions.map((s) => ({ ...s, name: s.id === 'ses_1' ? 'Movie 2' : s.name }))
		);
		await rerender({ ...p, open: false });
		await rerender({ ...p, open: true });

		await waitFor(() => expect(screen.getByRole('option', { name: 'Movie 2', hidden: true })).toBeInTheDocument());
		expect(screen.getByRole('combobox').querySelectorAll('option')).toHaveLength(3);
	});

	it('shows the generic message when the library load rejects with a non-Error', async () => {
		fetchIsoLibraryMock.mockRejectedValue('nope');
		renderComponent(IsoPicker, { props: isoProps() });

		expect(await screen.findByText('Could not load the library.')).toBeInTheDocument();
	});

	it('keeps the session list empty when fetching sessions fails', async () => {
		fetchSessionsMock.mockRejectedValue(new Error('down'));
		await renderIso();

		await flush();

		expect(screen.getAllByRole('option', { name: 'Automatic', hidden: true })).toHaveLength(1);
		expect(screen.getByRole('combobox').querySelectorAll('option')).toHaveLength(1);
	});
});

describe('IsoPicker starting a rip', () => {
	it('ignores a second click while the first start is still in flight', async () => {
		const pending = deferred<{ drive_id: string }>();
		startIsoRipMock.mockReturnValue(pending.promise);
		const p = await renderIso();
		await fireEvent.click(option('a.iso'));

		const start = screen.getByRole('button', { name: 'Start rip' });
		// Two synchronous clicks: the DOM has not disabled the button yet.
		start.click();
		start.click();
		pending.resolve({ drive_id: 'drv_1' });

		await waitFor(() => expect(p.onstarted).toHaveBeenCalledWith('drv_1'));
		expect(startIsoRipMock).toHaveBeenCalledTimes(1);
	});

	it('shows the generic message when the start rejects with a non-Error', async () => {
		startIsoRipMock.mockRejectedValue('nope');
		await renderIso();
		await fireEvent.click(option('a.iso'));

		await fireEvent.click(screen.getByRole('button', { name: 'Start rip' }));

		expect(await screen.findByText('Could not start the rip.')).toBeInTheDocument();
	});

	it('titles the success toast "Folder rip started" in folder mode', async () => {
		startIsoRipMock.mockResolvedValue({ drive_id: 'drv_1' });
		await renderFolders();
		await fireEvent.click(option('Disc 1'));

		await fireEvent.click(screen.getByRole('button', { name: 'Start rip' }));

		await waitFor(() => expect(toasts.value.at(-1)).toMatchObject({ title: 'Folder rip started' }));
	});
});

describe('IsoPicker folder list keyboard handling', () => {
	it('moves focus down and up, and stays put at the ends', async () => {
		await renderFolders();

		await fireEvent.keyDown(option('Half Baked'), { key: 'ArrowDown' });
		expect(document.activeElement).toBe(option('Disc 1'));

		await fireEvent.keyDown(option('MirrorMask'), { key: 'ArrowDown' });
		expect(document.activeElement).toBe(option('Disc 1'));

		await fireEvent.keyDown(option('MirrorMask'), { key: 'ArrowUp' });
		expect(document.activeElement).toBe(option('Disc 1'));

		await fireEvent.keyDown(option('Half Baked'), { key: 'ArrowUp' });
		expect(document.activeElement).toBe(option('Disc 1'));
	});

	it('jumps to the first and last rows with Home and End', async () => {
		await renderFolders();

		await fireEvent.keyDown(option('Disc 1'), { key: 'End' });
		expect(document.activeElement).toBe(option('MirrorMask'));

		await fireEvent.keyDown(option('Disc 1'), { key: 'Home' });
		expect(document.activeElement).toBe(option('Half Baked'));
	});

	it('selects a folder with Enter and with Space', async () => {
		await renderFolders();

		await fireEvent.keyDown(option('Disc 1'), { key: 'Enter' });
		expect(option('Disc 1')).toHaveAttribute('aria-selected', 'true');

		await fireEvent.keyDown(option('MirrorMask'), { key: ' ' });
		expect(option('MirrorMask')).toHaveAttribute('aria-selected', 'true');
		expect(option('Disc 1')).toHaveAttribute('aria-selected', 'false');
	});

	it('ignores a key it does not handle and leaves the default action alone', async () => {
		await renderFolders();

		const notPrevented = await fireEvent.keyDown(option('Disc 1'), { key: 'x' });

		expect(notPrevented).toBe(true);
		expect(option('Disc 1')).toHaveAttribute('aria-selected', 'false');
	});
});

describe('IsoPicker folder mode states', () => {
	it('shows the empty-library message', async () => {
		fetchIsoFoldersMock.mockResolvedValue({ ...FOLDERS, entries: [] });
		renderComponent(IsoPicker, { props: folderProps() });

		expect(await screen.findByText('No disc folders in the library.')).toBeInTheDocument();
	});

	it('shows the error and reloads on Retry', async () => {
		fetchIsoFoldersMock.mockRejectedValueOnce(new Error('boom'));
		renderComponent(IsoPicker, { props: folderProps() });

		expect(await screen.findByText("Couldn't load the library")).toBeInTheDocument();
		expect(screen.getByText('boom')).toBeInTheDocument();

		await fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

		await waitFor(() => expect(option('Disc 1')).toBeInTheDocument());
	});

	it('notes a partial listing', async () => {
		fetchIsoFoldersMock.mockResolvedValue({ ...FOLDERS, partial: true });
		renderComponent(IsoPicker, { props: folderProps() });

		expect(await screen.findByText(/stopped searching partway/)).toBeInTheDocument();
	});

	it('says so when the filter matches no folder', async () => {
		await renderFolders();

		await fireEvent.input(screen.getByRole('searchbox', { name: 'Filter folders' }), {
			target: { value: 'zzz' }
		});

		expect(screen.getByText('No folder matches "zzz".')).toBeInTheDocument();
		expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
	});

	it('marks a ripping folder with a chip and selects nothing on click or Enter', async () => {
		await renderFolders();
		const row = option('Half Baked');

		expect(row).toHaveAttribute('aria-disabled', 'true');
		expect(row).toHaveAttribute('data-state', 'ripping');
		expect(screen.getByText('Ripping')).toBeInTheDocument();

		await fireEvent.click(row);
		await fireEvent.keyDown(row, { key: 'Enter' });

		expect(row).toHaveAttribute('aria-selected', 'false');
		expect(screen.getByText('Pick a disc folder to start.')).toBeInTheDocument();
	});

	it('lists a folder with no parent without a parent line', async () => {
		await renderFolders();

		expect(option('Half Baked').querySelector('.iso-picker-row-parent')).toBeNull();
		expect(option('Disc 1').querySelector('.iso-picker-row-parent')).not.toBeNull();
	});

	it('discards a folder listing that resolves after a newer load started', async () => {
		const first = deferred<typeof FOLDERS>();
		fetchIsoFoldersMock.mockReturnValueOnce(first.promise).mockResolvedValueOnce(FOLDERS);
		renderComponent(IsoPicker, { props: folderProps() });

		await fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
		await waitFor(() => expect(option('Disc 1')).toBeInTheDocument());

		first.resolve({ ...FOLDERS, entries: [{ ...FOLDERS.entries[2], name: 'Stale', path: 'Stale' }] });
		await flush();

		expect(option('Disc 1')).toBeInTheDocument();
		expect(screen.queryByRole('option', { name: 'Stale' })).not.toBeInTheDocument();
	});

	it('discards a failure that rejects after a newer load started', async () => {
		const first = deferred<typeof FOLDERS>();
		fetchIsoFoldersMock.mockReturnValueOnce(first.promise).mockResolvedValueOnce(FOLDERS);
		renderComponent(IsoPicker, { props: folderProps() });

		await fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
		await waitFor(() => expect(option('Disc 1')).toBeInTheDocument());

		first.reject(new Error('late failure'));
		await flush();

		expect(option('Disc 1')).toBeInTheDocument();
		expect(screen.queryByText("Couldn't load the library")).not.toBeInTheDocument();
	});
});
