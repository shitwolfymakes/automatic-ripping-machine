import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import type { DirectoryListing, FileEntry } from '$lib/api/files';

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

import { fetchDirectory } from '$lib/api/files';
import * as auth from '$lib/stores/auth';
import { FilesBrowser } from '$lib/stores/files-browser.svelte';
import FilesTable from '../FilesTable.svelte';

const setRole = (auth as unknown as { __setRole: (r: string | null) => void }).__setRole;
const mockDir = vi.mocked(fetchDirectory);

const entry = (name: string, extra: Partial<FileEntry> = {}) =>
	({ name, type: 'file', size: 10, modified: '2026-01-01T00:00:00Z', category: 'other', ...extra }) as FileEntry;

function setup(entries: FileEntry[], selected: string[] = []) {
	const browser = new FilesBrowser();
	browser.current = { root: 'raw', subpath: 'src' };
	browser.listing = { entries } as DirectoryListing;
	browser.selectedKeys = new Set(selected);
	browser.loading = false;
	const cbs = { onrename: vi.fn(), ondelete: vi.fn(), onfixpermissions: vi.fn() };
	render(FilesTable, { browser, ...cbs });
	return { browser, ...cbs };
}

const rowNames = () => Array.from(document.querySelectorAll('.file-row-name')).map((n) => n.textContent);
const sortButton = (label: string) => screen.getByRole('button', { name: new RegExp(`^${label}`) });
const indicators = (label: string) => sortButton(label).querySelectorAll('.table-sort-indicator').length;

beforeEach(() => {
	mockDir.mockReset();
	setRole('admin');
});

afterEach(cleanup);

describe('FilesTable', () => {
	it('shows the select-all checkbox unchecked for an admin with nothing selected', () => {
		setup([entry('a'), entry('b')]);
		const boxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
		expect(boxes).toHaveLength(3);
		expect(boxes[0].checked).toBe(false);
	});

	it('checks select-all when every entry is selected', () => {
		setup([entry('a'), entry('b')], ['raw::src/a', 'raw::src/b']);
		const boxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
		expect(boxes[0].checked).toBe(true);
		expect(boxes[1].checked).toBe(true);
	});

	it('select-all selects every entry through the browser', async () => {
		const { browser } = setup([entry('a'), entry('b')]);
		await fireEvent.click(screen.getAllByRole('checkbox')[0]);
		expect(browser.selectedKeys).toEqual(new Set(['raw::src/a', 'raw::src/b']));
	});

	it('hides the select-all checkbox and the row actions for a non-admin', () => {
		setRole('viewer');
		setup([entry('a')]);
		expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
		expect(screen.queryByTitle('Rename')).toBeNull();
	});

	it('lists the rows in sorted order and marks the selected ones', () => {
		setup([entry('b'), entry('c'), entry('a')], ['raw::src/c']);
		expect(rowNames()).toEqual(['a', 'b', 'c']);
		const rows = Array.from(document.querySelectorAll('tbody tr')).map((r) => r.getAttribute('data-selected'));
		expect(rows).toEqual(['false', 'false', 'true']);
	});

	it('shows the indicator on Name only until another header is clicked', async () => {
		const { browser } = setup([entry('a')]);
		expect(indicators('Name')).toBe(1);
		expect(indicators('Size')).toBe(0);
		expect(indicators('Modified')).toBe(0);

		await fireEvent.click(sortButton('Size'));
		expect(browser.sortKey).toBe('size');
		expect(indicators('Name')).toBe(0);
		expect(indicators('Size')).toBe(1);

		await fireEvent.click(sortButton('Modified'));
		expect(browser.sortKey).toBe('modified');
		expect(indicators('Size')).toBe(0);
		expect(indicators('Modified')).toBe(1);
	});

	it('reverses the rows when the active sort header is clicked again', async () => {
		const { browser } = setup([entry('a'), entry('b')]);
		await fireEvent.click(sortButton('Name'));
		expect(browser.sortDir).toBe('desc');
		await tick();
		expect(rowNames()).toEqual(['b', 'a']);
	});

	it('navigates into a directory row through the browser', async () => {
		mockDir.mockResolvedValueOnce({ entries: [] } as unknown as DirectoryListing);
		setup([entry('sub', { type: 'directory' })]);
		await fireEvent.click(screen.getByText('sub'));
		await waitFor(() => expect(mockDir).toHaveBeenCalledWith('raw', 'src/sub'));
	});

	it('toggles a row selection through the browser', async () => {
		const { browser } = setup([entry('a'), entry('b')]);
		await fireEvent.click(screen.getAllByRole('checkbox')[2]);
		expect(browser.selectedKeys).toEqual(new Set(['raw::src/b']));
	});

	it('passes a rename with the entry name and the new name to onrename', async () => {
		const { onrename } = setup([entry('a')]);
		await fireEvent.click(screen.getByTitle('Rename'));
		await fireEvent.input(screen.getByDisplayValue('a'), { target: { value: 'z' } });
		await fireEvent.click(screen.getByTitle('Confirm'));
		expect(onrename).toHaveBeenCalledWith('a', 'z');
	});

	it('passes a delete with the entry name twice to ondelete', async () => {
		const { ondelete } = setup([entry('a')]);
		await fireEvent.click(screen.getByTitle('Delete'));
		expect(ondelete).toHaveBeenCalledWith('a', 'a');
	});

	it('passes a fix-permissions with the entry name twice to onfixpermissions', async () => {
		const { onfixpermissions } = setup([entry('a')]);
		await fireEvent.click(screen.getByTitle('Fix permissions'));
		expect(onfixpermissions).toHaveBeenCalledWith('a', 'a');
	});
});
