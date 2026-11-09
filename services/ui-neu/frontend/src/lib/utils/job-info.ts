// Pure helpers for JobInfoForm, the job's identity and disc fields; the
// component decides when each runs.
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
