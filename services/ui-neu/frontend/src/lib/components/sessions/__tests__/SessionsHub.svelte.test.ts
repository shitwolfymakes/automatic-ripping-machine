import { it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, within } from '$lib/testing/render';
import SessionsHub from '../SessionsHub.svelte';

const j = (id: string, name: string, mt: string, tc: string | null, builtin = false) =>
	({
		id,
		name,
		media_type: mt,
		is_builtin: builtin,
		rip_preset_id: 'r1',
		transcode_preset_id: tc,
		output_path_template: 'x/{title}.{ext}',
		overrides_json: null,
		ripPreset: { id: 'r1', name: 'Rip', track_selection: 'main_feature', output_mode: 'tracks' },
		transcodePreset: tc ? { id: tc, name: 'TC', container: 'mkv', encoder: 'any_h265' } : undefined
	}) as any;
const props = (over = {}) => ({
	sessions: [j('s1', 'Alpha', 'movie', 't1'), j('s2', 'Beta', 'movie', null), j('s3', 'Gamma', 'tv', 't2', true)],
	typeCounts: { all: 3, movie: 2, tv: 1, music: 0, data: 0, iso: 0 },
	loading: false,
	onedit: vi.fn(),
	onclone: vi.fn(),
	ondelete: vi.fn(),
	onnew: vi.fn(),
	...over
});

afterEach(cleanup);

it('lists all sessions', () => {
	renderComponent(SessionsHub, props());
	expect(screen.getByText('Alpha')).toBeInTheDocument();
	expect(screen.getByText('Gamma')).toBeInTheDocument();
});
it('search narrows by name', async () => {
	renderComponent(SessionsHub, props());
	await fireEvent.input(screen.getByPlaceholderText(/search/i), { target: { value: 'Bet' } });
	expect(screen.queryByText('Alpha')).not.toBeInTheDocument();
	expect(screen.getByText('Beta')).toBeInTheDocument();
});
it('media-type chip narrows', async () => {
	renderComponent(SessionsHub, props());
	await fireEvent.click(screen.getByRole('button', { name: /TV/ }));
	expect(screen.getByText('Gamma')).toBeInTheDocument();
	expect(screen.queryByText('Alpha')).not.toBeInTheDocument();
});
it('empty shows guided panel + new', async () => {
	const onnew = vi.fn();
	renderComponent(
		SessionsHub,
		props({ sessions: [], typeCounts: { all: 0, movie: 0, tv: 0, music: 0, data: 0, iso: 0 }, onnew })
	);
	await fireEvent.click(screen.getByRole('button', { name: /new session|first/i }));
	expect(onnew).toHaveBeenCalled();
});
it('loading shows skeletons', () => {
	renderComponent(SessionsHub, props({ loading: true, sessions: [] }));
	expect(screen.getAllByTestId('session-skeleton').length).toBeGreaterThan(0);
});
it('source filter narrows by is_builtin', async () => {
	renderComponent(SessionsHub, props());
	const selects = screen.getAllByRole('combobox');
	const sourceSel = selects.find((s) => within(s).queryByText('Built-in only'))!;
	await fireEvent.change(sourceSel, { target: { value: 'builtin' } });
	expect(screen.getByText('Gamma')).toBeInTheDocument();
	expect(screen.queryByText('Alpha')).not.toBeInTheDocument();
	await fireEvent.change(sourceSel, { target: { value: 'custom' } });
	expect(screen.getByText('Alpha')).toBeInTheDocument();
	expect(screen.queryByText('Gamma')).not.toBeInTheDocument();
});
it('transcode filter narrows by transcode_preset_id', async () => {
	renderComponent(SessionsHub, props());
	const selects = screen.getAllByRole('combobox');
	const tcSel = selects.find((s) => within(s).queryByText('Rip only'))!;
	await fireEvent.change(tcSel, { target: { value: 'none' } });
	expect(screen.getByText('Beta')).toBeInTheDocument();
	expect(screen.queryByText('Alpha')).not.toBeInTheDocument();
	await fireEvent.change(tcSel, { target: { value: 'has' } });
	expect(screen.getByText('Alpha')).toBeInTheDocument();
	expect(screen.queryByText('Beta')).not.toBeInTheDocument();
});

it('lists the sessions as a table with the mockup columns', () => {
	renderComponent(SessionsHub, props());
	const table = screen.getByRole('table', { name: 'Sessions' });
	const headers = within(table)
		.getAllByRole('columnheader')
		.map((h) => h.textContent?.trim());
	expect(headers).toEqual([
		'Session',
		'Media',
		'Type',
		'Rip preset',
		'Transcode preset',
		'Output path (sample)',
		'Actions'
	]);
	expect(within(table).getAllByRole('row')).toHaveLength(4);
});

it('shows the rip preset, transcode preset and sample path in a row', () => {
	renderComponent(SessionsHub, props());
	const row = screen.getByText('Alpha').closest('tr')!;
	expect(within(row).getByText('Rip')).toBeInTheDocument();
	expect(within(row).getByText('Main feature | Tracks')).toBeInTheDocument();
	expect(within(row).getByText('TC')).toBeInTheDocument();
	expect(within(row).getByText('Custom')).toBeInTheDocument();
	expect(row.querySelector('.mono')).not.toBeNull();
	const bare = screen.getByText('Beta').closest('tr')!;
	expect(within(bare).getByText('No transcode')).toBeInTheDocument();
});

it('Edit, Clone and Delete call back with the session', async () => {
	const p = props();
	renderComponent(SessionsHub, p);
	const row = screen.getByText('Alpha').closest('tr')!;
	await fireEvent.click(within(row).getByRole('button', { name: 'Edit' }));
	await fireEvent.click(within(row).getByRole('button', { name: 'Clone' }));
	await fireEvent.click(within(row).getByRole('button', { name: 'Delete' }));
	expect(p.onedit).toHaveBeenCalledWith(expect.objectContaining({ id: 's1' }));
	expect(p.onclone).toHaveBeenCalledWith(expect.objectContaining({ id: 's1' }));
	expect(p.ondelete).toHaveBeenCalledWith(expect.objectContaining({ id: 's1' }));
});

it('a built-in session opens with View and cannot be deleted', async () => {
	const p = props();
	renderComponent(SessionsHub, p);
	const row = screen.getByText('Gamma').closest('tr')!;
	expect(within(row).queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
	await fireEvent.click(within(row).getByRole('button', { name: 'View' }));
	expect(p.onedit).toHaveBeenCalledWith(expect.objectContaining({ id: 's3' }));
	const del = within(row).getByRole('button', { name: 'Delete' });
	expect(del).toBeDisabled();
	expect(del).toHaveAttribute('title', 'Built-in session: clone to customise');
	expect(within(screen.getByText('Alpha').closest('tr')!).getByRole('button', { name: 'Delete' })).not.toHaveAttribute(
		'title'
	);
});

it('marks the row of the open session', () => {
	renderComponent(SessionsHub, props({ activeKey: 's2' }));
	expect(screen.getByText('Beta').closest('tr')).toHaveAttribute('aria-current', 'true');
	expect(screen.getByText('Alpha').closest('tr')).not.toHaveAttribute('aria-current');
});

it('says no sessions match inside the table area when filters leave nothing', async () => {
	renderComponent(SessionsHub, props());
	await fireEvent.input(screen.getByPlaceholderText(/search/i), { target: { value: 'zzz' } });
	expect(screen.queryByRole('table')).not.toBeInTheDocument();
	expect(screen.getByText('No sessions match your filters.')).toBeInTheDocument();
});
