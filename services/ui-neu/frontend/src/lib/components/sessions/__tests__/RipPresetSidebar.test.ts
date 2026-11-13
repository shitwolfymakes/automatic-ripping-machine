import { it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor, within } from '$lib/test-utils';

vi.mock('$lib/api/rip-presets', () => ({
	createRipPreset: vi.fn(),
	updateRipPreset: vi.fn()
}));

import { createRipPreset } from '$lib/api/rip-presets';
import RipPresetSidebar from '../RipPresetSidebar.svelte';

const preset = (over = {}) =>
	({
		id: 'r1',
		name: 'rip r1',
		media_type: 'movie',
		is_builtin: false,
		track_selection: 'main_feature',
		identification_mode: 'required',
		output_mode: 'tracks',
		track_filters_json: null,
		...over
	}) as any;
const props = (over = {}) => ({ preset: null, readOnly: false, onsaved: vi.fn(), onclose: vi.fn(), ...over });

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

it('New: titled "New rip preset", with the shell footer holding the usage line, Cancel and Save', () => {
	renderComponent(RipPresetSidebar, { props: props() });
	const dialog = screen.getByRole('dialog', { name: 'New rip preset' });
	expect(within(dialog).getByRole('heading', { name: 'New rip preset' })).toBeInTheDocument();
	const footer = screen.getByTestId('editor-sidebar-footer');
	expect(within(footer).getByText('Used by 0 sessions')).toBeInTheDocument();
	expect(within(footer).getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
	expect(within(footer).getByRole('button', { name: 'Save' })).not.toBeDisabled();
	// the form's own title and buttons are not repeated in the body
	expect(within(dialog).getAllByRole('heading')).toHaveLength(1);
	expect(screen.queryByTestId('preset-submit')).toBeNull();
	expect(dialog).toHaveAttribute('data-stacked', 'false');
});

it('Save with an empty name makes no call, marks the name and focuses it', async () => {
	renderComponent(RipPresetSidebar, { props: props() });
	await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
	const name = screen.getByTestId('preset-name');
	await waitFor(() => expect(document.activeElement).toBe(name));
	expect(createRipPreset).not.toHaveBeenCalled();
	expect(name).toHaveAttribute('aria-invalid', 'true');
	expect(document.getElementById('preset-name-error')).toHaveTextContent('Name is required');
});

it('Edit: titled "Edit rip preset", shows the usage count', () => {
	renderComponent(RipPresetSidebar, { props: props({ preset: preset(), usage: 1 }) });
	expect(screen.getByRole('dialog', { name: 'Edit rip preset' })).toBeInTheDocument();
	expect(screen.getByText('Used by 1 session')).toBeInTheDocument();
	expect(screen.queryByRole('button', { name: 'Clone' })).toBeNull();
});

it('Save in the footer submits the form and reports the saved preset', async () => {
	const saved = preset({ id: 'r2', name: 'new' });
	vi.mocked(createRipPreset).mockResolvedValue(saved);
	const onsaved = vi.fn();
	renderComponent(RipPresetSidebar, { props: props({ onsaved }) });
	await fireEvent.input(screen.getByTestId('preset-name'), { target: { value: 'new' } });
	await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
	await waitFor(() => expect(onsaved).toHaveBeenCalledWith(saved));
});

it('Cancel and Close both call onclose', async () => {
	const onclose = vi.fn();
	renderComponent(RipPresetSidebar, { props: props({ onclose }) });
	await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
	await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
	expect(onclose).toHaveBeenCalledTimes(2);
});

it('View: a built-in is read-only, with the built-in note, a Clone button and no Save', async () => {
	const onclone = vi.fn();
	const p = preset({ is_builtin: true });
	renderComponent(RipPresetSidebar, { props: props({ preset: p, readOnly: true, onclone }) });
	const dialog = screen.getByRole('dialog', { name: 'View rip preset' });
	expect(within(dialog).getByTestId('preset-builtin-note')).toBeInTheDocument();
	expect(within(dialog).getByTestId('preset-name')).toBeDisabled();
	expect(within(dialog).queryByRole('button', { name: 'Save' })).toBeNull();
	const footer = screen.getByTestId('editor-sidebar-footer');
	expect(within(footer).getByRole('button', { name: 'Close' })).toBeInTheDocument();
	await fireEvent.click(within(dialog).getByRole('button', { name: 'Clone' }));
	expect(onclone).toHaveBeenCalledWith(p);
	expect(document.querySelector('.modal')).toBeNull();
});

it('a read-only preset without a clone handler shows no Clone button', () => {
	renderComponent(RipPresetSidebar, { props: props({ preset: preset({ is_builtin: true }), readOnly: true }) });
	expect(screen.queryByRole('button', { name: 'Clone' })).toBeNull();
});

it('a read-only sidebar with no preset shows no Clone button', () => {
	renderComponent(RipPresetSidebar, { props: props({ readOnly: true, onclone: vi.fn() }) });
	expect(screen.queryByRole('button', { name: 'Clone' })).toBeNull();
});

it('stacked layers the sidebar above the session sidebar', () => {
	renderComponent(RipPresetSidebar, { props: props({ stacked: true }) });
	expect(screen.getByRole('dialog')).toHaveAttribute('data-stacked', 'true');
});
