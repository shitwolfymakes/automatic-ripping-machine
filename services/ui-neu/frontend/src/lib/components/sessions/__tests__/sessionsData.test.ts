import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/sessions', () => ({ fetchSessions: vi.fn() }));
vi.mock('$lib/api/ripPresets', () => ({ fetchRipPresets: vi.fn() }));
vi.mock('$lib/api/transcodePresets', () => ({ fetchTranscodePresets: vi.fn() }));

import { fetchSessions } from '$lib/api/sessions';
import { fetchRipPresets } from '$lib/api/ripPresets';
import { fetchTranscodePresets } from '$lib/api/transcodePresets';
import { createSessionsData } from '../sessionsData.svelte';

const rip = (id: string, media_type = 'movie') => ({ id, name: `rip ${id}`, media_type, is_builtin: false, track_selection: 'main_feature', identification_mode: 'required', output_mode: 'tracks', track_filters_json: null } as any);
const tc = (id: string, media_type = 'movie') => ({ id, name: `tc ${id}`, media_type, is_builtin: false, tool: 'handbrake', container: 'mkv', codec: 'h265', hw_preference: 'any', preset_ref: null, preset_json: null, extra_args: null } as any);
const ses = (id: string, ripId: string, tcId: string | null, media_type = 'movie') => ({ id, name: `ses ${id}`, media_type, is_builtin: false, rip_preset_id: ripId, transcode_preset_id: tcId, output_path_template: 'movies/{title}.{ext}', overrides_json: null } as any);

beforeEach(() => {
	vi.mocked(fetchRipPresets).mockResolvedValue([rip('r1'), rip('r2', 'tv')]);
	vi.mocked(fetchTranscodePresets).mockResolvedValue([tc('t1')]);
	vi.mocked(fetchSessions).mockResolvedValue([ses('s1', 'r1', 't1'), ses('s2', 'r1', null)]);
});

it('joins sessions to their preset objects', async () => {
	const d = createSessionsData();
	await d.load();
	const s1 = d.sessions().find((s) => s.id === 's1')!;
	expect(s1.ripPreset?.name).toBe('rip r1');
	expect(s1.transcodePreset?.name).toBe('tc t1');
	expect(d.sessions().find((s) => s.id === 's2')!.transcodePreset).toBeUndefined();
});

it('computes preset usage counts', async () => {
	const d = createSessionsData();
	await d.load();
	expect(d.ripUsage('r1')).toBe(2); // both sessions use r1
	expect(d.ripUsage('r2')).toBe(0);
	expect(d.transcodeUsage('t1')).toBe(1);
});

it('computes media-type counts incl. all', async () => {
	const d = createSessionsData();
	await d.load();
	expect(d.typeCounts().all).toBe(2);
	expect(d.typeCounts().movie).toBe(2);
	expect(d.typeCounts().tv).toBe(0);
});

it('sets error on failure', async () => {
	vi.mocked(fetchSessions).mockRejectedValueOnce(new Error('boom'));
	const d = createSessionsData();
	await d.load();
	expect(d.error()).toContain('boom');
	expect(d.loading()).toBe(false);
});
