// Loading/failure states of the encoder picker's GET /api/encoders fetch,
// isolated in its own file so the shared encoders store's module-level
// cache (src/lib/stores/encoders.svelte.ts) starts fresh (Vitest isolates
// modules per test file) and a single controlled fetch can be driven
// through loading and then failure within one render.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, waitFor, fireEvent, cleanup } from '$lib/test-utils';
import TranscodePresetForm from '../TranscodePresetForm.svelte';
import { updateTranscodePreset } from '$lib/api/transcodePresets';
import type { TranscodePresetView } from '$lib/types/api.gen';

vi.mock('$lib/api/transcodePresets', () => ({
	createTranscodePreset: vi.fn(),
	updateTranscodePreset: vi.fn()
}));

let rejectFetch: (e: unknown) => void = () => {};
vi.mock('$lib/api/encoders', () => ({
	fetchEncoders: () =>
		new Promise((_resolve, reject) => {
			rejectFetch = reject;
		})
}));

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
		encoder: 'preset',
		extra_args: null,
		created_by_user_id: 'user_1',
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		...overrides
	} as TranscodePresetView;
}

afterEach(() => cleanup());

describe('TranscodePresetForm encoder catalog loading and failure', () => {
	it('shows a loading placeholder, then an inline error on failure, keeping the current encoder selected and submittable', async () => {
		const updateMock = vi.mocked(updateTranscodePreset);
		updateMock.mockResolvedValue(makePreset({ id: 'tpr_5', encoder: 'any_h265' }));

		const preset = makePreset({ id: 'tpr_5', encoder: 'any_h265' });
		renderComponent(TranscodePresetForm, { props: { preset, onsaved: vi.fn(), oncancel: vi.fn() } });

		const encoder = screen.getByTestId('tp-encoder') as HTMLSelectElement;
		await waitFor(() => expect(encoder).toBeDisabled());
		expect(screen.getByText('Loading encoders...')).toBeInTheDocument();
		expect(encoder.value).toBe('any_h265');
		expect(screen.queryByTestId('tp-encoder-error')).not.toBeInTheDocument();

		rejectFetch(new Error('network down'));

		await waitFor(() =>
			expect(screen.getByTestId('tp-encoder-error').textContent).toBe(
				'Could not load encoders; the current encoder is kept.'
			)
		);
		expect(encoder).not.toBeDisabled();
		expect(encoder.value).toBe('any_h265');

		await fireEvent.click(screen.getByTestId('tp-submit'));

		await waitFor(() =>
			expect(updateMock).toHaveBeenCalledWith(
				'tpr_5',
				expect.objectContaining({ encoder: 'any_h265' })
			)
		);
	});
});
