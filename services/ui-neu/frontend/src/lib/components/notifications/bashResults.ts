// What Settings > Notifications shows from a bash hook's preview and
// test run.
import type { ScriptInput } from '$lib/api/channels';
import type { ChannelTemplate } from '$lib/types/notifications';

/**
 * The input a preview error says is missing, named the way the Inputs
 * block labels it, or by its key when the inputs don't list it; null
 * for any other error.
 */
export function incompleteInput(error: string | null | undefined, inputs: ScriptInput[]): string | null {
	const m = error?.match(/^input ([A-Z][A-Z0-9_]*) is required$/);
	if (!m) return null;
	return inputs.find((i) => i.key === m[1])?.label ?? m[1];
}

/** The event's template overrides something: a title, a body or an input. */
export function isCustomized(template: ChannelTemplate | undefined): boolean {
	return (
		!!template && (!!template.title || !!template.body || !!(template.inputs && Object.keys(template.inputs).length))
	);
}

/** The ARM_ context variables the script receives, in order. */
export function armContext(env: Record<string, string>): [string, string][] {
	return Object.entries(env).filter(([k]) => k.startsWith('ARM_'));
}
