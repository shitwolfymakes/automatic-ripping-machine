// The padding colour is one of the schema's named colours or a custom value
// (such as a hex colour) stored verbatim.

export const PAD_CUSTOM = '__custom__';

export interface PadColorView {
	// The select's value: a listed name, or PAD_CUSTOM.
	selected: string;
	custom: boolean;
	// What the custom text input shows.
	text: string;
}

// A stored value outside the listed names reads as custom; so does a pick of "Custom…" before any text is typed.
export function padColorView(shown: string, names: readonly string[], customOpen: boolean): PadColorView {
	const custom = customOpen || (shown !== '' && !names.includes(shown));
	return { selected: custom ? PAD_CUSTOM : shown, custom, text: custom ? shown : '' };
}
