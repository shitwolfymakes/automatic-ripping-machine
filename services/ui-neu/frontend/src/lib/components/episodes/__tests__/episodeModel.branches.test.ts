import { describe, it, expect } from 'vitest';
import { failedSources, panelState, buildRows } from '../../../episodes/episode-model';
import type { IdentityView, JobView, MatchPreview, TrackView } from '$lib/types/api.gen';

const job = (o: Partial<JobView> = {}) => ({ has_series: true, media_type: 'tv', ...o }) as JobView;
const ident = (o: Record<string, unknown> = {}) => ({ pin: {}, ...o }) as unknown as IdentityView;
const track = (o: Partial<TrackView> = {}) => ({ id: 'trk_0', source_ref: 't00', ...o }) as TrackView;
const preview = (match: Record<string, unknown>) =>
	({ outcomes: [{ matches: [{ source_ref: 't00', ...match }] }] }) as unknown as MatchPreview;

describe('failedSources', () => {
	it('an identity with no sources has none failed', () => {
		expect(failedSources(ident())).toEqual([]);
	});
	it('an error source outside SOURCE_LABEL is labelled by its id', () => {
		const id = ident({ sources: { episodes_other: { status: 'error', detail: 'boom' } } });
		expect(failedSources(id)).toEqual([{ id: 'episodes_other', label: 'episodes_other', detail: 'boom' }]);
	});
	it('an error source with no detail has a null detail', () => {
		const id = ident({ sources: { episodes_tmdb: { status: 'error' } } });
		expect(failedSources(id)).toEqual([{ id: 'episodes_tmdb', label: 'TMDb', detail: null }]);
	});
});

describe('panelState', () => {
	it('an episode source with no status counts as ok', () => {
		expect(panelState(job(), ident({ sources: { episodes_tmdb: {} } }), false)).toBe('applied');
	});
});

describe('buildRows', () => {
	it('a track with no identity provenance has origin none', () => {
		const id = ident({ tracks: [{ track_id: 'trk_0', source_ref: 't00' }] });
		expect(buildRows([track()], id, null)[0].origin).toEqual({ kind: 'none', source: null });
	});
	it('a preview match with nothing set proposes Not placed with an empty name and null confidence', () => {
		const rows = buildRows([track()], ident(), preview({}));
		expect(rows[0].proposed).toEqual({ code: 'Not placed', name: '', confidence: null });
	});
	it('with no duration the track length falls back to the expected duration', () => {
		const rows = buildRows([track({ expected_duration_seconds: 125 })], ident(), null);
		expect(rows[0]).toMatchObject({ length: '2:05', seconds: 125 });
	});
	it('with neither duration the length is a dash and the seconds are null', () => {
		const rows = buildRows([track()], ident(), null);
		expect(rows[0]).toMatchObject({ length: '-', seconds: null });
	});
});
