import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent, waitFor } from '$lib/test-utils';
import IsoPicker from '../IsoPicker.svelte';

const fetchIsoFoldersMock = vi.fn();
const fetchIsoLibraryMock = vi.fn();
const startIsoRipMock = vi.fn();
vi.mock('$lib/api/iso', () => ({
	fetchIsoFolders: (...args: unknown[]) => fetchIsoFoldersMock(...args),
	fetchIsoLibrary: (...args: unknown[]) => fetchIsoLibraryMock(...args),
	startIsoRip: (...args: unknown[]) => startIsoRipMock(...args),
	cancelIsoRip: vi.fn()
}));
vi.mock('$lib/api/sessions', () => ({ fetchSessions: () => Promise.resolve([]) }));

const FOLDERS = {
	host_path: '/mnt/nas/iso',
	partial: false,
	entries: [
		{ path: 'Half Baked', name: 'Half Baked', parent: '', disc_type: 'dvd', ripping: true },
		{
			path: 'LOTR/Extended/Fellowship/Disc 1',
			name: 'Disc 1',
			parent: 'LOTR/Extended/Fellowship',
			disc_type: 'bluray',
			ripping: false
		},
		{
			path: 'Movies/Fantasy/MirrorMask (2005)',
			name: 'MirrorMask (2005)',
			parent: 'Movies/Fantasy',
			disc_type: 'bluray',
			ripping: false
		}
	]
};

function props() {
	return { open: true, mode: 'folder' as const, onclose: vi.fn(), onstarted: vi.fn() };
}

beforeEach(() => {
	fetchIsoFoldersMock.mockReset().mockResolvedValue(FOLDERS);
	fetchIsoLibraryMock.mockReset();
	startIsoRipMock.mockReset().mockResolvedValue({ drive_id: 'drv_1' });
});
afterEach(() => cleanup());

describe('IsoPicker in folder mode', () => {
	it('lists every disc folder flat, with its parent path and disc type', async () => {
		renderComponent(IsoPicker, { props: props() });
		expect(await screen.findByText('Disc 1')).toBeInTheDocument();
		expect(screen.getByRole('heading', { name: 'Rip from folder' })).toBeInTheDocument();
		expect(screen.getByText('LOTR/Extended/Fellowship')).toBeInTheDocument();
		expect(screen.getByText('MirrorMask (2005)')).toBeInTheDocument();
		expect(screen.getAllByText('BD')).toHaveLength(2);
		expect(screen.getByText('DVD')).toBeInTheDocument();
		expect(fetchIsoLibraryMock).not.toHaveBeenCalled();
	});

	it('marks a folder that is already ripping and does not select it', async () => {
		renderComponent(IsoPicker, { props: props() });
		await fireEvent.click(await screen.findByRole('option', { name: 'Half Baked' }));
		expect(screen.getByRole('option', { name: 'Half Baked' })).toHaveAttribute('aria-disabled', 'true');
		expect(screen.getByRole('button', { name: 'Start rip' })).toBeDisabled();
	});

	it('filters on any part of the path', async () => {
		renderComponent(IsoPicker, { props: props() });
		await screen.findByText('Disc 1');
		await fireEvent.input(screen.getByRole('searchbox', { name: 'Filter folders' }), {
			target: { value: 'fellow' }
		});
		expect(screen.getByText('Disc 1')).toBeInTheDocument();
		expect(screen.queryByText('MirrorMask (2005)')).toBeNull();
	});

	it('starts a rip of the selected folder by its library path', async () => {
		const p = props();
		renderComponent(IsoPicker, { props: p });
		await fireEvent.click(await screen.findByRole('option', { name: 'Disc 1' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Start rip' }));
		await waitFor(() => expect(startIsoRipMock).toHaveBeenCalledWith('LOTR/Extended/Fellowship/Disc 1', null));
		expect(p.onstarted).toHaveBeenCalledWith('drv_1');
	});

	it('says when the listing was cut short', async () => {
		fetchIsoFoldersMock.mockResolvedValue({ ...FOLDERS, partial: true });
		renderComponent(IsoPicker, { props: props() });
		expect(await screen.findByText(/stopped searching/i)).toBeInTheDocument();
	});
});
