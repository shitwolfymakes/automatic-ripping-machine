// The settings filter box and "Changed only" toggle: which inputs each tab shows,
// and how many, so the tab strip's counts and the rendered fields agree.

import type { HandbrakeSchemaSlimView, HandbrakeSettings, SlimFamily, SlimKey } from '$lib/types/api.gen';
import { rowKeys, visibleTrackKeys } from './audioTracks';
import { cardOpen, cardVariant, visibleCardFields, type EncoderCard } from './encoderCards';
import { fieldKind, TABS, type TabId } from './fields';
import {
	audioListShown,
	audioListValue,
	blockOf,
	commonKeys,
	commonOf,
	inheritedDepth,
	keyShown,
	panelContext,
	type BaseValues,
	type FilterState
} from './sidebarModel';
import type { Context } from './dependencyRules';

export interface VisibleInput {
	schema: HandbrakeSchemaSlimView;
	settings: HandbrakeSettings;
	base: BaseValues;
	filter: FilterState;
	// The encoder cards the Video tab renders, with their schema families.
	cards: Array<{ card: EncoderCard; family: SlimFamily }>;
	// The families whose collapsed card the user expanded.
	expanded: string[];
}

export interface VisibleRow {
	key: SlimKey;
	row: 'audio-list' | 'field';
}

export interface VisibleCard {
	card: EncoderCard;
	family: SlimFamily;
	fields: string[];
	// A collapsed card renders its title only, so its fields are not shown yet.
	open: boolean;
}

export interface TabVisible {
	// The tab's common keys that render, in schema order.
	rows: VisibleRow[];
	// The fields of each audio track, by track index; empty unless the audio track list renders.
	tracks: SlimKey[][];
	// The encoder cards with a field to show; Video tab only.
	cards: VisibleCard[];
}

// Each track's visible fields, or null when the audio track list does not render.
function audioTracksOf(input: VisibleInput, key: SlimKey, ctx: Context): SlimKey[][] | null {
	const keys = rowKeys(input.schema);
	const list = audioListValue(key, input.settings, input.base);
	const tracks = list.map((track) => visibleTrackKeys(keys, track, ctx, input.filter));
	return audioListShown(input.filter, key.name in commonOf(input.settings), tracks) ? tracks : null;
}

function visibleCards(input: VisibleInput, ctx: Context): VisibleCard[] {
	return input.cards
		.map(({ card, family }) => {
			const block = blockOf(input.settings, family.name);
			const variant = cardVariant(family, block, inheritedDepth(family, input.base).depth);
			return {
				card,
				family,
				fields: visibleCardFields(input.schema, family, variant, block, ctx, input.filter),
				open: cardOpen(card, block, input.expanded.includes(family.name))
			};
		})
		.filter((c) => c.fields.length > 0);
}

function visibleRows(input: VisibleInput, tab: TabId, ctx: Context, listShown: boolean): VisibleRow[] {
	const common = commonOf(input.settings);
	return commonKeys(input.schema, tab).flatMap((key): VisibleRow[] => {
		if (fieldKind(key) === 'audio-list') return listShown ? [{ key, row: 'audio-list' }] : [];
		return keyShown(key, key.name in common, input.filter, ctx) ? [{ key, row: 'field' }] : [];
	});
}

export function visibleTab(input: VisibleInput, tab: TabId): TabVisible {
	const ctx = panelContext(input.schema, input.settings, input.base);
	const listKey = commonKeys(input.schema, tab).find((k) => fieldKind(k) === 'audio-list');
	const tracks = listKey ? audioTracksOf(input, listKey, ctx) : null;
	return {
		rows: visibleRows(input, tab, ctx, tracks !== null),
		tracks: tracks ?? [],
		cards: tab === 'video' ? visibleCards(input, ctx) : []
	};
}

// The inputs a tab renders: its field rows, each track's fields and each open card's fields.
function inputCount(v: TabVisible): number {
	const fields = v.rows.filter((r) => r.row === 'field').length;
	const trackFields = v.tracks.reduce((n, keys) => n + keys.length, 0);
	const cardFields = v.cards.filter((c) => c.open).reduce((n, c) => n + c.fields.length, 0);
	return fields + trackFields + cardFields;
}

export function tabVisibleCounts(input: VisibleInput): Record<TabId, number> {
	return Object.fromEntries(TABS.map((t) => [t.id, inputCount(visibleTab(input, t.id))])) as Record<TabId, number>;
}

// Stay on the current tab when it has a match; otherwise the first that does.
export function firstTabWithMatch(counts: Record<TabId, number>, current: TabId): TabId {
	if (counts[current] > 0) return current;
	return TABS.find((t) => counts[t.id] > 0)?.id ?? current;
}
