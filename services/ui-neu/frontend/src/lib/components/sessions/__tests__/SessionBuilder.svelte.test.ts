import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
vi.mock('$lib/api/sessions', () => ({ createSession: vi.fn(), updateSession: vi.fn(), previewTemplate: vi.fn().mockResolvedValue({ resolved: 'p', error: null }) }));
import { createSession } from '$lib/api/sessions';
import SessionBuilder from '../SessionBuilder.svelte';

const rip = (id: string, mt = 'movie') => ({ id, name: `rip ${id}`, media_type: mt } as any);
const props = (over = {}) => ({ session: null, ripPresets: [rip('r1'), rip('r2', 'tv')], transcodePresets: [{ id: 't1', name: 'tc1', media_type: 'movie' }], oncreaterip: vi.fn(), oncreatetranscode: vi.fn(), onsaved: vi.fn(), oncancel: vi.fn(), ...over });

afterEach(cleanup);

it('create is disabled until name + rip preset + template are set', async () => {
	renderComponent(SessionBuilder, props());
	const submit = () => screen.getByRole('button', { name: /create session/i }) as HTMLButtonElement;
	expect(submit().disabled).toBe(true);
	await fireEvent.input(screen.getByLabelText(/session name/i), { target: { value: 'My Movies' } });
	// movie is default media type; pick rip preset r1
	await fireEvent.change(screen.getByLabelText(/rip preset/i), { target: { value: 'r1' } });
	await fireEvent.input(screen.getByLabelText(/output path/i), { target: { value: 'movies/{title}.{ext}' } });
	expect(submit().disabled).toBe(false);
});

it('rip preset dropdown only lists presets of the chosen media type', async () => {
	renderComponent(SessionBuilder, props());
	const sel = screen.getByLabelText(/rip preset/i) as HTMLSelectElement;
	const opts = Array.from(sel.options).map((o) => o.textContent);
	expect(opts.join()).toMatch(/rip r1/); // movie
	expect(opts.join()).not.toMatch(/rip r2/); // tv, filtered out
});

it('switching media type clears the rip selection', async () => {
	renderComponent(SessionBuilder, props());
	await fireEvent.change(screen.getByLabelText(/rip preset/i), { target: { value: 'r1' } });
	await fireEvent.click(screen.getByRole('button', { name: /^TV$/ }));
	expect((screen.getByLabelText(/rip preset/i) as HTMLSelectElement).value).toBe('');
});

it('submits createSession with the assembled body', async () => {
	vi.mocked(createSession).mockResolvedValue({ id: 's9' } as any);
	const onsaved = vi.fn();
	renderComponent(SessionBuilder, props({ onsaved }));
	await fireEvent.input(screen.getByLabelText(/session name/i), { target: { value: 'My Movies' } });
	await fireEvent.change(screen.getByLabelText(/rip preset/i), { target: { value: 'r1' } });
	await fireEvent.input(screen.getByLabelText(/output path/i), { target: { value: 'movies/{title}.{ext}' } });
	await fireEvent.click(screen.getByRole('button', { name: /create session/i }));
	await waitFor(() => expect(createSession).toHaveBeenCalledWith(expect.objectContaining({ name: 'My Movies', media_type: 'movie', rip_preset_id: 'r1', transcode_preset_id: null, output_path_template: 'movies/{title}.{ext}' })));
	await waitFor(() => expect(onsaved).toHaveBeenCalled());
});

it('selecting "+ Create new rip preset..." fires oncreaterip and reverts select', async () => {
	const oncreaterip = vi.fn();
	renderComponent(SessionBuilder, props({ oncreaterip }));
	const sel = screen.getByLabelText(/rip preset/i) as HTMLSelectElement;
	await fireEvent.change(sel, { target: { value: '__create_rip__' } });
	expect(oncreaterip).toHaveBeenCalledOnce();
});

it('selecting "+ Create new transcode preset..." fires oncreatetranscode', async () => {
	const oncreatetranscode = vi.fn();
	renderComponent(SessionBuilder, props({ oncreatetranscode }));
	const sel = screen.getByLabelText(/transcode preset/i) as HTMLSelectElement;
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
		transcodePreset: undefined,
	} as any;
	renderComponent(SessionBuilder, props({ session }));
	// Open the Advanced disclosure to reveal the textarea
	await fireEvent.click(screen.getByText(/^Advanced$/i));
	const textarea = screen.getByLabelText(/overrides json/i) as HTMLTextAreaElement;
	expect(textarea.value).toContain('"foo"');
});
