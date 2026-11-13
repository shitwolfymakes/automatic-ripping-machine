// Edits to a subscribed event's message template on a notification
// channel: a script-input override, and a variable token spliced into
// the title or the body.
import type { ChannelTemplate } from '$lib/types/notifications';

/** A template's two text fields. */
export type TemplateField = 'title' | 'body';

/**
 * The overrides with the input set to the value, or removed when the
 * value is blank; null when none are left.
 */
export function withInput(
	inputs: ChannelTemplate['inputs'],
	inputKey: string,
	value: string
): Record<string, string> | null {
	const next = { ...(inputs ?? {}) };
	if (value === '') delete next[inputKey];
	else next[inputKey] = value;
	return Object.keys(next).length ? next : null;
}

/**
 * The text with the token in place of the selection from start to end,
 * each clamped to the text, and the caret just after the token.
 */
export function spliceToken(text: string, start: number, end: number, token: string): { text: string; caret: number } {
	const from = Math.min(start, text.length);
	const to = Math.min(end, text.length);
	const next = text.slice(0, from) + token + text.slice(to);
	const caret = from + token.length;
	return { text: next, caret };
}

/**
 * The template with the field's text set, null when blank. It keeps
 * only the title and the body, so the event's input overrides are
 * dropped; #539 tracks that.
 */
export function withText(template: ChannelTemplate, field: TemplateField, text: string): ChannelTemplate {
	return {
		title: field === 'title' ? text || null : (template.title ?? null),
		body: field === 'body' ? text || null : (template.body ?? null)
	};
}
