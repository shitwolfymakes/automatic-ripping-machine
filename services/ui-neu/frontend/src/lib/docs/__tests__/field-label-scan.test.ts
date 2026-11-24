import { describe, expect, it } from 'vitest';
import registry from '../field-docs.json';

// Configuration forms label their fields through FieldLabel, which puts the
// field's docs link beside the label. This scan fails on a class="field-label"
// or a <label> element written anywhere else, on a FieldLabel with no docs id,
// and on a literal docs id the registry doesn't know, unless the file or the
// line is allowed below.
const sources = import.meta.glob(
	['/src/lib/components/**/*.svelte', '/src/routes/**/*.svelte', '!/src/lib/components/shared/FieldLabel.svelte'],
	{ query: '?raw', import: 'default', eager: true }
) as Record<string, string>;

const REGISTRY_IDS = new Set(Object.keys(registry.fields));

// Task forms and tools that change one job or run one action, not a stored
// setting; their labels stay plain.
const TASK_FORMS: Record<string, string> = {
	'/src/routes/login/+page.svelte': 'login: signing in, not a setting',
	'/src/lib/components/jobs/JobInfoForm.svelte': "job dialog: edits one job's title, year and disc numbers",
	'/src/lib/components/jobs/ApplySessionDialog.svelte': 'job dialog: picks a session for one job',
	'/src/lib/components/match/TitleSearch.svelte': 'match dialog: searches a title for one job',
	'/src/lib/components/match/TrackTitleSearch.svelte': 'match dialog: searches a title for one track',
	'/src/lib/components/match/track-title-search/TrackOutputOptions.svelte': "match dialog: one track's output name",
	'/src/lib/components/music/music-search/MusicReleaseDetail.svelte': "music dialog: one release's album details",
	'/src/lib/components/music/music-search/MusicSearchForm.svelte': 'music dialog: searches releases for one disc',
	'/src/lib/components/episodes/RerunPanel.svelte': 'episode dialog: reruns matching for one disc',
	'/src/lib/components/drives/IsoPicker.svelte': 'ISO dialog: picks the session for one ISO rip',
	'/src/lib/components/notifications/BashTestPanel.svelte': 'test send: simulates an event once, saves nothing',
	'/src/lib/components/handbrake/ImportPanel.svelte': 'import: reads a preset file once, not a preset field'
};

type Allowance = { file: string; text: string; reason: string };

// Single lines inside configuration forms that carry the class without being a
// field's label.
const LINES: Allowance[] = [
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

// <label> elements inside configuration forms that name an option, a filter or
// a sub-control rather than a stored setting's field.
const LABEL_ELEMENTS: Allowance[] = [
	{
		file: '/src/lib/components/drives/drive-card/DriveCardFull.svelte',
		text: 'drive-card-uhd"',
		reason: 'the 4K chip is a display toggle; the setting itself is labelled in the essentials form'
	},
	{
		file: '/src/lib/components/handbrake/SettingsTabs.svelte',
		text: 'settings-tabs-changed',
		reason: 'a view filter (changed keys only), not a preset field'
	},
	{
		file: '/src/lib/components/handbrake/TunableField.svelte',
		text: 'tunable-field-inline',
		reason: 'a sub-control of the rotate field, whose FieldLabel carries the docs link'
	},
	{
		file: '/src/lib/components/notifications/ChannelTypePicker.svelte',
		text: 'channel-type-option',
		reason: 'one option card of the delivery type radio group'
	},
	{
		file: '/src/lib/components/notifications/EventSubscriptions.svelte',
		text: '<label class="field field-row">',
		reason: 'one event in the subscription list; its template fields use FieldLabel'
	},
	{
		file: '/src/lib/components/notifications/sections/EventsSection.svelte',
		text: '<label class="field field-row">',
		reason: 'one event in the compact subscription list'
	},
	{
		file: '/src/lib/components/notifications/inbox/InboxHeader.svelte',
		text: 'notifications-page-show-cleared',
		reason: 'an inbox view filter, not a setting'
	},
	{
		file: '/src/lib/components/settings/ChoiceCard.svelte',
		text: 'choice-card',
		reason: 'one option card of a radio group whose heading carries the docs link'
	}
];

// FieldLabel uses that show no docs link on purpose.
const NO_DOCS_ID: Allowance[] = [
	{
		file: '/src/lib/components/settings/MakemkvKeyField.svelte',
		text: 'label="Registration key"',
		reason: 'compound widget; the heading carries the link'
	}
];

const CLASS_ATTR = /\bclass="(?:[^"]*\s)?field-label(?:\s[^"]*)?"/;
const COMMENT_LINE = /^\s*(?:\/\/|\/\*|\*|<!--)/;

type Hit = { file: string; line: number; text: string };

function lineHits(test: (text: string) => boolean): Hit[] {
	return Object.entries(sources).flatMap(([file, src]) =>
		src.split('\n').flatMap((text, i) => (test(text) ? [{ file, line: i + 1, text }] : []))
	);
}

const classHits = (): Hit[] => lineHits((text) => CLASS_ATTR.test(text));

function matches(hit: Hit, list: Allowance[]): boolean {
	return list.some((l) => l.file === hit.file && hit.text.includes(l.text));
}

// The text of a component tag from its `<` to the closing `>`, skipping a `>`
// inside an attribute's braces or quotes.
function tagEnd(src: string, start: number): number {
	let depth = 0;
	let quote = '';
	for (let i = start; i < src.length; i++) {
		const c = src[i];
		if (quote) quote = c === quote ? '' : quote;
		else if (c === '"' || c === "'" || c === '`') quote = c;
		else if (c === '{') depth++;
		else if (c === '}') depth--;
		else if (c === '>' && depth === 0) return i + 1;
	}
	return src.length;
}

// Every `<Name …>` tag in the sources, with the line it starts on.
function tags(name: string): Hit[] {
	const open = new RegExp(`<${name}\\b`, 'g');
	return Object.entries(sources).flatMap(([file, src]) =>
		[...src.matchAll(open)].map((m) => ({
			file,
			line: src.slice(0, m.index).split('\n').length,
			text: src.slice(m.index, tagEnd(src, m.index))
		}))
	);
}

// <label> elements, read as whole tags so an allowance can name any attribute;
// a tag on a comment line is prose, not markup.
function labelHits(): Hit[] {
	return tags('label').filter((t) => !COMMENT_LINE.test(sources[t.file].split('\n')[t.line - 1]));
}

// Whether a FieldLabel tag passes docsId, as an attribute or the {docsId} shorthand.
const HAS_DOCS_ID = /\sdocsId[=\s/>]|\{docsId\}/;

// Literal ids a tag passes in the named attributes.
function literalIds(tag: Hit, attrs: string[]): string[] {
	return attrs.flatMap((attr) => [...tag.text.matchAll(new RegExp(`\\s${attr}="([^"]*)"`, 'g'))].map((m) => m[1]));
}

function unknownIds(name: string, attrs: string[]): string[] {
	return tags(name).flatMap((tag) =>
		literalIds(tag, attrs)
			.filter((id) => !REGISTRY_IDS.has(id))
			.map((id) => `${tag.file}:${tag.line} passes "${id}", which the field docs registry doesn't have`)
	);
}

describe('field-label scan', () => {
	it('finds the components', () => {
		expect(Object.keys(sources).length).toBeGreaterThan(100);
	});

	it('renders every field label through FieldLabel', () => {
		const stray = classHits()
			.filter((h) => !(h.file in TASK_FORMS) && !matches(h, LINES))
			.map((h) => `${h.file}:${h.line} renders class="field-label" outside FieldLabel`);
		expect(stray).toEqual([]);
	});

	it('writes no <label> element outside FieldLabel in a configuration form', () => {
		const stray = labelHits()
			.filter((h) => !(h.file in TASK_FORMS) && !matches(h, LABEL_ELEMENTS))
			.map((h) => `${h.file}:${h.line} writes a <label> outside FieldLabel`);
		expect(stray).toEqual([]);
	});

	it('gives every FieldLabel a docs id', () => {
		const bare = tags('FieldLabel')
			.filter((t) => !HAS_DOCS_ID.test(t.text) && !matches(t, NO_DOCS_ID))
			.map((t) => `${t.file}:${t.line} renders a FieldLabel with no docsId`);
		expect(bare).toEqual([]);
	});

	it('passes only registered literal ids to FieldLabel and FieldDocsLink', () => {
		expect([
			...unknownIds('FieldLabel', ['docsId', 'docsFallbackId']),
			...unknownIds('FieldDocsLink', ['id', 'fallbackId'])
		]).toEqual([]);
	});

	it('gives every allowance a reason', () => {
		const lists = [...LINES, ...LABEL_ELEMENTS, ...NO_DOCS_ID];
		const reasons = [...Object.values(TASK_FORMS), ...lists.map((l) => l.reason)];
		expect(reasons.filter((r) => r.trim() === '')).toEqual([]);
	});

	it('keeps no allowance that matches nothing', () => {
		const lines = classHits();
		const labels = labelHits();
		const fieldLabels = tags('FieldLabel');
		const staleFiles = Object.keys(TASK_FORMS).filter((f) => ![...lines, ...labels].some((h) => h.file === f));
		const stale = [
			...LINES.filter((l) => !lines.some((h) => matches(h, [l]))),
			...LABEL_ELEMENTS.filter((l) => !labels.some((h) => matches(h, [l]))),
			...NO_DOCS_ID.filter((l) => !fieldLabels.some((h) => matches(h, [l])))
		];
		expect([...staleFiles, ...stale.map((l) => `${l.file}: ${l.text}`)]).toEqual([]);
	});

	it('matches the class as a whole token only', () => {
		expect(CLASS_ATTR.test('<span class="field-label">')).toBe(true);
		expect(CLASS_ATTR.test('<span class="field-label tiny">')).toBe(true);
		expect(CLASS_ATTR.test('<label for="x" class="mb-1 field-label">')).toBe(true);
		expect(CLASS_ATTR.test('<span class="music-search-field-label-sm">')).toBe(false);
		expect(CLASS_ATTR.test('.guest-access-field-info :global(.field-label) {')).toBe(false);
	});

	it('treats a tag on a comment line as prose, and finds docsId in either form', () => {
		expect(COMMENT_LINE.test('\t// For a <label for> beside the switch.')).toBe(true);
		expect(COMMENT_LINE.test('\t<!-- a <label> -->')).toBe(true);
		expect(COMMENT_LINE.test('\t\t<label')).toBe(false);
		expect(HAS_DOCS_ID.test('<FieldLabel for="a" label="A" {docsId} />')).toBe(true);
		expect(HAS_DOCS_ID.test('<FieldLabel\n\tdocsId={x}\n/>')).toBe(true);
		expect(HAS_DOCS_ID.test('<FieldLabel for="a" label="A" docsFallbackId="x" />')).toBe(false);
	});

	it('reads a tag across lines and past a ">" inside braces or quotes', () => {
		const src = '<FieldLabel\n\tfor="a"\n\tlabel={x > 1 ? "a>b" : `c>d`}\n\tdocsId="config.x"\n/>\n<p>';
		const tag = src.slice(0, tagEnd(src, 0));
		expect(tag.endsWith('/>')).toBe(true);
		expect(literalIds({ file: 'f', line: 1, text: tag }, ['docsId'])).toEqual(['config.x']);
		expect(tagEnd('<FieldLabel label="x"', 0)).toBe('<FieldLabel label="x"'.length);
	});
});
