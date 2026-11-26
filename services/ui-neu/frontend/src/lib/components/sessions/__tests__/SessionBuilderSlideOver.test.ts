import { it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor, within } from '$lib/testing/render';
vi.mock('$lib/api/sessions', () => ({
	createSession: vi.fn(),
	updateSession: vi.fn(),
	previewTemplate: vi.fn().mockResolvedValue({ resolved: 'p', error: null })
}));
import { createSession } from '$lib/api/sessions';
import SessionBuilderSlideOver from '../SessionBuilderSlideOver.svelte';

const props = (over = {}) => ({
	session: null,
	ripPresets: [{ id: 'r1', name: 'rip r1', media_type: 'movie' }] as any,
	transcodePresets: [{ id: 't1', name: 'tc1', media_type: 'movie' }] as any,
	oncreaterip: vi.fn(),
	oncreatetranscode: vi.fn(),
	onsaved: vi.fn(),
	oncancel: vi.fn(),
	...over
});
const session = (over = {}) => ({
	id: 's1',
	name: 'ses',
	media_type: 'movie',
	is_builtin: false,
	rip_preset_id: 'r1',
	transcode_preset_id: null,
	output_path_template: 'm/{title}.{ext}',
	overrides_json: null,
	...over
});

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

it('New session: shell header and footer with the note, Cancel and a clickable Save', async () => {
	renderComponent(SessionBuilderSlideOver, { props: props() });
	const dialog = screen.getByRole('dialog', { name: 'New session' });
	expect(within(dialog).getByRole('heading', { name: 'New session' })).toBeInTheDocument();
	const footer = screen.getByTestId('editor-sidebar-footer');
	expect(within(footer).getByText('Rips only, no transcode step.')).toBeInTheDocument();
	expect(within(footer).getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
	const save = within(footer).getByRole('button', { name: 'Save' });
	expect(save).toBeEnabled();
	// the builder's own footer is not repeated in the body
	expect(within(dialog).getAllByRole('button', { name: 'Cancel' })).toHaveLength(1);
});

it('Save in the footer with an empty name makes no call, marks the name and focuses it', async () => {
	renderComponent(SessionBuilderSlideOver, { props: props() });
	await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
	const name = screen.getByLabelText(/session name/i);
	await waitFor(() => expect(document.activeElement).toBe(name));
	expect(createSession).not.toHaveBeenCalled();
	expect(name).toHaveAttribute('aria-invalid', 'true');
	expect(document.getElementById('sb-name-error')).toHaveTextContent('Name is required');
});

it('Save in the footer submits the form', async () => {
	const saved = session();
	vi.mocked(createSession).mockResolvedValue(saved as any);
	const onsaved = vi.fn();
	renderComponent(SessionBuilderSlideOver, { props: props({ onsaved }) });
	await fireEvent.input(screen.getByLabelText(/session name/i), { target: { value: 'Mine' } });
	await fireEvent.change(screen.getByLabelText(/rip preset/i), { target: { value: 'r1' } });
	await fireEvent.input(screen.getByLabelText(/output path/i), { target: { value: 'm/{title}.{ext}' } });
	await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
	await waitFor(() => expect(onsaved).toHaveBeenCalledWith(saved));
});

it('Edit session: titled "Edit session"', () => {
	renderComponent(SessionBuilderSlideOver, { props: props({ session: session() }) });
	expect(screen.getByRole('dialog', { name: 'Edit session' })).toBeInTheDocument();
});

it('View session: a built-in has Close and no Save', () => {
	renderComponent(SessionBuilderSlideOver, { props: props({ session: session({ is_builtin: true }) }) });
	expect(screen.getByRole('dialog', { name: 'View session' })).toBeInTheDocument();
	const footer = screen.getByTestId('editor-sidebar-footer');
	expect(within(footer).getByRole('button', { name: 'Close' })).toBeInTheDocument();
	expect(within(footer).queryByRole('button', { name: 'Save' })).toBeNull();
});

it.each([
	[
		'footer Cancel',
		async () =>
			fireEvent.click(within(screen.getByTestId('editor-sidebar-footer')).getByRole('button', { name: 'Cancel' }))
	],
	['header Close', async () => fireEvent.click(screen.getByRole('button', { name: 'Close' }))],
	['Escape', async () => fireEvent.keyDown(document, { key: 'Escape' })]
])('%s calls oncancel', async (_name, act) => {
	const oncancel = vi.fn();
	renderComponent(SessionBuilderSlideOver, { props: props({ oncancel }) });
	await act();
	expect(oncancel).toHaveBeenCalledOnce();
});
