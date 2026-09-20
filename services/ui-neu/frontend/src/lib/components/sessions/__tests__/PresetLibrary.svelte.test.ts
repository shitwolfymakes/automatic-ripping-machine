import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import PresetLibrary from '../PresetLibrary.svelte';

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
	updated_at: null,
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
	codec: 'h265' as const,
	hw_preference: 'any' as const,
	extra_args: null,
	created_by_user_id: null,
	created_at: null,
	updated_at: null,
});

const defaultProps = (over = {}) => ({
	kind: 'rip' as 'rip' | 'transcode',
	ripPresets: [
		rip('r1', 'Movie Rip', 'movie', true),
		rip('r2', 'TV Rip', 'tv', false),
	],
	transcodePresets: [
		transcode('t1', 'H.265 MKV', 'movie', false),
	],
	ripUsage: (id: string) => (id === 'r2' ? 2 : 0),
	transcodeUsage: (_id: string) => 0,
	loading: false,
	onnewrip: vi.fn(),
	onnewtranscode: vi.fn(),
	onview: vi.fn(),
	onedit: vi.fn(),
	onclone: vi.fn(),
	ondelete: vi.fn(),
	...over,
});

afterEach(cleanup);

it('rip kind renders only the Rip presets section', () => {
	renderComponent(PresetLibrary, defaultProps({ kind: 'rip' }));
	expect(screen.getByRole('heading', { name: /rip presets/i })).toBeInTheDocument();
	expect(screen.queryByRole('heading', { name: /transcode presets/i })).not.toBeInTheDocument();
});

it('transcode kind renders only the Transcode presets section', () => {
	renderComponent(PresetLibrary, defaultProps({ kind: 'transcode' }));
	expect(screen.getByRole('heading', { name: /transcode presets/i })).toBeInTheDocument();
	expect(screen.queryByRole('heading', { name: /^rip presets/i })).not.toBeInTheDocument();
});

it('shows all rip preset rows (rip kind)', () => {
	renderComponent(PresetLibrary, defaultProps({ kind: 'rip' }));
	expect(screen.getByText('Movie Rip')).toBeInTheDocument();
	expect(screen.getByText('TV Rip')).toBeInTheDocument();
	// transcode rows are NOT shown on the rip tab
	expect(screen.queryByText('H.265 MKV')).not.toBeInTheDocument();
});

it('shows transcode preset rows (transcode kind)', () => {
	renderComponent(PresetLibrary, defaultProps({ kind: 'transcode' }));
	expect(screen.getByText('H.265 MKV')).toBeInTheDocument();
	expect(screen.queryByText('Movie Rip')).not.toBeInTheDocument();
});

it('+ New rip preset calls onnewrip', async () => {
	const onnewrip = vi.fn();
	renderComponent(PresetLibrary, defaultProps({ kind: 'rip', onnewrip }));
	await fireEvent.click(screen.getByRole('button', { name: /new rip preset/i }));
	expect(onnewrip).toHaveBeenCalled();
});

it('+ New transcode preset calls onnewtranscode', async () => {
	const onnewtranscode = vi.fn();
	renderComponent(PresetLibrary, defaultProps({ kind: 'transcode', onnewtranscode }));
	await fireEvent.click(screen.getByRole('button', { name: /new transcode preset/i }));
	expect(onnewtranscode).toHaveBeenCalled();
});

it('builtin rip preset shows BUILT-IN and disabled delete', () => {
	renderComponent(PresetLibrary, defaultProps({ kind: 'rip' }));
	// Movie Rip is builtin
	expect(screen.getByText('BUILT-IN')).toBeInTheDocument();
	// Find the delete button for the builtin row - there should be at least one disabled delete
	const delButtons = screen.getAllByRole('button', { name: /delete/i }) as HTMLButtonElement[];
	const disabledDels = delButtons.filter(b => b.disabled);
	expect(disabledDels.length).toBeGreaterThan(0);
});

it('rip preset with ripUsage>0 shows Used by N', () => {
	renderComponent(PresetLibrary, defaultProps({ kind: 'rip' }));
	// TV Rip (r2) has usage 2
	expect(screen.getByText(/used by 2/i)).toBeInTheDocument();
});

it('media-type chip narrows rip presets section', async () => {
	renderComponent(PresetLibrary, defaultProps({ kind: 'rip' }));
	// Click TV chip — Movie Rip should disappear, TV Rip should remain
	await fireEvent.click(screen.getByRole('button', { name: /^TV/i }));
	expect(screen.queryByText('Movie Rip')).not.toBeInTheDocument();
	expect(screen.getByText('TV Rip')).toBeInTheDocument();
});

it('loading shows skeleton placeholders', () => {
	renderComponent(PresetLibrary, defaultProps({ kind: 'rip', loading: true, ripPresets: [], transcodePresets: [] }));
	expect(screen.getAllByTestId('preset-skeleton').length).toBeGreaterThan(0);
});

it('derives chip counts from the active kind only', () => {
	// rip kind: Movie has r1 (rip) = 1, TV has r2 = 1 — transcode t1 is NOT counted here
	renderComponent(PresetLibrary, defaultProps({ kind: 'rip' }));
	expect(screen.getByRole('button', { name: /movie.*1/i })).toBeInTheDocument();
});

it('includes the reusable-note text', () => {
	renderComponent(PresetLibrary, defaultProps({ kind: 'rip' }));
	expect(screen.getByText(/reusable|preset.*reused|used by multiple/i)).toBeInTheDocument();
});
