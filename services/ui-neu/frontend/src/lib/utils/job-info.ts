// Pure helpers for JobInfoForm, the job's identity and disc fields; the
// component decides when each runs.
import type { ResolveJobBody } from '$lib/api/jobs';
import type { JobView } from '$lib/types/api.gen';

/** The text each of the form's fields shows. */
export interface JobInfoText {
	title: string;
	year: string;
	season: string;
	discNumber: string;
	discTotal: string;
}

const numberText = (v: number | null | undefined) => (v != null ? String(v) : '');

/** The job's identity and disc fields as the form shows them: '' when missing. */
export function jobInfoText(
	job: Pick<JobView, 'title' | 'year' | 'season' | 'disc_number' | 'disc_total'>
): JobInfoText {
	return {
		title: job.title ?? '',
		year: numberText(job.year),
		season: numberText(job.season),
		discNumber: numberText(job.disc_number),
		discTotal: numberText(job.disc_total)
	};
}

// A cleared number input binds as null, not ''.
function num(v: string | null | undefined): number | null {
	const t = String(v ?? '').trim();
	return t === '' ? null : Number(t);
}

/**
 * The identify request from the form's fields. Season is sent only when
 * touched: omitted keeps the stored value, null forgets it.
 */
export function jobInfoResolveBody(fields: JobInfoText, seasonTouched: boolean): ResolveJobBody {
	return {
		title: fields.title.trim(),
		year: num(fields.year),
		...(seasonTouched ? { season: num(fields.season) } : {}),
		disc_number: num(fields.discNumber),
		disc_total: num(fields.discTotal)
	};
}
