/**
 * The noun for a count: the singular form for exactly one, otherwise the
 * plural form (the singular with an "s" unless one is given).
 */
export function plural(count: number, singular: string, pluralForm: string = `${singular}s`): string {
	return count === 1 ? singular : pluralForm;
}
