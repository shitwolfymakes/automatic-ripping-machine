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
export const RIP_SPEED_MIN = 1;

/** The highest rip speed the drive settings accept. */
export const RIP_SPEED_MAX = 99;

/**
 * The rip speed to save: the speed, null to clear it (max speed), or
 * undefined when the input is not a valid speed.
 */
export function parseRipSpeed(raw: string | number | null | undefined): number | null | undefined {
	return parseWholeNumber(raw, RIP_SPEED_MIN, RIP_SPEED_MAX);
}

/** A parsed prescan override: the value to store and whether it was the default. */
export interface PrescanInput {
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
