// Where a job's season / disc position came from, as a short operator-facing line.
export const PROVENANCE_LABEL: Record<string, string> = {
	manual: 'set by you',
	label: 'from the disc label',
	bd_title: 'from the Blu-ray disc title',
	thediscdb: 'from TheDiscDB',
	episodes_tmdb: 'matched by TMDb',
	episodes_tvmaze: 'matched by TVmaze',
	episodes_tvdb: 'matched by TVDB'
};

const FIELD_LABEL = { season: 'Season', disc_number: 'Disc number', disc_total: 'Disc total' } as const;

export function provenanceLine(
	field: keyof typeof FIELD_LABEL,
	prov: Record<string, string> | null | undefined
): string | null {
	const source = prov?.[field];
	const label = source ? PROVENANCE_LABEL[source] : undefined;
	return label ? `${FIELD_LABEL[field]} ${label}` : null;
}
