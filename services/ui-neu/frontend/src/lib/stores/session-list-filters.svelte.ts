// The Sessions area's list filters (Sessions, Rip presets, Transcode presets),
// kept outside the lists so they survive a switch to another sub-tab or
// settings tab and back. Saved in sessionStorage: a reload keeps them, a new
// browser tab starts unfiltered.
import { browser } from '$app/environment';
import type { MediaType } from '$lib/types/api.gen';
import type { SourceFilter, TranscodeFilter } from '$lib/sessions/list-filters';

/** The lists that keep their own filters. */
export type FilterList = 'sessions' | 'rip' | 'transcode';

interface Stored {
	type: MediaType | 'all';
	source: SourceFilter;
	search: string;
	transcode: TranscodeFilter;
}

const KEY = 'arm_session_list_filters';
const LISTS: FilterList[] = ['sessions', 'rip', 'transcode'];
const TYPES = new Set<string>(['all', 'movie', 'tv', 'music', 'data', 'iso']);
const SOURCES = new Set<string>(['all', 'builtin', 'custom']);
const TRANSCODES = new Set<string>(['any', 'has', 'none']);

function pick<T extends string>(value: unknown, allowed: Set<string>, fallback: T): T {
	return typeof value === 'string' && allowed.has(value) ? (value as T) : fallback;
}

function readStored(): Partial<Record<FilterList, Partial<Stored>>> {
	if (!browser) return {};
	try {
		const parsed: unknown = JSON.parse(sessionStorage.getItem(KEY) ?? '{}');
		return parsed && typeof parsed === 'object' ? parsed : {};
	} catch {
		return {};
	}
}

/** One list's filters. Each change saves every list. */
class ListFilterState {
	#type = $state<MediaType | 'all'>('all');
	#source = $state<SourceFilter>('all');
	#search = $state('');
	#transcode = $state<TranscodeFilter>('any');

	constructor(stored: Partial<Stored> | undefined) {
		this.load(stored);
	}

	load(stored: Partial<Stored> | undefined): void {
		this.#type = pick(stored?.type, TYPES, 'all');
		this.#source = pick(stored?.source, SOURCES, 'all');
		this.#search = typeof stored?.search === 'string' ? stored.search : '';
		this.#transcode = pick(stored?.transcode, TRANSCODES, 'any');
	}

	get type() {
		return this.#type;
	}
	set type(v) {
		this.#type = v;
		save();
	}
	get source() {
		return this.#source;
	}
	set source(v) {
		this.#source = v;
		save();
	}
	get search() {
		return this.#search;
	}
	set search(v) {
		this.#search = v;
		save();
	}
	/** The Sessions list's transcode filter; the preset lists ignore it. */
	get transcode() {
		return this.#transcode;
	}
	set transcode(v) {
		this.#transcode = v;
		save();
	}

	toJSON(): Stored {
		return { type: this.#type, source: this.#source, search: this.#search, transcode: this.#transcode };
	}
}

const initial = readStored();
const states = Object.fromEntries(LISTS.map((l) => [l, new ListFilterState(initial[l])])) as Record<
	FilterList,
	ListFilterState
>;

function save(): void {
	if (!browser) return;
	try {
		sessionStorage.setItem(KEY, JSON.stringify(states));
	} catch {
		/* storage unavailable: the filters last for this page load */
	}
}

/** The filters of one list, shared by every mount of that list. */
export function listFilters(list: FilterList): ListFilterState {
	return states[list];
}

/** Clears every list's filters and the saved copy (tests, mostly). */
export function resetListFilters(): void {
	for (const l of LISTS) states[l].load(undefined);
	if (!browser) return;
	try {
		sessionStorage.removeItem(KEY);
	} catch {
		/* storage unavailable */
	}
}
