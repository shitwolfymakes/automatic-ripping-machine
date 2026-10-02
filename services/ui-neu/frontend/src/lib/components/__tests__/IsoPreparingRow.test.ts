import { describe, it, expect, afterEach, vi } from 'vitest';
import { fireEvent } from '@testing-library/svelte';
import { renderComponent, cleanup } from '$lib/test-utils';

vi.mock('$lib/api/iso', () => ({ cancelIsoRip: vi.fn(() => Promise.resolve()) }));
vi.mock('$lib/stores/auth', async () => {
	const { readable } = await import('svelte/store');
	return { isAdmin: readable(true) };
});

import { cancelIsoRip } from '$lib/api/iso';
import IsoPreparingRow from '../IsoPreparingRow.svelte';

const AT = '2026-10-02T14:00:00Z';

describe('IsoPreparingRow', () => {
	afterEach(() => cleanup());

	it('shows the unpack progress and the file being extracted', () => {
		const { getByText, container } = renderComponent(IsoPreparingRow, {
			props: {
				prepare: {
					drive_id: 'drv_1',
					phase: 'extracting',
					progress_pct: 42,
					current_file: 'BDMV/STREAM/00001.m2ts',
					updated_at: AT,
					iso_name: 'MirrorMask.iso'
				}
			}
		});
		expect(getByText('Unpacking image')).toBeInTheDocument();
		expect(getByText('BDMV/STREAM/00001.m2ts')).toBeInTheDocument();
		expect(getByText('42%')).toBeInTheDocument();
		expect(container.querySelector('.chip')).toHaveAttribute('title', 'MirrorMask.iso');
	});

	it('shows an indeterminate bar while scanning', () => {
		const { getByText, container } = renderComponent(IsoPreparingRow, {
			props: { prepare: { drive_id: 'drv_1', phase: 'scanning', updated_at: AT, iso_name: 'a.iso' } }
		});
		expect(getByText('Scanning image')).toBeInTheDocument();
		expect(container.querySelector('[data-indeterminate="true"]')).not.toBeNull();
		expect(container.querySelector('[data-progress-fill]')).toBeNull();
	});

	it('cancels the ISO rip', async () => {
		const { getByRole } = renderComponent(IsoPreparingRow, {
			props: { prepare: { drive_id: 'drv_1', phase: 'scanning', updated_at: AT, iso_name: 'a.iso' } }
		});
		await fireEvent.click(getByRole('button', { name: 'Cancel' }));
		expect(cancelIsoRip).toHaveBeenCalledWith('drv_1');
	});

	it('labels a disc-folder rip as a folder', () => {
		const { getByText } = renderComponent(IsoPreparingRow, {
			props: {
				prepare: { drive_id: 'drv_1', phase: 'scanning', updated_at: AT, iso_name: 'Disc 1', iso_kind: 'folder' }
			}
		});
		expect(getByText('Folder')).toBeInTheDocument();
		expect(getByText('Scanning disc folder')).toBeInTheDocument();
	});
});
