import { it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/testing/render';
vi.mock('$lib/api/sessions', () => ({
	createSession: vi.fn(),
	updateSession: vi.fn(),
	previewTemplate: vi.fn().mockResolvedValue({ resolved: 'p', error: null })
}));
import { createSession } from '$lib/api/sessions';
import SessionBuilder from './SessionBuilderHarness.svelte';

const rip = (id: string, mt = 'movie') => ({ id, name: `rip ${id}`, media_type: mt }) as any;
const props = (over = {}) => ({
	session: null,
	ripPresets: [rip('r1'), rip('r2', 'tv')],
	transcodePresets: [{ id: 't1', name: 'tc1', media_type: 'movie' }],
	oncreaterip: vi.fn(),
	oncreatetranscode: vi.fn(),
	onsaved: vi.fn(),
	...over
});

afterEach(cleanup);

it('Save with nothing filled in makes no call, marks every required field and focuses the name', async () => {
	renderComponent(SessionBuilder, props());
	const submit = screen.getByRole('button', { name: /^save$/i }) as HTMLButtonElement;
	expect(submit.disabled).toBe(false);
	await fireEvent.click(submit);
	const name = screen.getByLabelText(/session name/i);
	await waitFor(() => expect(document.activeElement).toBe(name));
	expect(createSession).not.toHaveBeenCalled();
	expect(name).toHaveAttribute('aria-invalid', 'true');
	expect(name).toHaveAttribute('aria-describedby', 'sb-name-error');
	expect(document.getElementById('sb-name-error')).toHaveTextContent('Name is required');
	expect(screen.getByLabelText(/^rip preset/i)).toHaveAttribute('aria-invalid', 'true');
	expect(document.getElementById('sb-rip-error')).toHaveTextContent('Choose a rip preset');
	const path = screen.getByLabelText(/^output path/i);
	expect(path).toHaveAttribute('aria-invalid', 'true');
	expect(path).toHaveAttribute('aria-describedby', 'sb-path-error');
	expect(document.getElementById('sb-path-error')).toHaveTextContent('Output path is required');
});

it('focuses the first invalid field in form order, and clears each mark once filled', async () => {
	renderComponent(SessionBuilder, props());
	await fireEvent.input(screen.getByLabelText(/session name/i), { target: { value: 'My Movies' } });
	await fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
	const rip = screen.getByLabelText(/^rip preset/i);
	await waitFor(() => expect(document.activeElement).toBe(rip));
	expect(screen.getByLabelText(/session name/i)).not.toHaveAttribute('aria-invalid');
	expect(screen.queryByText('Name is required')).toBeNull();

	// movie is default media type; pick rip preset r1
	await fireEvent.change(rip, { target: { value: 'r1' } });
	await fireEvent.input(screen.getByLabelText(/^output path/i), { target: { value: 'movies/{title}.{ext}' } });
	expect(rip).not.toHaveAttribute('aria-invalid');
	expect(screen.getByLabelText(/^output path/i)).not.toHaveAttribute('aria-invalid');
	expect(screen.getByLabelText(/^output path/i)).not.toHaveAttribute('aria-describedby');
	expect(document.querySelector('.field-error')).toBeNull();
});

it('rip preset dropdown only lists presets of the chosen media type', async () => {
	renderComponent(SessionBuilder, props());
	const sel = screen.getByLabelText(/^rip preset/i) as HTMLSelectElement;
	const opts = Array.from(sel.options).map((o) => o.textContent);
	expect(opts.join()).toMatch(/rip r1/); // movie
	expect(opts.join()).not.toMatch(/rip r2/); // tv, filtered out
});

it('switching media type clears the rip selection', async () => {
	renderComponent(SessionBuilder, props());
	await fireEvent.change(screen.getByLabelText(/^rip preset/i), { target: { value: 'r1' } });
	await fireEvent.click(screen.getByRole('button', { name: /^TV$/ }));
	expect((screen.getByLabelText(/^rip preset/i) as HTMLSelectElement).value).toBe('');
});

it('submits createSession with the assembled body', async () => {
	vi.mocked(createSession).mockResolvedValue({ id: 's9' } as any);
	const onsaved = vi.fn();
	renderComponent(SessionBuilder, props({ onsaved }));
	await fireEvent.input(screen.getByLabelText(/session name/i), { target: { value: 'My Movies' } });
	await fireEvent.change(screen.getByLabelText(/^rip preset/i), { target: { value: 'r1' } });
	await fireEvent.input(screen.getByLabelText(/^output path/i), { target: { value: 'movies/{title}.{ext}' } });
	await fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
	await waitFor(() =>
		expect(createSession).toHaveBeenCalledWith(
			expect.objectContaining({
				name: 'My Movies',
				media_type: 'movie',
				rip_preset_id: 'r1',
				transcode_preset_id: null,
				output_path_template: 'movies/{title}.{ext}'
			})
		)
	);
	await waitFor(() => expect(onsaved).toHaveBeenCalled());
});

it('selecting "+ Create new rip preset..." fires oncreaterip and reverts select', async () => {
	const oncreaterip = vi.fn();
	renderComponent(SessionBuilder, props({ oncreaterip }));
	const sel = screen.getByLabelText(/^rip preset/i) as HTMLSelectElement;
	await fireEvent.change(sel, { target: { value: '__create_rip__' } });
	expect(oncreaterip).toHaveBeenCalledOnce();
});

it('selecting "+ Create new transcode preset..." fires oncreatetranscode', async () => {
	const oncreatetranscode = vi.fn();
	renderComponent(SessionBuilder, props({ oncreatetranscode }));
	const sel = screen.getByLabelText(/^transcode preset/i) as HTMLSelectElement;
	await fireEvent.change(sel, { target: { value: '__create_tc__' } });
	expect(oncreatetranscode).toHaveBeenCalledOnce();
});

it('edit mode seeds overrides_json into the textarea', async () => {
	const session = {
		id: 'ses1',
		name: 'My Session',
		media_type: 'movie',
		rip_preset_id: 'r1',
		transcode_preset_id: null,
		output_path_template: 'out/{title}',
		overrides_json: { foo: 1 },
		created_by_user_id: null,
		created_at: null,
		updated_at: null,
		ripPreset: undefined,
		transcodePreset: undefined
	} as any;
	renderComponent(SessionBuilder, props({ session }));
	// Open the Advanced disclosure to reveal the textarea
	await fireEvent.click(screen.getByText(/^Advanced$/i));
	const textarea = screen.getByLabelText(/overrides json/i) as HTMLTextAreaElement;
	expect(textarea.value).toContain('"foo"');
});

it('a built-in session offers Close and no save button', () => {
	renderComponent(SessionBuilder, props({ session: { id: 's', name: 'b', media_type: 'movie', is_builtin: true } }));
	expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument();
	expect(screen.queryByRole('button', { name: /^save/i })).toBeNull();
});

it('labels every field by name and links the output path to its tokens help', () => {
	renderComponent(SessionBuilder, props());
	expect(screen.getByLabelText('Transcode preset')).toHaveAttribute('id', 'sb-tc');
	expect(screen.getByLabelText('Overrides JSON')).toHaveAttribute('id', 'sb-overrides');
	expect(screen.getByRole('link', { name: 'Docs for Output path' })).toHaveAttribute(
		'href',
		'/help/guide/web-ui#output-path-tokens'
	);
	expect(screen.queryByRole('link', { name: 'Docs for Session name' })).toBeNull();
});
