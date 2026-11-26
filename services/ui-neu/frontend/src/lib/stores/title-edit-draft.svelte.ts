// The title search's "Edit before using": four fields filled from the chosen
// match, and the values Use applies from them or from the match.
import type { MetadataCandidate } from '$lib/types/api.gen';
import type { TitleApplyValues } from '$lib/jobs/resolve';
import { isSeriesKind } from '$lib/match/match';

export class TitleEditDraft {
	/**
	 * Whether the edit fields are open. "Edit before using": the edit fields
	 * start from the selected match and, once opened, are what Use applies.
	 */
	editing = $state(false);
	/** The title field. */
	title = $state('');
	/** The year field, as text. */
	year = $state('');
	/** The type field. */
	type = $state<'movie' | 'series'>('movie');
	/** The poster URL field. */
	posterUrl = $state('');
	/**
	 * True once the operator typed in the poster field; only then is the
	 * poster theirs.
	 */
	posterEdited = $state(false);

	/** Whether Use applies a poster the operator typed. */
	get posterIsManual(): boolean {
		return this.editing && this.posterEdited;
	}

	/** Fills the four fields from a match and clears the poster edit flag. */
	fill = (c: MetadataCandidate): void => {
		this.title = c.title;
		this.year = c.year != null ? String(c.year) : '';
		this.type = isSeriesKind(c.kind) ? 'series' : 'movie';
		this.posterUrl = c.poster_url ?? '';
		this.posterEdited = false;
	};

	/** Opens the fields (filled from the match) or closes them. */
	toggle = (c: MetadataCandidate): void => {
		if (!this.editing) this.fill(c);
		this.editing = !this.editing;
	};

	/** Closes the fields and clears the poster edit flag; the text stays. */
	close = (): void => {
		this.editing = false;
		this.posterEdited = false;
	};

	/**
	 * The values Use applies: the trimmed fields while open (the poster only
	 * when typed, a typed blank is null), else the match's own.
	 */
	values = (c: MetadataCandidate): TitleApplyValues =>
		this.editing
			? {
					title: this.title.trim(),
					year: this.year.trim(),
					isSeries: this.type === 'series',
					poster: this.posterEdited ? this.posterUrl.trim() || null : (c.poster_url ?? null)
				}
			: {
					title: c.title,
					year: c.year != null ? String(c.year) : '',
					isSeries: isSeriesKind(c.kind),
					poster: c.poster_url ?? null
				};
}
