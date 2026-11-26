/**
 * Reads a whole number from a settings input: null when the input is blank,
 * undefined when it is not a number or falls outside min..max.
 */
function parseWholeNumber(
	raw: string | number | null | undefined,
	min: number,
	max: number
): number | null | undefined {
	// bind:value on a number input can hand us a number; String() it before
	// trimming.
	const trimmed = String(raw ?? '').trim();
	if (trimmed === '') return null;
	const parsed = parseInt(trimmed, 10);
	if (isNaN(parsed) || parsed < min || parsed > max) return undefined;
	return parsed;
}

/** The lowest rip speed the drive settings accept. */
const RIP_SPEED_MIN = 1;

/** The highest rip speed the drive settings accept. */
const RIP_SPEED_MAX = 99;

/**
 * The rip speed to save: the speed, null to clear it (max speed), or
 * undefined when the input is not a valid speed.
 */
export function parseRipSpeed(raw: string | number | null | undefined): number | null | undefined {
	return parseWholeNumber(raw, RIP_SPEED_MIN, RIP_SPEED_MAX);
}

/** A parsed prescan override: the value to store and whether it was the default. */
interface PrescanInput {
	value: number | null;
	matchesDefault: boolean;
}

/**
 * The prescan override to save, or undefined when the input is not a valid
 * number in range. A value equal to the global default is stored as null, so
 * the drive keeps following the default.
 */
export function parsePrescanInput(
	raw: string | number | null | undefined,
	range: { min: number; max: number },
	globalDefault: number | undefined
): PrescanInput | undefined {
	const parsed = parseWholeNumber(raw, range.min, range.max);
	if (parsed === undefined) return undefined;
	if (parsed !== null && parsed === globalDefault) return { value: null, matchesDefault: true };
	return { value: parsed, matchesDefault: false };
}

/** The text a number input shows for a stored number: blank when there is none. */
export function numberInputText(value: number | null | undefined): string {
	return value != null ? String(value) : '';
}

/** The drive fields that hold a prescan override. */
export type PrescanKey = 'prescan_cache_mb' | 'prescan_timeout' | 'prescan_retries' | 'disc_enum_timeout';

/** One prescan override input: the drive field it edits and how it is shown. */
export interface PrescanField {
	key: PrescanKey;
	label: string;
	unit: string;
	min: number;
	max: number;
	tooltip: string;
}

/**
 * The prescan override inputs, in display order. An empty input means the
 * drive follows the global default.
 */
export const PRESCAN_FIELDS: readonly PrescanField[] = [
	{
		key: 'prescan_cache_mb',
		label: 'Pre-scan Cache',
		unit: 'MB',
		min: 1,
		max: 1024,
		tooltip: 'Community recommends 64-128 for scratched or damaged discs'
	},
	{
		key: 'prescan_timeout',
		label: 'Pre-scan Timeout',
		unit: 's',
		min: 30,
		max: 3600,
		tooltip: 'Community recommends 600 for slow or damaged DVD/BD media'
	},
	{
		key: 'prescan_retries',
		label: 'Pre-scan Retries',
		unit: '',
		min: 1,
		max: 10,
		tooltip: 'Community recommends 3-5 retries for problematic drives'
	},
	{
		key: 'disc_enum_timeout',
		label: 'Enum Timeout',
		unit: 's',
		min: 10,
		max: 600,
		tooltip: 'Community recommends 120 for drives that are slow to spin up'
	}
];

/** The text each prescan input shows for a drive: blank when it has no override. */
export function prescanInputTexts(d: { [K in PrescanKey]?: number | null } | undefined): Record<PrescanKey, string> {
	return {
		prescan_cache_mb: numberInputText(d?.prescan_cache_mb),
		prescan_timeout: numberInputText(d?.prescan_timeout),
		prescan_retries: numberInputText(d?.prescan_retries),
		disc_enum_timeout: numberInputText(d?.disc_enum_timeout)
	};
}
