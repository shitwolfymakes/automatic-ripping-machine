import { describe, expect, it } from 'vitest';

// Configuration forms label their fields through FieldLabel, which puts the
// field's docs link beside the label. This scan fails on a class="field-label"
// written anywhere else, unless the file or the line is allowed below.
const sources = import.meta.glob(
	['/src/lib/components/**/*.svelte', '/src/routes/**/*.svelte', '!/src/lib/components/shared/FieldLabel.svelte'],
	{ query: '?raw', import: 'default', eager: true }
) as Record<string, string>;

// Task forms and tools that change one job or run one action, not a stored
// setting; their labels stay plain.
const TASK_FORMS: Record<string, string> = {
	'/src/routes/login/+page.svelte': 'login: signing in, not a setting',
	'/src/lib/components/jobs/JobInfoForm.svelte': "job dialog: edits one job's title, year and disc numbers",
	'/src/lib/components/jobs/ApplySessionDialog.svelte': 'job dialog: picks a session for one job',
	'/src/lib/components/jobs/identify/IdentifyCdForm.svelte': 'identify dialog: names one audio CD',
	'/src/lib/components/jobs/identify/IdentifyVideoForm.svelte': 'identify dialog: names one video disc',
	'/src/lib/components/match/TitleSearch.svelte': 'match dialog: searches a title for one job',
	'/src/lib/components/match/TrackTitleSearch.svelte': 'match dialog: searches a title for one track',
	'/src/lib/components/match/track-title-search/TrackOutputOptions.svelte': "match dialog: one track's output name",
	'/src/lib/components/music/music-search/MusicReleaseDetail.svelte': "music dialog: one release's album details",
	'/src/lib/components/episodes/RerunPanel.svelte': 'episode dialog: reruns matching for one disc',
	'/src/lib/components/notifications/BashTestPanel.svelte': 'test send: simulates an event once, saves nothing',
	'/src/lib/components/handbrake/ImportPanel.svelte': 'import: reads a preset file once, not a preset field'
};

// Single lines inside configuration forms that carry the class without being a
// field's label.
const LINES: { file: string; text: string; reason: string }[] = [
	{
		file: '/src/lib/components/settings/DiscHandlingField.svelte',
		text: 'disc-handling-field-title',
		reason: 'compound widget heading with its own docs link'
	},
	{
		file: '/src/lib/components/settings/MakemkvKeyField.svelte',
		text: 'makemkv-key-field-title',
		reason: 'compound widget heading with its own docs link'
	},
	{
		file: '/src/lib/components/settings/IdentityCard.svelte',
		text: '<h5 class="field-label">',
		reason: 'compound widget heading with its own docs link'
	}
];

const CLASS_ATTR = /\bclass="(?:[^"]*\s)?field-label(?:\s[^"]*)?"/;

type Hit = { file: string; line: number; text: string };

function hits(): Hit[] {
	return Object.entries(sources).flatMap(([file, src]) =>
		src.split('\n').flatMap((text, i) => (CLASS_ATTR.test(text) ? [{ file, line: i + 1, text }] : []))
	);
}

function allowed(hit: Hit): boolean {
	return hit.file in TASK_FORMS || LINES.some((l) => l.file === hit.file && hit.text.includes(l.text));
}

describe('field-label scan', () => {
	it('finds the components', () => {
		expect(Object.keys(sources).length).toBeGreaterThan(100);
	});

	it('renders every field label through FieldLabel', () => {
		const stray = hits()
			.filter((h) => !allowed(h))
			.map((h) => `${h.file}:${h.line} renders class="field-label" outside FieldLabel`);
		expect(stray).toEqual([]);
	});

	it('gives every allowance a reason', () => {
		const reasons = [...Object.values(TASK_FORMS), ...LINES.map((l) => l.reason)];
		expect(reasons.filter((r) => r.trim() === '')).toEqual([]);
	});

	it('keeps no allowance that matches nothing', () => {
		const found = hits();
		const staleFiles = Object.keys(TASK_FORMS).filter((f) => !found.some((h) => h.file === f));
		const staleLines = LINES.filter((l) => !found.some((h) => h.file === l.file && h.text.includes(l.text)));
		expect([...staleFiles, ...staleLines.map((l) => `${l.file}: ${l.text}`)]).toEqual([]);
	});

	it('matches the class as a whole token only', () => {
		expect(CLASS_ATTR.test('<span class="field-label">')).toBe(true);
		expect(CLASS_ATTR.test('<span class="field-label tiny">')).toBe(true);
		expect(CLASS_ATTR.test('<label for="x" class="mb-1 field-label">')).toBe(true);
		expect(CLASS_ATTR.test('<span class="music-search-field-label-sm">')).toBe(false);
		expect(CLASS_ATTR.test('.guest-access-field-info :global(.field-label) {')).toBe(false);
	});
});
