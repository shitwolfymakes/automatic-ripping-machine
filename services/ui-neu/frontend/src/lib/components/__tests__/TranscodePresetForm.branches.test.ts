import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import TranscodePresetForm from '../TranscodePresetForm.svelte';
import { createTranscodePreset, updateTranscodePreset } from '$lib/api/transcodePresets';
import type { EncoderAvailabilityView, TranscodePresetView } from '$lib/types/api.gen';

// Branch pins for TranscodePresetForm, beside TranscodePresetForm.test.ts.
// Three branches cannot be reached from the rendered component, so nothing
// here forces them:
// - The `?? []` in `{#each groupedEncoders.get(g) ?? [] as enc (enc.id)}`: it
//   sits inside `{#if groupedEncoders.get(g)?.length}`, so the group always
//   has a list there.
// - The "value unchanged" path Svelte compiles for `<option value={encoder}>`
//   on the loading and empty-catalog placeholder options: the option's update
//   runs only when `encoder` changes, so it never sees the same value twice.
// - The `?? ''` Svelte adds to those two `value={encoder}` attributes:
//   `encoder` is a string state, never null.

vi.mock('$lib/api/transcodePresets', () => ({
	createTranscodePreset: vi.fn(),
	updateTranscodePreset: vi.fn()
}));

const catalog = vi.hoisted(() => ({ list: [] as unknown[] }));
vi.mock('$lib/api/encoders', () => ({ fetchEncoders: () => Promise.resolve(catalog.list) }));
vi.mock('$lib/api/ws', () => ({
	wsClient: { start: vi.fn(), subscribe: vi.fn(() => () => {}) }
}));

const createMock = vi.mocked(createTranscodePreset);
const updateMock = vi.mocked(updateTranscodePreset);

function enc(id: string, group: string): EncoderAvailabilityView {
	return {
		id,
		label: `Label ${id}`,
		group,
		engine: 'handbrake',
		kind: 'cpu',
		vendor: null,
		codec: null,
		available: true,
		reason: null
	} as EncoderAvailabilityView;
}

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

function deferred<T>() {
	let resolve!: (v: T) => void;
	let reject!: (e: unknown) => void;
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

function form(): HTMLFormElement {
	return screen.getByTestId('tp-name').closest('form') as HTMLFormElement;
}

function groups(): { label: string; values: string[] }[] {
	const select = screen.getByTestId('tp-encoder') as HTMLSelectElement;
	return Array.from(select.querySelectorAll('optgroup')).map((g) => ({
		label: g.label,
		values: Array.from(g.querySelectorAll('option')).map((o) => o.value)
	}));
}

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('TranscodePresetForm encoder groups', () => {
	it('renders groups in fixed order with their headings, keeping catalog order inside a group', async () => {
		catalog.list = [
			enc('vaapi_a', 'vaapi'),
			enc('cpu_b', 'cpu'),
			enc('nvenc_a', 'nvenc'),
			enc('cpu_a', 'cpu'),
			enc('qsv_a', 'qsv'),
			enc('any_a', 'any'),
			enc('preset', 'preset')
		];
		renderComponent(TranscodePresetForm, { props: { preset: null, onsaved: vi.fn(), oncancel: vi.fn() } });

		await waitFor(() =>
			expect(groups()).toEqual([
				{ label: "HandBrake preset's own", values: ['preset'] },
				{ label: 'CPU', values: ['cpu_b', 'cpu_a'] },
				{ label: 'Any GPU', values: ['any_a'] },
				{ label: 'Intel QSV', values: ['qsv_a'] },
				{ label: 'NVIDIA NVENC', values: ['nvenc_a'] },
				{ label: 'AMD VAAPI', values: ['vaapi_a'] }
			])
		);
	});

	it('renders no optgroup for an empty group and nothing for an unknown group', async () => {
		catalog.list = [enc('preset', 'preset'), enc('mystery', 'bogus'), enc('nvenc_a', 'nvenc')];
		renderComponent(TranscodePresetForm, { props: { preset: null, onsaved: vi.fn(), oncancel: vi.fn() } });

		await waitFor(() =>
			expect(groups()).toEqual([
				{ label: "HandBrake preset's own", values: ['preset'] },
				{ label: 'NVIDIA NVENC', values: ['nvenc_a'] }
			])
		);
		const values = Array.from((screen.getByTestId('tp-encoder') as HTMLSelectElement).options).map((o) => o.value);
		expect(values).not.toContain('mystery');
	});
});

describe('TranscodePresetForm submit guard', () => {
	it('makes no call for a built-in preset', async () => {
		renderComponent(TranscodePresetForm, {
			props: { preset: makePreset({ is_builtin: true }), onsaved: vi.fn(), oncancel: vi.fn() }
		});

		await fireEvent.submit(form());

		expect(createMock).not.toHaveBeenCalled();
		expect(updateMock).not.toHaveBeenCalled();
	});

	it.each(['', '   '])('makes no call for a blank name %j', async (value) => {
		renderComponent(TranscodePresetForm, { props: { preset: null, onsaved: vi.fn(), oncancel: vi.fn() } });
		await fireEvent.input(screen.getByTestId('tp-name'), { target: { value } });

		await fireEvent.submit(form());

		expect(createMock).not.toHaveBeenCalled();
		expect(updateMock).not.toHaveBeenCalled();
	});

	it('makes no second call while a save is in flight', async () => {
		const pending = deferred<TranscodePresetView>();
		createMock.mockReturnValue(pending.promise);
		renderComponent(TranscodePresetForm, { props: { preset: null, onsaved: vi.fn(), oncancel: vi.fn() } });
		await fireEvent.input(screen.getByTestId('tp-name'), { target: { value: 'HQ' } });

		await fireEvent.submit(form());
		await fireEvent.submit(form());

		expect(createMock).toHaveBeenCalledTimes(1);
		pending.resolve(makePreset());
		await waitFor(() => expect(screen.getByTestId('tp-submit')).toHaveTextContent('Save'));
	});
});

describe('TranscodePresetForm request', () => {
	it('creates with every field of the body', async () => {
		createMock.mockResolvedValue(makePreset());
		renderComponent(TranscodePresetForm, { props: { preset: null, onsaved: vi.fn(), oncancel: vi.fn() } });
		await fireEvent.input(screen.getByTestId('tp-name'), { target: { value: 'HQ' } });
		await fireEvent.change(screen.getByTestId('tp-media-type'), { target: { value: 'tv' } });
		await fireEvent.input(screen.getByTestId('tp-preset-ref'), { target: { value: 'Fast 1080p30' } });
		await fireEvent.change(screen.getByTestId('tp-container'), { target: { value: 'mp4' } });
		await fireEvent.input(screen.getByTestId('tp-extra-args'), { target: { value: '--foo' } });

		await fireEvent.submit(form());

		await waitFor(() =>
			expect(createMock).toHaveBeenCalledWith({
				name: 'HQ',
				media_type: 'tv',
				tool: 'handbrake',
				preset_ref: 'Fast 1080p30',
				container: 'mp4',
				encoder: 'preset',
				extra_args: '--foo'
			})
		);
	});

	it('updates a custom preset by id with the body minus media_type', async () => {
		updateMock.mockResolvedValue(makePreset());
		const preset = makePreset({
			id: 'tpr_9',
			name: 'Mine',
			preset_ref: 'Ref',
			container: 'mp4',
			extra_args: '--bar'
		});
		renderComponent(TranscodePresetForm, { props: { preset, onsaved: vi.fn(), oncancel: vi.fn() } });

		await fireEvent.submit(form());

		await waitFor(() =>
			expect(updateMock).toHaveBeenCalledWith('tpr_9', {
				name: 'Mine',
				tool: 'handbrake',
				preset_ref: 'Ref',
				container: 'mp4',
				encoder: 'preset',
				extra_args: '--bar'
			})
		);
		expect(createMock).not.toHaveBeenCalled();
	});

	it('sends an empty preset ref and empty extra args as null', async () => {
		createMock.mockResolvedValue(makePreset());
		renderComponent(TranscodePresetForm, { props: { preset: null, onsaved: vi.fn(), oncancel: vi.fn() } });
		await fireEvent.input(screen.getByTestId('tp-name'), { target: { value: 'HQ' } });

		await fireEvent.submit(form());

		await waitFor(() =>
			expect(createMock).toHaveBeenCalledWith(expect.objectContaining({ preset_ref: null, extra_args: null }))
		);
	});
});

describe('TranscodePresetForm save', () => {
	it('shows Saving... and disables Save, Cancel and the name while in flight', async () => {
		const pending = deferred<TranscodePresetView>();
		createMock.mockReturnValue(pending.promise);
		renderComponent(TranscodePresetForm, { props: { preset: null, onsaved: vi.fn(), oncancel: vi.fn() } });
		await fireEvent.input(screen.getByTestId('tp-name'), { target: { value: 'HQ' } });

		await fireEvent.submit(form());

		await waitFor(() => expect(screen.getByTestId('tp-submit')).toHaveTextContent('Saving...'));
		expect(screen.getByTestId('tp-submit')).toBeDisabled();
		expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
		expect(screen.getByTestId('tp-name')).toBeDisabled();
		pending.resolve(makePreset());
		await waitFor(() => expect(screen.getByTestId('tp-name')).not.toBeDisabled());
	});

	it('hands the saved preset to onsaved and clears the busy state', async () => {
		const saved = makePreset({ id: 'saved_1' });
		createMock.mockResolvedValue(saved);
		const onsaved = vi.fn();
		renderComponent(TranscodePresetForm, { props: { preset: null, onsaved, oncancel: vi.fn() } });
		await fireEvent.input(screen.getByTestId('tp-name'), { target: { value: 'HQ' } });

		await fireEvent.submit(form());

		await waitFor(() => expect(onsaved).toHaveBeenCalledWith(saved));
		await waitFor(() => expect(screen.getByTestId('tp-submit')).toHaveTextContent('Save'));
		expect(screen.getByTestId('tp-submit')).not.toBeDisabled();
		expect(screen.getByRole('button', { name: 'Cancel' })).not.toBeDisabled();
		expect(screen.getByTestId('tp-name')).not.toBeDisabled();
	});

	it('shows an Error message, skips onsaved and clears the busy state', async () => {
		createMock.mockRejectedValue(new Error('name taken'));
		const onsaved = vi.fn();
		renderComponent(TranscodePresetForm, { props: { preset: null, onsaved, oncancel: vi.fn() } });
		await fireEvent.input(screen.getByTestId('tp-name'), { target: { value: 'HQ' } });

		await fireEvent.submit(form());

		await waitFor(() => expect(screen.getByTestId('tp-error').textContent).toBe('name taken'));
		expect(onsaved).not.toHaveBeenCalled();
		expect(screen.getByTestId('tp-submit')).toHaveTextContent('Save');
		expect(screen.getByTestId('tp-submit')).not.toBeDisabled();
		expect(screen.getByTestId('tp-name')).not.toBeDisabled();
	});

	it('shows "Save failed" for a non-Error rejection', async () => {
		createMock.mockRejectedValue('boom');
		renderComponent(TranscodePresetForm, { props: { preset: null, onsaved: vi.fn(), oncancel: vi.fn() } });
		await fireEvent.input(screen.getByTestId('tp-name'), { target: { value: 'HQ' } });

		await fireEvent.submit(form());

		await waitFor(() => expect(screen.getByTestId('tp-error').textContent).toBe('Save failed'));
	});

	it('clears the earlier error line while a later submit runs', async () => {
		createMock.mockRejectedValueOnce(new Error('name taken'));
		renderComponent(TranscodePresetForm, { props: { preset: null, onsaved: vi.fn(), oncancel: vi.fn() } });
		await fireEvent.input(screen.getByTestId('tp-name'), { target: { value: 'HQ' } });
		await fireEvent.submit(form());
		await waitFor(() => expect(screen.getByTestId('tp-error')).toBeInTheDocument());

		const pending = deferred<TranscodePresetView>();
		createMock.mockReturnValueOnce(pending.promise);
		await fireEvent.submit(form());

		await waitFor(() => expect(screen.queryByTestId('tp-error')).not.toBeInTheDocument());
		pending.resolve(makePreset());
		await waitFor(() => expect(screen.getByTestId('tp-name')).not.toBeDisabled());
	});

	it('calls the onsaved current when the save resolves, not the one at submit', async () => {
		const pending = deferred<TranscodePresetView>();
		createMock.mockReturnValue(pending.promise);
		const first = vi.fn();
		const second = vi.fn();
		const { rerender } = renderComponent(TranscodePresetForm, {
			props: { preset: null, onsaved: first, oncancel: vi.fn() }
		});
		await fireEvent.input(screen.getByTestId('tp-name'), { target: { value: 'HQ' } });
		await fireEvent.submit(form());

		await rerender({ preset: null, onsaved: second, oncancel: vi.fn() });
		const saved = makePreset({ id: 'saved_2' });
		pending.resolve(saved);

		await waitFor(() => expect(second).toHaveBeenCalledWith(saved));
		expect(first).not.toHaveBeenCalled();
	});
});
