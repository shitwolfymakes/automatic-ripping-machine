import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import TranscodePresetsSection from '../TranscodePresetsSection.svelte';
import { fetchTranscodePresets, deleteTranscodePreset } from '$lib/api/transcodePresets';
import type { TranscodePresetView } from '$lib/types/api.gen';

vi.mock('$lib/api/transcodePresets', () => ({
	fetchTranscodePresets: vi.fn(),
	deleteTranscodePreset: vi.fn(),
	// TranscodePresetForm imports these; stub them so its module resolves.
	createTranscodePreset: vi.fn(),
	updateTranscodePreset: vi.fn()
}));

const fetchMock = vi.mocked(fetchTranscodePresets);
const deleteMock = vi.mocked(deleteTranscodePreset);

function makePreset(overrides: Partial<TranscodePresetView> = {}): TranscodePresetView {
	return {
		id: 'tpr_1',
		name: 'My preset',
		media_type: 'movie',
		is_builtin: false,
		tool: 'handbrake',
		preset_ref: null,
		preset_json: null,
		container: 'mkv',
		codec: null,
		hw_preference: null,
		extra_args: null,
		created_by_user_id: 'user_1',
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		...overrides
	} as TranscodePresetView;
}

describe('TranscodePresetsSection', () => {
	beforeEach(() => {
		fetchMock.mockReset();
		deleteMock.mockReset();
		deleteMock.mockResolvedValue(undefined);
	});
	afterEach(() => cleanup());

	it('renders the list from fetchTranscodePresets', async () => {
		fetchMock.mockResolvedValue([
			makePreset({ id: 'p1', name: 'HQ movie' }),
			makePreset({ id: 'p2', name: 'Stock TV', media_type: 'tv', is_builtin: true })
		]);
		renderComponent(TranscodePresetsSection);
		await waitFor(() => {
			expect(screen.getByText('HQ movie')).toBeInTheDocument();
			expect(screen.getByText('Stock TV')).toBeInTheDocument();
		});
		expect(fetchMock).toHaveBeenCalled();
	});

	it('renders mapped tool/container labels and "—" for a null hw_preference', async () => {
		fetchMock.mockResolvedValue([
			makePreset({ id: 'a', name: 'A', tool: 'abcde', container: 'flac', hw_preference: null }),
			makePreset({ id: 'b', name: 'B', tool: 'handbrake', container: 'mkv', hw_preference: 'cpu_only' })
		]);
		renderComponent(TranscodePresetsSection);
		await waitFor(() => expect(screen.getByText('A')).toBeInTheDocument());

		// non-null label mapping
		expect(screen.getByText('abcde')).toBeInTheDocument();
		expect(screen.getByText('FLAC')).toBeInTheDocument();
		expect(screen.getByText('CPU only')).toBeInTheDocument();
		// null hw_preference renders the placeholder dash
		expect(screen.getByText('-')).toBeInTheDocument();
	});

	it('shows the form when "New preset" is clicked', async () => {
		fetchMock.mockResolvedValue([makePreset()]);
		renderComponent(TranscodePresetsSection);
		await waitFor(() => expect(screen.getByText('My preset')).toBeInTheDocument());
		await fireEvent.click(screen.getByTestId('transcode-preset-new'));
		expect(screen.getByText('New transcode preset')).toBeInTheDocument();
	});

	it('hides Delete for a built-in preset', async () => {
		fetchMock.mockResolvedValue([
			makePreset({ id: 'builtin', name: 'Stock preset', is_builtin: true })
		]);
		renderComponent(TranscodePresetsSection);
		await waitFor(() => expect(screen.getByText('Stock preset')).toBeInTheDocument());
		expect(screen.queryByTestId('transcode-preset-delete')).not.toBeInTheDocument();
		expect(screen.getByTestId('transcode-preset-builtin-badge')).toBeInTheDocument();
		expect(screen.getByTestId('transcode-preset-edit')).toBeInTheDocument();
	});

	it('deletes after confirming the dialog', async () => {
		fetchMock.mockResolvedValue([makePreset({ id: 'del_me', name: 'Delete me' })]);
		renderComponent(TranscodePresetsSection);
		await waitFor(() => expect(screen.getByText('Delete me')).toBeInTheDocument());

		await fireEvent.click(screen.getByTestId('transcode-preset-delete'));
		await waitFor(() => expect(screen.getByText('Delete transcode preset')).toBeInTheDocument());

		const deleteButtons = screen.getAllByText('Delete');
		await fireEvent.click(deleteButtons[deleteButtons.length - 1]);

		await waitFor(() => expect(deleteMock).toHaveBeenCalledWith('del_me'));
		expect(fetchMock).toHaveBeenCalledTimes(2);
	});

	it('surfaces a delete 409 (referenced by session) message inline', async () => {
		fetchMock.mockResolvedValue([makePreset({ id: 'ref_me', name: 'Referenced' })]);
		deleteMock.mockRejectedValue(new Error("preset is referenced by session 'My session'"));
		renderComponent(TranscodePresetsSection);
		await waitFor(() => expect(screen.getByText('Referenced')).toBeInTheDocument());

		await fireEvent.click(screen.getByTestId('transcode-preset-delete'));
		await waitFor(() => expect(screen.getByText('Delete transcode preset')).toBeInTheDocument());
		const deleteButtons = screen.getAllByText('Delete');
		await fireEvent.click(deleteButtons[deleteButtons.length - 1]);

		await waitFor(() =>
			expect(screen.getByTestId('transcode-presets-error')).toHaveTextContent(
				"referenced by session 'My session'"
			)
		);
	});
});
