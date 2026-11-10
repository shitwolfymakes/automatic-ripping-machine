import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, within } from '$lib/test-utils';
import PresetLibrary from '../PresetLibrary.svelte';

// Branch pins for PresetLibrary, beside PresetLibrary.svelte.test.ts. No
// branch is left open.

const rip = (id: string, name: string, mt: string, builtin = false) => ({
	id,
	name,
	media_type: mt as any,
	is_builtin: builtin,
	track_selection: 'main_feature' as const,
	identification_mode: 'required' as const,
	output_mode: 'tracks' as const,
	track_filters_json: null,
	created_by_user_id: null,
	created_at: null,
	updated_at: null
});

const transcode = (id: string, name: string, mt: string, builtin = false) => ({
	id,
	name,
	media_type: mt as any,
	is_builtin: builtin,
	tool: 'handbrake' as const,
	preset_ref: null,
	preset_json: null,
	container: 'mkv' as const,
	encoder: 'any_h265',
	extra_args: null,
	created_by_user_id: null,
	created_at: null,
	updated_at: null
});

const defaultProps = (over = {}) => ({
	kind: 'rip' as 'rip' | 'transcode',
	ripPresets: [
		rip('r1', 'Movie Rip', 'movie', true),
		rip('r2', 'TV Rip', 'tv', false),
		rip('r3', 'Custom Movie Rip', 'movie', false)
	],
	transcodePresets: [
		transcode('t1', 'H.265 MKV', 'movie', false),
		transcode('t2', 'Built-in TV Transcode', 'tv', true),
		transcode('t3', 'Music Transcode', 'music', false)
	],
	ripUsage: (id: string) => (id === 'r3' ? 4 : 0),
	transcodeUsage: (id: string) => (id === 't1' ? 7 : 0),
	loading: false,
	onnewrip: vi.fn(),
	onnewtranscode: vi.fn(),
	onview: vi.fn(),
	onedit: vi.fn(),
	onclone: vi.fn(),
	ondelete: vi.fn(),
	...over
});

const chooseSource = (value: string) =>
	fireEvent.change(screen.getByRole('combobox', { name: /filter by source/i }), { target: { value } });

afterEach(cleanup);

describe('PresetLibrary source filter', () => {
	it.each([
		['builtin', ['Movie Rip'], ['TV Rip', 'Custom Movie Rip']],
		['custom', ['TV Rip', 'Custom Movie Rip'], ['Movie Rip']],
		['all', ['Movie Rip', 'TV Rip', 'Custom Movie Rip'], []]
	])('rip kind with %s shows the matching presets', async (value, shown, hidden) => {
		renderComponent(PresetLibrary, defaultProps({ kind: 'rip' }));
		await chooseSource(value === 'all' ? 'builtin' : value);
		if (value === 'all') await chooseSource('all');
		for (const name of shown) expect(screen.getByText(name)).toBeInTheDocument();
		for (const name of hidden) expect(screen.queryByText(name)).not.toBeInTheDocument();
	});

	it.each([
		['builtin', ['Built-in TV Transcode'], ['H.265 MKV', 'Music Transcode']],
		['custom', ['H.265 MKV', 'Music Transcode'], ['Built-in TV Transcode']],
		['all', ['H.265 MKV', 'Built-in TV Transcode', 'Music Transcode'], []]
	])('transcode kind with %s shows the matching presets', async (value, shown, hidden) => {
		renderComponent(PresetLibrary, defaultProps({ kind: 'transcode' }));
		await chooseSource(value === 'all' ? 'custom' : value);
		if (value === 'all') await chooseSource('all');
		for (const name of shown) expect(screen.getByText(name)).toBeInTheDocument();
		for (const name of hidden) expect(screen.queryByText(name)).not.toBeInTheDocument();
	});

	it('search ignores case and surrounding spaces', async () => {
		renderComponent(PresetLibrary, defaultProps({ kind: 'rip' }));
		await fireEvent.input(screen.getByRole('searchbox', { name: /search rip presets/i }), {
			target: { value: '  tV rIP ' }
		});
		expect(screen.getByText('TV Rip')).toBeInTheDocument();
		expect(screen.queryByText('Movie Rip')).not.toBeInTheDocument();
	});
});

describe('PresetLibrary empty lists', () => {
	it('rip kind says no rip presets match when the filters leave nothing', async () => {
		renderComponent(PresetLibrary, defaultProps({ kind: 'rip' }));
		await chooseSource('builtin');
		await fireEvent.click(screen.getByRole('button', { name: /^TV/ }));
		expect(screen.getByText('No rip presets match the current filters.')).toBeInTheDocument();
		expect(screen.queryByText('Movie Rip')).not.toBeInTheDocument();
	});

	it('transcode kind says no transcode presets match when the filters leave nothing', async () => {
		renderComponent(PresetLibrary, defaultProps({ kind: 'transcode' }));
		await fireEvent.input(screen.getByRole('searchbox', { name: /search transcode presets/i }), {
			target: { value: 'zzz' }
		});
		expect(screen.getByText('No transcode presets match the current filters.')).toBeInTheDocument();
		expect(screen.queryByText('H.265 MKV')).not.toBeInTheDocument();
	});

	it('says nothing matches when the kind has no presets at all', () => {
		renderComponent(PresetLibrary, defaultProps({ kind: 'rip', ripPresets: [] }));
		expect(screen.getByText('No rip presets match the current filters.')).toBeInTheDocument();
	});
});

describe('PresetLibrary type chips', () => {
	it('counts only the rip presets on the rip tab', () => {
		renderComponent(PresetLibrary, defaultProps({ kind: 'rip' }));
		expect(screen.getByRole('button', { name: /^All 3$/ })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /^Movie 2$/ })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /^TV 1$/ })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /^Music 0$/ })).toBeInTheDocument();
	});

	it('counts only the transcode presets on the transcode tab', () => {
		renderComponent(PresetLibrary, defaultProps({ kind: 'transcode' }));
		expect(screen.getByRole('button', { name: /^All 3$/ })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /^Movie 1$/ })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /^TV 1$/ })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /^Music 1$/ })).toBeInTheDocument();
	});

	it('shows 0 for every type when the kind has no presets', () => {
		renderComponent(PresetLibrary, defaultProps({ kind: 'rip', ripPresets: [] }));
		for (const label of ['All', 'Movie', 'TV', 'Music', 'Data', 'ISO']) {
			expect(screen.getByRole('button', { name: new RegExp(`^${label} 0$`) })).toBeInTheDocument();
		}
	});

	it('shows 0 for a type with no presets', () => {
		renderComponent(PresetLibrary, defaultProps({ kind: 'rip' }));
		expect(screen.getByRole('button', { name: /^Data 0$/ })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /^ISO 0$/ })).toBeInTheDocument();
	});

	it('a chip press filters the list and All brings every preset back', async () => {
		renderComponent(PresetLibrary, defaultProps({ kind: 'transcode' }));
		await fireEvent.click(screen.getByRole('button', { name: /^Music/ }));
		expect(screen.getByRole('button', { name: /^Music/ })).toHaveAttribute('aria-pressed', 'true');
		expect(screen.getByText('Music Transcode')).toBeInTheDocument();
		expect(screen.queryByText('H.265 MKV')).not.toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: /^All/ }));
		expect(screen.getByText('H.265 MKV')).toBeInTheDocument();
		expect(screen.getByText('Built-in TV Transcode')).toBeInTheDocument();
	});
});

describe('PresetLibrary New button', () => {
	it('the rip tab offers only + New rip preset, which calls onnewrip', async () => {
		const props = defaultProps({ kind: 'rip' });
		renderComponent(PresetLibrary, props);
		expect(screen.queryByRole('button', { name: /new transcode preset/i })).not.toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: '+ New rip preset' }));
		expect(props.onnewrip).toHaveBeenCalledTimes(1);
		expect(props.onnewtranscode).not.toHaveBeenCalled();
	});

	it('the transcode tab offers only + New transcode preset, which calls onnewtranscode', async () => {
		const props = defaultProps({ kind: 'transcode' });
		renderComponent(PresetLibrary, props);
		expect(screen.queryByRole('button', { name: /new rip preset/i })).not.toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: '+ New transcode preset' }));
		expect(props.onnewtranscode).toHaveBeenCalledTimes(1);
		expect(props.onnewrip).not.toHaveBeenCalled();
	});
});

// The row is the nearest ancestor of the preset's name that holds its buttons
// and its usage chip.
const rowOf = (name: string): HTMLElement => {
	let el: HTMLElement | null = screen.getByText(name);
	while (
		el &&
		(within(el).queryByRole('button', { name: 'Clone' }) === null || within(el).queryByText(/used by/i) === null)
	)
		el = el.parentElement;
	return el as HTMLElement;
};

describe('PresetLibrary rip rows', () => {
	it('draws one row per rip preset and none for transcode presets', () => {
		renderComponent(PresetLibrary, defaultProps({ kind: 'rip' }));
		expect(screen.getAllByRole('button', { name: 'Clone' })).toHaveLength(3);
		expect(screen.queryByText('H.265 MKV')).not.toBeInTheDocument();
	});

	it('shows each rip preset its own usage from ripUsage', () => {
		const ripUsage = vi.fn((id: string) => (id === 'r3' ? 4 : 0));
		renderComponent(PresetLibrary, defaultProps({ kind: 'rip', ripUsage, transcodeUsage: () => 99 }));
		expect(within(rowOf('Custom Movie Rip')).getByText(/used by 4/i)).toBeInTheDocument();
		expect(within(rowOf('TV Rip')).getByText(/used by 0/i)).toBeInTheDocument();
		expect(ripUsage).toHaveBeenCalledWith('r1');
	});

	it('wires a custom row: Edit, Clone and Delete pass its preset on', async () => {
		const props = defaultProps({ kind: 'rip' });
		renderComponent(PresetLibrary, props);
		const row = rowOf('TV Rip');
		await fireEvent.click(within(row).getByRole('button', { name: 'Edit' }));
		await fireEvent.click(within(row).getByRole('button', { name: 'Clone' }));
		await fireEvent.click(within(row).getByRole('button', { name: 'Delete' }));
		expect(props.onedit).toHaveBeenCalledWith(props.ripPresets[1]);
		expect(props.onclone).toHaveBeenCalledWith(props.ripPresets[1]);
		expect(props.ondelete).toHaveBeenCalledWith(props.ripPresets[1]);
		expect(props.onview).not.toHaveBeenCalled();
	});

	it('wires a built-in row: View and Clone pass its preset on', async () => {
		const props = defaultProps({ kind: 'rip' });
		renderComponent(PresetLibrary, props);
		const row = rowOf('Movie Rip');
		await fireEvent.click(within(row).getByRole('button', { name: 'View' }));
		await fireEvent.click(within(row).getByRole('button', { name: 'Clone' }));
		expect(props.onview).toHaveBeenCalledWith(props.ripPresets[0]);
		expect(props.onclone).toHaveBeenCalledWith(props.ripPresets[0]);
		expect(props.onedit).not.toHaveBeenCalled();
	});
});

describe('PresetLibrary transcode rows', () => {
	it('draws one row per transcode preset and none for rip presets', () => {
		renderComponent(PresetLibrary, defaultProps({ kind: 'transcode' }));
		expect(screen.getAllByRole('button', { name: 'Clone' })).toHaveLength(3);
		expect(screen.queryByText('Movie Rip')).not.toBeInTheDocument();
	});

	it('shows each transcode preset its own usage from transcodeUsage', () => {
		const transcodeUsage = vi.fn((id: string) => (id === 't1' ? 7 : 0));
		renderComponent(PresetLibrary, defaultProps({ kind: 'transcode', transcodeUsage, ripUsage: () => 99 }));
		expect(within(rowOf('H.265 MKV')).getByText(/used by 7/i)).toBeInTheDocument();
		expect(within(rowOf('Music Transcode')).getByText(/used by 0/i)).toBeInTheDocument();
		expect(transcodeUsage).toHaveBeenCalledWith('t2');
	});

	it('wires a custom row: Edit, Clone and Delete pass its preset on', async () => {
		const props = defaultProps({ kind: 'transcode' });
		renderComponent(PresetLibrary, props);
		const row = rowOf('Music Transcode');
		await fireEvent.click(within(row).getByRole('button', { name: 'Edit' }));
		await fireEvent.click(within(row).getByRole('button', { name: 'Clone' }));
		await fireEvent.click(within(row).getByRole('button', { name: 'Delete' }));
		expect(props.onedit).toHaveBeenCalledWith(props.transcodePresets[2]);
		expect(props.onclone).toHaveBeenCalledWith(props.transcodePresets[2]);
		expect(props.ondelete).toHaveBeenCalledWith(props.transcodePresets[2]);
		expect(props.onview).not.toHaveBeenCalled();
	});

	it('wires a built-in row: View and Clone pass its preset on', async () => {
		const props = defaultProps({ kind: 'transcode' });
		renderComponent(PresetLibrary, props);
		const row = rowOf('Built-in TV Transcode');
		await fireEvent.click(within(row).getByRole('button', { name: 'View' }));
		await fireEvent.click(within(row).getByRole('button', { name: 'Clone' }));
		expect(props.onview).toHaveBeenCalledWith(props.transcodePresets[1]);
		expect(props.onclone).toHaveBeenCalledWith(props.transcodePresets[1]);
		expect(props.onedit).not.toHaveBeenCalled();
	});
});
