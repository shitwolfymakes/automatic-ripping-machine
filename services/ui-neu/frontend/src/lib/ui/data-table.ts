// The shapes DataTable draws: a column says what each cell shows, and a cell
// is the text, sub line, pill and badges of one value.
import type { MediaType } from '$lib/types/api.gen';

export type BadgeTone = 'warn' | 'info' | 'neutral';

type PillTone = MediaType | 'custom' | 'builtin';

export type CellContent = {
	text: string;
	/** Draw the cell as an uppercase pill: a media-type pill, or the Custom / Built-in tag. */
	pill?: { tone: PillTone };
	sub?: string;
	muted?: boolean;
	/** Draw the text in the monospace face (paths). */
	mono?: boolean;
	badges?: Array<{ text: string; tone: BadgeTone }>;
};

export interface TableColumn<R> {
	id: string;
	header: string;
	align?: 'start' | 'end';
	cell: (row: R) => CellContent;
}

type CellView = {
	/** Class of the cell's td (and of its column's th). */
	className: string;
	/** Tooltip of the plain text; a pill carries none. */
	title: string | undefined;
	text: string;
	sub: string | undefined;
	pill: { kind: 'media' | 'tag'; tone: PillTone; text: string } | undefined;
	badges: CellContent['badges'];
	/** Class of the plain-text span. */
	textClass: string;
	/** Value of the td's data-muted attribute. */
	muted: 'true' | undefined;
};

const MEDIA_TONES: ReadonlySet<PillTone> = new Set(['movie', 'tv', 'music', 'data', 'iso']);

export function alignClass(align?: 'start' | 'end'): string {
	return align === 'end' ? 'data-table-num' : '';
}

function pillView(cell: CellContent): CellView['pill'] {
	if (!cell.pill) return undefined;
	const kind = MEDIA_TONES.has(cell.pill.tone) ? 'media' : 'tag';
	return { kind, tone: cell.pill.tone, text: cell.text };
}

/** What one cell draws: its classes, tooltips, pill and badges, decided once. */
export function cellView(cell: CellContent, align?: 'start' | 'end'): CellView {
	const pill = pillView(cell);
	return {
		className: alignClass(align),
		title: pill ? undefined : cell.text,
		text: cell.text,
		sub: cell.sub,
		pill,
		badges: cell.badges,
		textClass: cell.mono ? 'data-table-text mono' : 'data-table-text',
		muted: cell.muted ? 'true' : undefined
	};
}
