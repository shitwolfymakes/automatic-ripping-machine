import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/svelte';
import { tick } from 'svelte';
import type { DirectoryListing } from '$lib/api/files';

vi.mock('$lib/api/files', () => ({ fetchRoots: vi.fn(), fetchDirectory: vi.fn() }));

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		// Test-only helper, not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});

// Mutable copy so a test can switch the maintenance UI the shipped flag hides.
vi.mock('$lib/features', async (importOriginal) => {
	const actual = await importOriginal<typeof import('$lib/features')>();
	return { ...actual, features: { ...actual.features } };
});

import { fetchDirectory } from '$lib/api/files';
import * as auth from '$lib/stores/auth';
import { features } from '$lib/features';
import { FilesBrowser } from '$lib/stores/files-browser.svelte';
import FilesToolbar from '../FilesToolbar.svelte';

const setRole = (auth as unknown as { __setRole: (r: string | null) => void }).__setRole;
const mockDir = vi.mocked(fetchDirectory);

function setup(selected: string[] = []) {
	const browser = new FilesBrowser();
	browser.current = { root: 'raw', subpath: 'src' };
	browser.selectedKeys = new Set(selected);
	browser.loading = false;
	const cbs = {
		onmove: vi.fn(),
		onbulkdelete: vi.fn(),
		onorphans: vi.fn(),
		oncleanup: vi.fn(),
		onnewfolder: vi.fn()
	};
	render(FilesToolbar, { browser, ...cbs });
	return { browser, ...cbs };
}

beforeEach(() => {
	mockDir.mockReset();
	setRole('admin');
	(features as { maintenance: boolean }).maintenance = true;
});

afterEach(cleanup);

describe('FilesToolbar', () => {
	it('shows only Refresh for a non-admin', () => {
		setRole('viewer');
		setup(['raw::a']);
		expect(screen.getByTitle('Refresh')).toBeTruthy();
		expect(screen.queryByTitle('New folder')).toBeNull();
		expect(screen.queryByTitle('Orphan folders')).toBeNull();
		expect(screen.queryByText('Move 1')).toBeNull();
	});

	it('hides the maintenance buttons when maintenance is off', () => {
		(features as { maintenance: boolean }).maintenance = false;
		setup();
		expect(screen.queryByTitle('Orphan folders')).toBeNull();
		expect(screen.queryByTitle('Clean up transcoder jobs')).toBeNull();
		expect(screen.getByTitle('New folder')).toBeTruthy();
	});

	it('shows the maintenance buttons and no bulk buttons with no selection', () => {
		setup();
		expect(screen.getByTitle('Orphan folders')).toBeTruthy();
		expect(screen.getByTitle('Clean up transcoder jobs')).toBeTruthy();
		expect(screen.queryByText(/^Move /)).toBeNull();
		expect(screen.queryByText(/^Delete /)).toBeNull();
	});

	it('shows the selection count in the Move and Delete labels', () => {
		setup(['raw::a', 'raw::b']);
		expect(screen.getByText('Move 2')).toBeTruthy();
		expect(screen.getByText('Delete 2')).toBeTruthy();
	});

	it('calls each callback from its button', async () => {
		const cbs = setup(['raw::a']);
		await fireEvent.click(screen.getByText('Move 1'));
		await fireEvent.click(screen.getByText('Delete 1'));
		await fireEvent.click(screen.getByTitle('Orphan folders'));
		await fireEvent.click(screen.getByTitle('Clean up transcoder jobs'));
		await fireEvent.click(screen.getByTitle('New folder'));
		expect(cbs.onmove).toHaveBeenCalledTimes(1);
		expect(cbs.onbulkdelete).toHaveBeenCalledTimes(1);
		expect(cbs.onorphans).toHaveBeenCalledTimes(1);
		expect(cbs.oncleanup).toHaveBeenCalledTimes(1);
		expect(cbs.onnewfolder).toHaveBeenCalledTimes(1);
	});

	it('disables Move, Delete and New folder on a read-only mount and retitles New folder', () => {
		const browser = new FilesBrowser();
		browser.current = { root: 'raw', subpath: 'src' };
		browser.selectedKeys = new Set(['raw::a']);
		browser.loading = false;
		browser.isReadonly = true;
		render(FilesToolbar, {
			browser,
			onmove: vi.fn(),
			onbulkdelete: vi.fn(),
			onorphans: vi.fn(),
			oncleanup: vi.fn(),
			onnewfolder: vi.fn()
		});
		expect((screen.getByText('Move 1').closest('button') as HTMLButtonElement).disabled).toBe(true);
		expect((screen.getByText('Delete 1').closest('button') as HTMLButtonElement).disabled).toBe(true);
		const nf = screen.getByTitle('Read-only mount') as HTMLButtonElement;
		expect(nf.disabled).toBe(true);
		expect(screen.queryByTitle('New folder')).toBeNull();
	});

	it('enables the write buttons when the mount is writable', () => {
		setup(['raw::a']);
		expect((screen.getByText('Move 1').closest('button') as HTMLButtonElement).disabled).toBe(false);
		expect((screen.getByTitle('New folder') as HTMLButtonElement).disabled).toBe(false);
	});

	it('disables Refresh and spins its icon while loading', () => {
		const browser = new FilesBrowser();
		browser.current = { root: 'raw', subpath: 'src' };
		browser.loading = true;
		render(FilesToolbar, {
			browser,
			onmove: vi.fn(),
			onbulkdelete: vi.fn(),
			onorphans: vi.fn(),
			oncleanup: vi.fn(),
			onnewfolder: vi.fn()
		});
		const refresh = screen.getByTitle('Refresh') as HTMLButtonElement;
		expect(refresh.disabled).toBe(true);
		expect(refresh.querySelector('svg.spin')).not.toBeNull();
	});

	it('reloads the current directory when Refresh is clicked', async () => {
		mockDir.mockResolvedValue({ entries: [] } as unknown as DirectoryListing);
		setup();
		const refresh = screen.getByTitle('Refresh') as HTMLButtonElement;
		expect(refresh.disabled).toBe(false);
		expect(refresh.querySelector('svg.spin')).toBeNull();
		await fireEvent.click(refresh);
		await tick();
		expect(mockDir).toHaveBeenCalledWith('raw', 'src');
	});
});
