import type { SlimKey } from '$lib/types/api.gen';

// How many of a group's keys the preset stores.
export function changedCount(keys: SlimKey[], stored: (name: string) => boolean): number {
	return keys.filter((key) => stored(key.name)).length;
}

// The group chip's text: nothing for none, else the count.
export function changedLabel(n: number): string | null {
	return n === 0 ? null : `${n} changed`;
}
