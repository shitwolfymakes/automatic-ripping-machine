// The music search's edit fields for the chosen release: album, artist and
// year, seeded from each release, and the disc number and total, seeded from
// the job and kept from one release to the next.
import type { JobView, MetadataReleaseDetail } from '$lib/types/api.gen';

export class MusicReleaseFields {
	/** The album title to apply. */
	album = $state('');
	/** The artist to apply. */
	artist = $state('');
	/** The release year to apply. */
	year = $state('');
	/** The disc number to apply. */
	discNumber = $state('');
	/** The disc total to apply. */
	discTotal = $state('');

	constructor(job: JobView) {
		this.discNumber = job.disc_number != null ? String(job.disc_number) : '';
		this.discTotal = job.disc_total != null ? String(job.disc_total) : '';
	}

	/**
	 * Sets album, artist and year from the release, and fills a blank disc total
	 * from a multi-disc release's disc count. The read of discTotal is tracked
	 * by the caller's effect (see #593).
	 */
	seed = (detail: MetadataReleaseDetail): void => {
		this.artist = detail.artist ?? '';
		this.album = detail.title;
		this.year = detail.year != null ? String(detail.year) : '';
		if (detail.disc_count != null && detail.disc_count > 1 && !this.discTotal) {
			this.discTotal = String(detail.disc_count);
		}
	};
}
