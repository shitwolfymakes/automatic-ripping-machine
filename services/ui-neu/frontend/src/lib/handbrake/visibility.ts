// Which fields and encoder cards the sidebar shows under the search text and the changed-only filter.
// Pure functions.

import type { EncoderAvailabilityView, HandbrakeSchemaSlimView, SlimFamily, SlimKey } from '$lib/types/api.gen';
import { baseVideoEncoder, type BaseValues } from './base-values';
import { fieldVisible, type Context } from './dependencyRules';
import { encoderCards, type EncoderCard } from './encoderCards';
import { keysForTab, type TabId } from './fields';

export type FilterState = { text: string; changedOnly: boolean };

// Neither ARM-owned, encoder-specific nor hidden: a field of the preset's common settings.
function isCommonKey(schema: HandbrakeSchemaSlimView, name: string): boolean {
	return (
		!schema.arm_owned_keys.includes(name) &&
		!schema.encoder_specific_keys.includes(name) &&
		!schema.hidden_keys.includes(name)
	);
}

export function commonKeys(schema: HandbrakeSchemaSlimView, tab: TabId): SlimKey[] {
	return keysForTab(schema, tab).filter((k) => isCommonKey(schema, k.name));
}

export function keyShown(key: SlimKey, stored: boolean, f: FilterState, ctx: Context): boolean {
	return fieldVisible(key.name, key.label, f, stored, ctx);
}

// The audio track list holds inputs rather than being one. Under Changed only it shows when the preset
// stores its own list; while filtering, when a track still shows a field.
export function audioListShown(f: FilterState, listStored: boolean, tracks: SlimKey[][]): boolean {
	if (f.changedOnly && !listStored) return false;
	return f.text.trim() === '' || tracks.some((keys) => keys.length > 0);
}

// The encoder cards the Video tab renders for this encoder, base preset and host.
export function panelCards(
	schema: HandbrakeSchemaSlimView,
	encoder: string,
	presetRef: string | null,
	availability: EncoderAvailabilityView[],
	base: BaseValues
): Array<{ card: EncoderCard; family: SlimFamily }> {
	return cardFamilies(encoderCards(encoder, presetRef, schema, availability, baseVideoEncoder(base)), schema);
}

// Each card with its schema family; a card for a family this HandBrake build lacks has nothing to edit.
export function cardFamilies(
	cards: EncoderCard[],
	schema: HandbrakeSchemaSlimView
): Array<{ card: EncoderCard; family: SlimFamily }> {
	return cards.flatMap((card) => {
		const family = schema.families.find((f) => f.name === card.family);
		return family ? [{ card, family }] : [];
	});
}
