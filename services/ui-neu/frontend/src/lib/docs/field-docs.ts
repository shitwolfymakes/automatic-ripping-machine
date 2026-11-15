// Resolves a form field's documentation link from the committed copy of the
// field docs registry (packages/arm_common/arm_common/field_docs.json).
import registry from './field-docs.json';

export type DocsLink = { type: 'external'; url: string } | { type: 'internal'; page: string; section?: string };

type Entry = DocsLink | { none: string };

const FIELDS = registry.fields as Record<string, Entry>;

function isLink(entry: Entry | undefined): entry is DocsLink {
	return entry !== undefined && 'type' in entry;
}

// The link for a field id. `fallbackId` names a broader entry (a HandBrake key's
// group) used when the id itself has none; an opt-out entry yields null.
export function docsLinkFor(id: string, fallbackId?: string): DocsLink | null {
	const own = FIELDS[id];
	if (own !== undefined) return isLink(own) ? own : null;
	const fallback = fallbackId === undefined ? undefined : FIELDS[fallbackId];
	return isLink(fallback) ? fallback : null;
}

// The link for one HandBrake setting: its own entry when it has one, else its group's.
export function handbrakeKeyDocs(tab: string, group: string, name: string): DocsLink | null {
	return docsLinkFor(`handbrake.key.${name}`, `handbrake.group.${tab}.${group}`);
}

// Encoder family ids start with the hardware family (nvenc_h264, qsv_av1, vce_h265);
// everything else (x264, svt_av1, ...) shares the default entry.
const FAMILY_PREFIXES: Array<[RegExp, string]> = [
	[/^nvenc/, 'nvenc'],
	[/^qsv/, 'qsv'],
	[/^(vce|vcn)/, 'vcn']
];

export function familyDocs(family: string): DocsLink | null {
	const name = FAMILY_PREFIXES.find(([prefix]) => prefix.test(family))?.[1] ?? 'default';
	return docsLinkFor(`handbrake.family.${name}`);
}

// The anchor the docs site gives a heading (github-slugger): lowercase, drop
// everything but letters, marks, digits, `_`, `-` and spaces, then spaces -> `-`.
// Repeated headings on one page get a numeric suffix on the site; a link names
// the first occurrence, so no suffix is built here.
export function headingAnchor(text: string): string {
	return text
		.toLowerCase()
		.replace(/[^\p{L}\p{M}\p{N}\p{Pc}\- ]/gu, '')
		.replaceAll(' ', '-');
}

export function helpHref(link: Extract<DocsLink, { type: 'internal' }>): string {
	const route = `/help/${link.page}`;
	return link.section === undefined ? route : `${route}#${headingAnchor(link.section)}`;
}

// The href a link opens; undefined for no link, so a caller can bind it directly.
export function docsHref(link: DocsLink | null): string | undefined {
	if (link === null) return undefined;
	return link.type === 'external' ? link.url : helpHref(link);
}
