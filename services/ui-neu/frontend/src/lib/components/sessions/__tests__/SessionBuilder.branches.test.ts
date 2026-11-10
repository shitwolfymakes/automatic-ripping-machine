import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
vi.mock('$lib/api/sessions', () => ({
	createSession: vi.fn(),
	updateSession: vi.fn(),
	previewTemplate: vi.fn().mockResolvedValue({ expansion: 'p' })
}));
import { createSession, updateSession, previewTemplate } from '$lib/api/sessions';
import SessionBuilder from '../SessionBuilder.svelte';

// Branch pins for SessionBuilder, beside SessionBuilder.svelte.test.ts. Two
// branches cannot be reached from the rendered component, so nothing here
// forces them:
// - switchMediaType's guard, `if (isEdit || readOnly) return;`: the media chips
//   are disabled exactly when it would return, and a disabled button's click
//   never reaches its handler.
// - handleSubmit's guard, `if (readOnly) return;`: a read-only builder renders
//   no submit button and disables every field, so the form cannot be submitted.

const rip = (id: string, mt = 'movie') => ({ id, name: `rip ${id}`, media_type: mt }) as any;
const props = (over = {}) => ({
	session: null,
	ripPresets: [rip('r1'), rip('r2', 'tv')],
	transcodePresets: [{ id: 't1', name: 'tc1', media_type: 'movie' }],
	oncreaterip: vi.fn(),
	oncreatetranscode: vi.fn(),
	onsaved: vi.fn(),
	oncancel: vi.fn(),
	...over
});

const editSession = {
	id: 'ses1',
	name: 'My Session',
	media_type: 'movie',
	rip_preset_id: 'r1',
	transcode_preset_id: null,
	output_path_template: 'out/{title}',
	overrides_json: null
} as any;

async function fillRequired() {
	await fireEvent.input(screen.getByLabelText(/session name/i), { target: { value: 'My Movies' } });
	await fireEvent.change(screen.getByLabelText(/rip preset/i), { target: { value: 'r1' } });
	await fireEvent.input(screen.getByLabelText(/output path/i), { target: { value: 'movies/{title}.{ext}' } });
}

const setOverrides = (value: string) =>
	fireEvent.input(screen.getByLabelText(/overrides json/i), { target: { value } });
const submit = () => fireEvent.click(screen.getByRole('button', { name: /create session/i }));

beforeEach(() => {
	vi.mocked(createSession).mockReset();
	vi.mocked(updateSession).mockReset();
	vi.mocked(previewTemplate).mockResolvedValue({ expansion: 'p' } as any);
});

afterEach(cleanup);

describe('SessionBuilder overrides', () => {
	it('sends overrides_json null when the field is blank', async () => {
		vi.mocked(createSession).mockResolvedValue({ id: 's1' } as any);
		renderComponent(SessionBuilder, props());
		await fillRequired();
		await submit();
		await waitFor(() => expect(createSession).toHaveBeenCalledWith(expect.objectContaining({ overrides_json: null })));
	});

	it('sends valid JSON parsed', async () => {
		vi.mocked(createSession).mockResolvedValue({ id: 's1' } as any);
		renderComponent(SessionBuilder, props());
		await fillRequired();
		await setOverrides('{"a": 1}');
		await submit();
		await waitFor(() =>
			expect(createSession).toHaveBeenCalledWith(expect.objectContaining({ overrides_json: { a: 1 } }))
		);
	});

	it('shows an error for invalid JSON, sends nothing, and clears it on the next submit', async () => {
		vi.mocked(createSession).mockResolvedValue({ id: 's1' } as any);
		renderComponent(SessionBuilder, props());
		await fillRequired();
		await setOverrides('{nope');
		await submit();
		expect(screen.getByText('Invalid JSON in overrides field')).toBeInTheDocument();
		expect(createSession).not.toHaveBeenCalled();

		await setOverrides('{"ok": true}');
		await submit();
		await waitFor(() => expect(createSession).toHaveBeenCalledOnce());
		expect(screen.queryByText('Invalid JSON in overrides field')).not.toBeInTheDocument();
	});
});

describe('SessionBuilder save', () => {
	it('create sends media_type with the fields', async () => {
		vi.mocked(createSession).mockResolvedValue({ id: 's1' } as any);
		renderComponent(SessionBuilder, props());
		await fillRequired();
		await submit();
		await waitFor(() =>
			expect(createSession).toHaveBeenCalledWith({
				name: 'My Movies',
				media_type: 'movie',
				rip_preset_id: 'r1',
				transcode_preset_id: null,
				output_path_template: 'movies/{title}.{ext}',
				overrides_json: null
			})
		);
		expect(updateSession).not.toHaveBeenCalled();
	});

	it('edit sends the fields without media_type', async () => {
		vi.mocked(updateSession).mockResolvedValue({ id: 'ses1' } as any);
		renderComponent(SessionBuilder, props({ session: editSession }));
		await fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
		await waitFor(() =>
			expect(updateSession).toHaveBeenCalledWith('ses1', {
				name: 'My Session',
				rip_preset_id: 'r1',
				transcode_preset_id: null,
				output_path_template: 'out/{title}',
				overrides_json: null
			})
		);
		expect(createSession).not.toHaveBeenCalled();
	});

	it('hands the saved session to onsaved', async () => {
		const saved = { id: 'saved1' } as any;
		vi.mocked(createSession).mockResolvedValue(saved);
		const onsaved = vi.fn();
		renderComponent(SessionBuilder, props({ onsaved }));
		await fillRequired();
		await submit();
		await waitFor(() => expect(onsaved).toHaveBeenCalledWith(saved));
	});

	it('shows the message of a rejected save', async () => {
		vi.mocked(createSession).mockRejectedValue(new Error('name already taken'));
		renderComponent(SessionBuilder, props());
		await fillRequired();
		await submit();
		expect(await screen.findByText('name already taken')).toBeInTheDocument();
	});

	it('shows "Failed to save session" for a rejection that is not an Error', async () => {
		vi.mocked(createSession).mockRejectedValue('nope');
		renderComponent(SessionBuilder, props());
		await fillRequired();
		await submit();
		expect(await screen.findByText('Failed to save session')).toBeInTheDocument();
	});

	it('disables the submit button while saving', async () => {
		let finish: (v: any) => void = () => {};
		vi.mocked(createSession).mockReturnValue(new Promise((res) => (finish = res)));
		renderComponent(SessionBuilder, props());
		await fillRequired();
		const button = screen.getByRole('button', { name: /create session/i }) as HTMLButtonElement;
		expect(button.disabled).toBe(false);
		await fireEvent.click(button);
		await waitFor(() => expect(button.disabled).toBe(true));
		finish({ id: 's1' });
		await waitFor(() => expect(button.disabled).toBe(false));
	});
});

describe('SessionBuilder selects', () => {
	it('choosing a transcode preset sets it and drops the rips-only note', async () => {
		vi.mocked(createSession).mockResolvedValue({ id: 's1' } as any);
		renderComponent(SessionBuilder, props());
		await fillRequired();
		expect(screen.getByText('Rips only, no transcode step.')).toBeInTheDocument();
		await fireEvent.change(screen.getByLabelText(/transcode preset/i), { target: { value: 't1' } });
		expect(screen.queryByText('Rips only, no transcode step.')).not.toBeInTheDocument();
		await submit();
		await waitFor(() =>
			expect(createSession).toHaveBeenCalledWith(expect.objectContaining({ transcode_preset_id: 't1' }))
		);
	});

	it('"+ Create new rip preset..." calls oncreaterip and keeps the previous rip value', async () => {
		const oncreaterip = vi.fn();
		renderComponent(SessionBuilder, props({ oncreaterip }));
		const sel = screen.getByLabelText(/rip preset/i) as HTMLSelectElement;
		await fireEvent.change(sel, { target: { value: 'r1' } });
		await fireEvent.change(sel, { target: { value: '__create_rip__' } });
		expect(oncreaterip).toHaveBeenCalledOnce();
		expect(sel.value).toBe('r1');
	});

	it('"+ Create new transcode preset..." calls oncreatetranscode and keeps the previous transcode value', async () => {
		const oncreatetranscode = vi.fn();
		renderComponent(SessionBuilder, props({ oncreatetranscode }));
		const sel = screen.getByLabelText(/transcode preset/i) as HTMLSelectElement;
		await fireEvent.change(sel, { target: { value: 't1' } });
		await fireEvent.change(sel, { target: { value: '__create_tc__' } });
		expect(oncreatetranscode).toHaveBeenCalledOnce();
		expect(sel.value).toBe('t1');
	});
});

describe('SessionBuilder output path', () => {
	it('typing in the field reaches the request output_path_template', async () => {
		vi.mocked(createSession).mockResolvedValue({ id: 's1' } as any);
		renderComponent(SessionBuilder, props());
		await fillRequired();
		await fireEvent.input(screen.getByLabelText(/output path/i), { target: { value: 'x/{title}' } });
		await submit();
		await waitFor(() =>
			expect(createSession).toHaveBeenCalledWith(expect.objectContaining({ output_path_template: 'x/{title}' }))
		);
	});

	it('gives OutputPathField has_transcode_preset true once a transcode preset is chosen', async () => {
		vi.useFakeTimers();
		try {
			renderComponent(SessionBuilder, props());
			await fireEvent.input(screen.getByLabelText(/output path/i), { target: { value: 'x/{title}' } });
			await fireEvent.change(screen.getByLabelText(/transcode preset/i), { target: { value: 't1' } });
			await vi.advanceTimersByTimeAsync(300);
			expect(previewTemplate).toHaveBeenLastCalledWith({
				template: 'x/{title}',
				media_type: 'movie',
				has_transcode_preset: true
			});
		} finally {
			vi.useRealTimers();
		}
	});
});
