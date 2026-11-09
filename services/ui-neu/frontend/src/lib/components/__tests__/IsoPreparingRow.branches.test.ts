import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { renderComponent, screen, fireEvent, waitFor, cleanup } from '$lib/test-utils';

// Branch pins for IsoPreparingRow, beside IsoPreparingRow.test.ts. Every
// branch is reachable from the rendered component, so nothing is forced.

vi.mock('$lib/api/iso', () => ({ cancelIsoRip: vi.fn() }));
vi.mock('$lib/stores/toast.svelte', () => ({ addToast: vi.fn() }));
vi.mock('$lib/stores/auth', async () => {
	const { writable } = await import('svelte/store');
	const _admin = writable(true);
	return {
		isAdmin: { subscribe: _admin.subscribe },
		// Test-only helper, not part of the real module's public API.
		__setAdmin: (v: boolean) => _admin.set(v)
	};
});

import { cancelIsoRip } from '$lib/api/iso';
import { addToast } from '$lib/stores/toast.svelte';
import * as auth from '$lib/stores/auth';
import IsoPreparingRow from '../IsoPreparingRow.svelte';

const setAdmin = (auth as unknown as { __setAdmin: (v: boolean) => void }).__setAdmin;
const AT = '2026-10-02T14:00:00Z';

type Prepare = {
	drive_id: string;
	phase: string;
	updated_at: string;
	iso_name: string;
	iso_kind?: string;
	progress_pct?: number | null;
	current_file?: string | null;
};

function render(over: Partial<Prepare> = {}) {
	const prepare = { drive_id: 'drv_7', phase: 'scanning', updated_at: AT, iso_name: 'a.iso', ...over };
	// Loose props: the phase is an open string and iso_kind is optional.
	return renderComponent(IsoPreparingRow, { props: { prepare } as never });
}

describe('IsoPreparingRow branches', () => {
	beforeEach(() => {
		setAdmin(true);
		vi.mocked(cancelIsoRip).mockReset();
		vi.mocked(cancelIsoRip).mockResolvedValue(undefined as never);
		vi.mocked(addToast).mockReset();
	});
	afterEach(() => cleanup());

	describe('phase label', () => {
		it('labels an iso scan as Scanning image', () => {
			render({ iso_kind: 'iso', phase: 'scanning' });
			expect(screen.getByText('Scanning image')).toBeInTheDocument();
		});

		it('labels an iso extraction as Unpacking image', () => {
			render({ iso_kind: 'iso', phase: 'extracting' });
			expect(screen.getByText('Unpacking image')).toBeInTheDocument();
		});

		it('shows an unknown iso phase as is', () => {
			render({ iso_kind: 'iso', phase: 'verifying' });
			expect(screen.getByText('verifying')).toBeInTheDocument();
		});

		it('labels a folder scan as Scanning disc folder', () => {
			render({ iso_kind: 'folder', phase: 'scanning' });
			expect(screen.getByText('Scanning disc folder')).toBeInTheDocument();
		});

		it('labels a folder extraction as Unpacking image', () => {
			render({ iso_kind: 'folder', phase: 'extracting' });
			expect(screen.getByText('Unpacking image')).toBeInTheDocument();
		});

		it('shows an unknown folder phase as is', () => {
			render({ iso_kind: 'folder', phase: 'verifying' });
			expect(screen.getByText('verifying')).toBeInTheDocument();
		});
	});

	describe('cancel', () => {
		it('shows Cancel to an admin', () => {
			render();
			expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
		});

		it('hides Cancel from a non-admin', () => {
			setAdmin(false);
			render();
			expect(screen.queryByRole('button')).toBeNull();
		});

		it('shows Cancelling and disables the button while in flight', async () => {
			vi.mocked(cancelIsoRip).mockReturnValue(new Promise(() => {}) as never);
			render();
			await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
			const btn = screen.getByRole('button', { name: 'Cancelling...' });
			expect(btn).toBeDisabled();
			expect(cancelIsoRip).toHaveBeenCalledWith('drv_7');
		});

		it('restores the button without a toast on success', async () => {
			render();
			await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
			await waitFor(() => expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled());
			expect(addToast).not.toHaveBeenCalled();
		});

		it('toasts the Error message and re-enables the button on failure', async () => {
			vi.mocked(cancelIsoRip).mockRejectedValue(new Error('drive busy'));
			render();
			await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
			await waitFor(() =>
				expect(addToast).toHaveBeenCalledWith({ tone: 'error', title: 'Cancel failed', body: 'drive busy' })
			);
			await waitFor(() => expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled());
		});

		it('toasts Unknown error when the failure is not an Error', async () => {
			vi.mocked(cancelIsoRip).mockRejectedValue('nope');
			render();
			await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
			await waitFor(() =>
				expect(addToast).toHaveBeenCalledWith({ tone: 'error', title: 'Cancel failed', body: 'Unknown error' })
			);
			await waitFor(() => expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled());
		});
	});

	describe('progress', () => {
		it('shows the progress bar when progress_pct is set', () => {
			const { container } = render({ progress_pct: 30 });
			expect(screen.getByText('30%')).toBeInTheDocument();
			expect(container.querySelector('[data-indeterminate="true"]')).toBeNull();
		});

		it('shows the indeterminate track when progress_pct is null', () => {
			const { container } = render({ progress_pct: null });
			expect(container.querySelector('[data-indeterminate="true"]')).not.toBeNull();
		});

		it('shows the current file line with the file as its title', () => {
			const { container } = render({ current_file: 'BDMV/STREAM/00002.m2ts' });
			const line = container.querySelector('.iso-preparing-row-file');
			expect(line).toHaveTextContent('BDMV/STREAM/00002.m2ts');
			expect(line).toHaveAttribute('title', 'BDMV/STREAM/00002.m2ts');
		});

		it('shows no file line without a current_file', () => {
			const { container } = render({ current_file: null });
			expect(container.querySelector('.iso-preparing-row-file')).toBeNull();
		});
	});
});
