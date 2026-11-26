import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/svelte';
import NewFolderRow from '../NewFolderRow.svelte';
import NewFolderRowHarness from './NewFolderRowHarness.svelte';

afterEach(cleanup);

function setup() {
	const onconfirm = vi.fn();
	const oncancel = vi.fn();
	render(NewFolderRow, { name: 'abc', onconfirm, oncancel });
	return { onconfirm, oncancel, input: screen.getByPlaceholderText('Folder name') as HTMLInputElement };
}

describe('NewFolderRow', () => {
	it('shows the bound name in the input', () => {
		expect(setup().input.value).toBe('abc');
	});

	it('writes typing back to the bound name', async () => {
		render(NewFolderRowHarness, { onconfirm: vi.fn(), oncancel: vi.fn() });
		const input = screen.getByPlaceholderText('Folder name') as HTMLInputElement;
		await fireEvent.input(input, { target: { value: 'Movies' } });
		expect(screen.getByTestId('bound-name').textContent).toBe('Movies');
	});

	it('calls onconfirm on Enter only', async () => {
		const { onconfirm, oncancel, input } = setup();
		await fireEvent.keyDown(input, { key: 'Enter' });
		expect(onconfirm).toHaveBeenCalledTimes(1);
		expect(oncancel).not.toHaveBeenCalled();
	});

	it('calls oncancel on Escape only', async () => {
		const { onconfirm, oncancel, input } = setup();
		await fireEvent.keyDown(input, { key: 'Escape' });
		expect(oncancel).toHaveBeenCalledTimes(1);
		expect(onconfirm).not.toHaveBeenCalled();
	});

	it('calls neither callback on another key', async () => {
		const { onconfirm, oncancel, input } = setup();
		await fireEvent.keyDown(input, { key: 'a' });
		expect(onconfirm).not.toHaveBeenCalled();
		expect(oncancel).not.toHaveBeenCalled();
	});

	it('calls onconfirm from the Create button', async () => {
		const { onconfirm, oncancel } = setup();
		await fireEvent.click(screen.getByTitle('Create'));
		expect(onconfirm).toHaveBeenCalledTimes(1);
		expect(oncancel).not.toHaveBeenCalled();
	});

	it('calls oncancel from the Cancel button', async () => {
		const { onconfirm, oncancel } = setup();
		await fireEvent.click(screen.getByTitle('Cancel'));
		expect(oncancel).toHaveBeenCalledTimes(1);
		expect(onconfirm).not.toHaveBeenCalled();
	});
});
