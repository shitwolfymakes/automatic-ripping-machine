// Branch coverage for ApplySessionDialog that ApplySessionDialog.test.ts
// leaves open: the disc-type filter, recipe-box fallbacks, the naming-preview
// failure text, stale previews, and the failure paths of load and apply.
//
// The branch below cannot be reached from the rendered dialog, so nothing
// here forces it:
// - the `value={s.id}` option guard: its unchanged-value arm needs an option
//   to re-render with the same id, but sessions load once in onMount into a
//   keyed each block, and the runtime-enabled store flipping re-filters the
//   same objects without re-rendering their options.
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import ApplySessionDialog from '../ApplySessionDialog.svelte';
import { createJob } from '../../../__fixtures__/job';
import { fetchSessions } from '$lib/api/sessions';
import { fetchRipPresets } from '$lib/api/rip-presets';
import { fetchTranscodePresets } from '$lib/api/transcode-presets';
import { applySession, fetchNamingPreview } from '$lib/api/jobs';
import { ApiError } from '$lib/api/client';
import type { SessionView, RipPresetView, TranscodePresetView, JobNamingPreviewResponse } from '$lib/types/api.gen';

vi.mock('$lib/api/sessions', () => ({
	fetchSessions: vi.fn()
}));
vi.mock('$lib/api/rip-presets', () => ({
	fetchRipPresets: vi.fn()
}));
vi.mock('$lib/api/transcode-presets', () => ({
	fetchTranscodePresets: vi.fn()
}));
vi.mock('$lib/api/jobs', () => ({
	applySession: vi.fn(),
	fetchNamingPreview: vi.fn()
}));

const fetchSessionsMock = vi.mocked(fetchSessions);
const fetchRipPresetsMock = vi.mocked(fetchRipPresets);
const fetchTranscodePresetsMock = vi.mocked(fetchTranscodePresets);
const applySessionMock = vi.mocked(applySession);
const fetchNamingPreviewMock = vi.mocked(fetchNamingPreview);

function createSession(overrides: Partial<SessionView> = {}): SessionView {
	return {
		id: 'ses_1',
		name: 'Session 1',
		media_type: 'movie',
		is_builtin: false,
		rip_preset_id: 'rip_1',
		transcode_preset_id: 'tx_1',
		output_path_template: '{title}/{title}.mkv',
		overrides_json: null,
		created_by_user_id: null,
		created_at: null,
		updated_at: null,
		...overrides
	};
}

function createRipPreset(overrides: Partial<RipPresetView> = {}): RipPresetView {
	return {
		id: 'rip_1',
		name: 'Rip Preset 1',
		media_type: 'movie',
		is_builtin: false,
		track_selection: 'longest',
		identification_mode: 'auto',
		output_mode: 'mkv',
		track_filters_json: {},
		...overrides
	} as RipPresetView;
}

function createTranscodePreset(overrides: Partial<TranscodePresetView> = {}): TranscodePresetView {
	return {
		id: 'tx_1',
		name: 'Transcode Preset 1',
		media_type: 'movie',
		is_builtin: false,
		tool: 'handbrake',
		preset_ref: null,
		handbrake_settings: null,
		...overrides
	} as TranscodePresetView;
}

function makePreview(path: string): JobNamingPreviewResponse {
	return {
		job_output_dir: 'dir',
		job_output_name: 'name',
		items: [
			{
				track_id: 'trk_1',
				track_number: 1,
				output_path: path,
				output_dir: 'dir',
				output_name: path
			}
		]
	};
}

function renderDialog(discType: 'dvd' | 'cd' | 'data' = 'dvd') {
	return renderComponent(ApplySessionDialog, {
		props: { job: createJob({ id: 'job_1', disc_type: discType }), onclose: vi.fn(), onapplied: vi.fn() }
	});
}

function optionTexts(): string[] {
	const select = screen.getByTestId('apply-session-select') as HTMLSelectElement;
	return Array.from(select.options).map((o) => o.textContent ?? '');
}

async function choose(sessionId: string) {
	await fireEvent.change(screen.getByTestId('apply-session-select'), { target: { value: sessionId } });
}

// Waits for the first session to be listed, then picks it.
async function pickSession(name: RegExp, sessionId: string) {
	await waitFor(() => expect(screen.getByText(name)).toBeInTheDocument());
	await choose(sessionId);
}

describe('ApplySessionDialog branches', () => {
	beforeEach(() => {
		fetchRipPresetsMock.mockResolvedValue([createRipPreset()]);
		fetchTranscodePresetsMock.mockResolvedValue([createTranscodePreset()]);
		fetchNamingPreviewMock.mockResolvedValue(makePreview('out/Track 01.mkv'));
	});

	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	describe('disc-type filter', () => {
		const sessions = [
			createSession({ id: 'ses_movie', name: 'Movie MKV', media_type: 'movie' }),
			createSession({ id: 'ses_tv', name: 'TV Episodes', media_type: 'tv' }),
			createSession({ id: 'ses_music', name: 'Music FLAC', media_type: 'music' }),
			createSession({ id: 'ses_data', name: 'Data ISO', media_type: 'data' })
		];

		it('lists music and tv sessions only for a CD job', async () => {
			fetchSessionsMock.mockResolvedValue(sessions);
			renderDialog('cd');
			await waitFor(() => expect(screen.getByText(/Music FLAC/)).toBeInTheDocument());
			expect(optionTexts()).toEqual(['Choose...', 'TV Episodes (tv)', 'Music FLAC (music)']);
		});

		it('lists data and tv sessions only for a data disc job', async () => {
			fetchSessionsMock.mockResolvedValue(sessions);
			renderDialog('data');
			await waitFor(() => expect(screen.getByText(/Data ISO/)).toBeInTheDocument());
			expect(optionTexts()).toEqual(['Choose...', 'TV Episodes (tv)', 'Data ISO (data)']);
		});
	});

	describe('recipe box', () => {
		it('shows the rip preset id when it is not in the rip preset list', async () => {
			fetchSessionsMock.mockResolvedValue([createSession({ id: 'ses_a', name: 'Alpha', rip_preset_id: 'rip_gone' })]);
			renderDialog();
			await pickSession(/Alpha/, 'ses_a');
			await waitFor(() => expect(screen.getByTestId('recipe-rip-preset')).toHaveTextContent('rip_gone'));
		});

		it('shows "No transcode" when the transcode preset id is not in the list', async () => {
			fetchSessionsMock.mockResolvedValue([
				createSession({ id: 'ses_a', name: 'Alpha', transcode_preset_id: 'tx_gone' })
			]);
			renderDialog();
			await pickSession(/Alpha/, 'ses_a');
			await waitFor(() => expect(screen.getByTestId('recipe-transcode-preset')).toHaveTextContent('No transcode'));
		});
	});

	describe('naming-preview failure text', () => {
		async function previewFailsWith(reason: unknown) {
			fetchSessionsMock.mockResolvedValue([createSession({ id: 'ses_a', name: 'Alpha' })]);
			fetchNamingPreviewMock.mockRejectedValue(reason);
			renderDialog();
			await pickSession(/Alpha/, 'ses_a');
			await waitFor(() => expect(screen.getByTestId('recipe-output-problem')).toBeInTheDocument());
			return screen.getByTestId('recipe-output-problem');
		}

		it('shows a message without a token as it is and blocks Apply', async () => {
			const problem = await previewFailsWith(new Error('naming template is broken'));
			expect(problem).toHaveTextContent('naming template is broken');
			expect(screen.getByTestId('apply-session-apply')).toBeDisabled();
		});

		it.each(['transcode_slug', 'ext'])('says the session has no transcode preset for token {%s}', async (token) => {
			const problem = await previewFailsWith(new Error(`track index=0: token {${token}} resolved empty`));
			expect(problem).toHaveTextContent(
				`This session has no transcode preset, so {${token}} in its output path cannot be filled.`
			);
			expect(problem).toHaveTextContent('Give the session a transcode preset or choose another session.');
		});

		it('names a known token with its plain-word description', async () => {
			const problem = await previewFailsWith(new Error('track index=0: token {year} resolved empty'));
			expect(problem).toHaveTextContent('This job has no year, so {year} in the output path cannot be filled.');
		});

		it('names an unknown token as a value for that token', async () => {
			const problem = await previewFailsWith(new Error('track index=0: token {mood} resolved empty'));
			expect(problem).toHaveTextContent(
				'This job has no value for {mood}, so {mood} in the output path cannot be filled.'
			);
			expect(problem).toHaveTextContent('marks it optional as {mood?}');
		});

		it('shows "Preview failed" when the rejection is not an Error', async () => {
			const problem = await previewFailsWith('boom');
			expect(problem).toHaveTextContent('Preview failed');
			expect(screen.getByTestId('apply-session-apply')).toBeDisabled();
		});
	});

	describe('stale preview', () => {
		type Deferred = {
			promise: Promise<JobNamingPreviewResponse>;
			resolve: (v: JobNamingPreviewResponse) => void;
			reject: (e: unknown) => void;
		};

		function deferred(): Deferred {
			let resolve!: Deferred['resolve'];
			let reject!: Deferred['reject'];
			const promise = new Promise<JobNamingPreviewResponse>((res, rej) => {
				resolve = res;
				reject = rej;
			});
			return { promise, resolve, reject };
		}

		// Selects Alpha (preview pending), then Beta (preview pending), so the
		// Alpha preview is stale by the time the test settles it.
		async function startTwoPreviews() {
			fetchSessionsMock.mockResolvedValue([
				createSession({ id: 'ses_a', name: 'Alpha' }),
				createSession({ id: 'ses_b', name: 'Beta' })
			]);
			const first = deferred();
			const second = deferred();
			fetchNamingPreviewMock.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
			renderDialog();
			await pickSession(/Alpha/, 'ses_a');
			await waitFor(() => expect(fetchNamingPreviewMock).toHaveBeenCalledTimes(1));
			await choose('ses_b');
			await waitFor(() => expect(fetchNamingPreviewMock).toHaveBeenCalledTimes(2));
			return { first, second };
		}

		it('ignores a rejection from a preview for a session that is no longer selected', async () => {
			const { first, second } = await startTwoPreviews();

			first.reject(new Error('track index=0: token {year} resolved empty'));
			await new Promise((r) => setTimeout(r, 30));

			expect(screen.queryByTestId('recipe-output-problem')).not.toBeInTheDocument();
			// The stale finally must not clear the loading state of the live preview.
			expect(screen.getByText('Resolving...')).toBeInTheDocument();
			expect(screen.getByTestId('apply-session-apply')).toBeDisabled();

			second.resolve(makePreview('out/Beta.mkv'));
			await waitFor(() => expect(screen.getByTestId('recipe-output-path')).toHaveTextContent('out/Beta.mkv'));
			expect(screen.getByTestId('apply-session-apply')).not.toBeDisabled();
		});

		it('ignores a result from a preview for a session that is no longer selected', async () => {
			const { first, second } = await startTwoPreviews();

			first.resolve(makePreview('out/Alpha.mkv'));
			await new Promise((r) => setTimeout(r, 30));

			expect(screen.queryByText('out/Alpha.mkv')).not.toBeInTheDocument();
			expect(screen.getByText('Resolving...')).toBeInTheDocument();

			second.resolve(makePreview('out/Beta.mkv'));
			await waitFor(() => expect(screen.getByTestId('recipe-output-path')).toHaveTextContent('out/Beta.mkv'));
			expect(screen.queryByText('out/Alpha.mkv')).not.toBeInTheDocument();
		});
	});

	describe('fetchSessions failing', () => {
		it('leaves the session list empty', async () => {
			fetchSessionsMock.mockRejectedValue(new Error('network down'));
			renderDialog();
			await waitFor(() => expect(fetchSessionsMock).toHaveBeenCalledTimes(1));
			await new Promise((r) => setTimeout(r, 30));
			expect(optionTexts()).toEqual(['Choose...']);
		});
	});

	describe('apply failures', () => {
		async function applyWith(rejection: unknown) {
			fetchSessionsMock.mockResolvedValue([createSession({ id: 'ses_a', name: 'Alpha' })]);
			applySessionMock.mockRejectedValue(rejection);
			renderDialog();
			await pickSession(/Alpha/, 'ses_a');
			await waitFor(() => expect(screen.getByTestId('apply-session-apply')).not.toBeDisabled());
			await fireEvent.click(screen.getByTestId('apply-session-apply'));
			await waitFor(() => expect(screen.getByTestId('apply-session-error')).toBeInTheDocument());
		}

		it('shows the error message for a 409 whose body has no detail', async () => {
			await applyWith(new ApiError(409, 'API 409: Conflict', {}));
			expect(screen.getByTestId('apply-session-error')).toHaveTextContent('API 409: Conflict');
			expect(screen.getByTestId('apply-session-select')).toBeInTheDocument();
		});

		it('shows the error message for a 409 whose detail has no collisions', async () => {
			await applyWith(new ApiError(409, 'API 409: Conflict', { detail: { message: 'nope' } }));
			expect(screen.getByTestId('apply-session-error')).toHaveTextContent('API 409: Conflict');
			expect(screen.queryByTestId('apply-session-overwrite')).not.toBeInTheDocument();
		});

		it('shows "Apply failed" when the rejection is not an Error', async () => {
			await applyWith('boom');
			expect(screen.getByTestId('apply-session-error')).toHaveTextContent('Apply failed');
		});
	});
});
