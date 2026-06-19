import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import RipPresetsSection from '../RipPresetsSection.svelte';
import { fetchRipPresets, deleteRipPreset } from '$lib/api/ripPresets';
import type { RipPresetView } from '$lib/types/api.gen';

vi.mock('$lib/api/ripPresets', () => ({
	fetchRipPresets: vi.fn(),
	deleteRipPreset: vi.fn(),
	// RipPresetForm imports these; stub them so its module resolves.
	createRipPreset: vi.fn(),
	updateRipPreset: vi.fn()
}));

const fetchRipPresetsMock = vi.mocked(fetchRipPresets);
const deleteRipPresetMock = vi.mocked(deleteRipPreset);

function makePreset(overrides: Partial<RipPresetView> = {}): RipPresetView {
	return {
		id: 'preset_1',
		name: 'My preset',
		media_type: 'movie',
		is_builtin: false,
		track_selection: 'custom',
		identification_mode: 'required',
		output_mode: 'tracks',
		track_filters_json: null,
		created_by_user_id: 'user_1',
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		...overrides
	} as RipPresetView;
}

describe('RipPresetsSection', () => {
	beforeEach(() => {
		fetchRipPresetsMock.mockReset();
		deleteRipPresetMock.mockReset();
		deleteRipPresetMock.mockResolvedValue(undefined);
	});
	afterEach(() => cleanup());

	it('renders the list from fetchRipPresets', async () => {
		fetchRipPresetsMock.mockResolvedValue([
			makePreset({ id: 'p1', name: 'Custom movie' }),
			makePreset({ id: 'p2', name: 'Built-in TV', media_type: 'tv', is_builtin: true })
		]);
		renderComponent(RipPresetsSection);
		await waitFor(() => {
			expect(screen.getByText('Custom movie')).toBeInTheDocument();
			expect(screen.getByText('Built-in TV')).toBeInTheDocument();
		});
		expect(fetchRipPresetsMock).toHaveBeenCalled();
	});

	it('shows the form when "New preset" is clicked', async () => {
		fetchRipPresetsMock.mockResolvedValue([makePreset()]);
		renderComponent(RipPresetsSection);
		await waitFor(() => expect(screen.getByText('My preset')).toBeInTheDocument());
		await fireEvent.click(screen.getByTestId('rip-preset-new'));
		expect(screen.getByText('New rip preset')).toBeInTheDocument();
	});

	it('hides Delete for a built-in preset', async () => {
		fetchRipPresetsMock.mockResolvedValue([
			makePreset({ id: 'builtin', name: 'Stock movie preset', is_builtin: true })
		]);
		renderComponent(RipPresetsSection);
		await waitFor(() => expect(screen.getByText('Stock movie preset')).toBeInTheDocument());
		expect(screen.queryByTestId('rip-preset-delete')).not.toBeInTheDocument();
		expect(screen.getByTestId('rip-preset-builtin-badge')).toBeInTheDocument();
		// Edit is still available for built-ins.
		expect(screen.getByTestId('rip-preset-edit')).toBeInTheDocument();
	});

	it('deletes after confirming the dialog', async () => {
		fetchRipPresetsMock.mockResolvedValue([makePreset({ id: 'del_me', name: 'Delete me' })]);
		renderComponent(RipPresetsSection);
		await waitFor(() => expect(screen.getByText('Delete me')).toBeInTheDocument());

		await fireEvent.click(screen.getByTestId('rip-preset-delete'));
		await waitFor(() => expect(screen.getByText('Delete rip preset')).toBeInTheDocument());

		// Confirm button label is "Delete"; pick the dialog's confirm button (last).
		const deleteButtons = screen.getAllByText('Delete');
		await fireEvent.click(deleteButtons[deleteButtons.length - 1]);

		await waitFor(() => expect(deleteRipPresetMock).toHaveBeenCalledWith('del_me'));
		// Refresh is triggered after delete.
		expect(fetchRipPresetsMock).toHaveBeenCalledTimes(2);
	});
});
