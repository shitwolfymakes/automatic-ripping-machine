import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import SessionCard from '../SessionCard.svelte';

const joined = (over = {}) => ({
	id: 's1', name: 'Movies — Archive', media_type: 'movie', is_builtin: false,
	rip_preset_id: 'r1', transcode_preset_id: 't1', output_path_template: 'movies/{title} ({year}).{ext}', overrides_json: null,
	ripPreset: { id: 'r1', name: 'Movie — Main Feature', track_selection: 'main_feature', output_mode: 'tracks' },
	transcodePreset: { id: 't1', name: 'H.265 MKV', container: 'mkv', codec: 'h265', hw_preference: 'any' },
	...over
} as any);

afterEach(cleanup);

it('renders name, rip+transcode preset names, and a resolved sample path', () => {
	renderComponent(SessionCard, { session: joined(), onedit: vi.fn(), onclone: vi.fn(), ondelete: vi.fn() });
	expect(screen.getByText('Movies — Archive')).toBeInTheDocument();
	expect(screen.getByText('Movie — Main Feature')).toBeInTheDocument();
	expect(screen.getByText('H.265 MKV')).toBeInTheDocument();
	expect(screen.getByText('movies/Fight Club (1999).mkv')).toBeInTheDocument();
});

it('shows "No transcode" when none', () => {
	renderComponent(SessionCard, { session: joined({ transcode_preset_id: null, transcodePreset: undefined }), onedit: vi.fn(), onclone: vi.fn(), ondelete: vi.fn() });
	expect(screen.getByText(/no transcode/i)).toBeInTheDocument();
});

it('has no Apply button (apply happens on the job page)', () => {
	renderComponent(SessionCard, { session: joined(), onedit: vi.fn(), onclone: vi.fn(), ondelete: vi.fn() });
	expect(screen.queryByRole('button', { name: /apply/i })).toBeNull();
});

it('builtin: shows BUILT-IN, View label, disabled Delete', () => {
	const onedit = vi.fn();
	renderComponent(SessionCard, { session: joined({ is_builtin: true }), onedit, onclone: vi.fn(), ondelete: vi.fn() });
	expect(screen.getByText('BUILT-IN')).toBeInTheDocument();
	expect(screen.getByRole('button', { name: /^view$/i })).toBeInTheDocument();
	expect(screen.queryByRole('button', { name: /^edit$/i })).toBeNull();
	expect((screen.getByRole('button', { name: /delete/i }) as HTMLButtonElement).disabled).toBe(true);
});

it('custom: shows Edit label (not View)', () => {
	renderComponent(SessionCard, { session: joined({ is_builtin: false }), onedit: vi.fn(), onclone: vi.fn(), ondelete: vi.fn() });
	expect(screen.getByRole('button', { name: /^edit$/i })).toBeInTheDocument();
	expect(screen.queryByRole('button', { name: /^view$/i })).toBeNull();
});
