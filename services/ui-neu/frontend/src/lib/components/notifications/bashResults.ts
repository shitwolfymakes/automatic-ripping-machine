// What Settings > Notifications shows from a bash hook's preview and
// test run.
import type { BashPreviewResult, ScriptInput } from '$lib/api/channels';
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

/** A run result as the preview endpoint returns it. */
type RunResult = NonNullable<BashPreviewResult['result']>;

/** A preview that failed before the hook answered, carrying the error. */
export function failedPreview(message: string): BashPreviewResult {
	return {
		title: '',
		body: '',
		inputs: {},
		env: {},
		argv: [],
		error: message,
		result: null
	};
}

/** A test run that failed before the hook answered, carrying the error. */
export function failedRun(message: string): RunResult {
	return {
		ok: false,
		exit_code: null,
		duration_ms: 0,
		stdout: '',
		stderr: '',
		error: message
	};
}

/**
 * A test run's result line: passed or failed, the exit code when there
 * is one, how long it took, and the error of a failure that has no exit
 * code.
 */
export function runSummary(result: RunResult): string {
	const exitCode = result.exit_code !== null ? `: exit code ${result.exit_code}` : '';
	const error = !result.ok && result.exit_code === null && result.error ? `: ${result.error}` : '';
	return `${result.ok ? 'Passed' : 'Failed'}${exitCode} after ${(result.duration_ms / 1000).toFixed(1)}s${error}`;
}
