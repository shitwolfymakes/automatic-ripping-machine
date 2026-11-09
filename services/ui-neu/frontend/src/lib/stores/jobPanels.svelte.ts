// The job page's search panel: which one the header card shows below the
// facts, and the search type the title panel opens with.
export type JobPanel = 'title' | 'music' | 'episodes';

export class JobPanels {
	active = $state<JobPanel | null>(null);
	// Search type TitleSearch opens with; set when the episode panel asks for a series search.
	titleInitialType = $state<'movie' | 'tv' | undefined>(undefined);

	toggle = (panel: JobPanel): void => {
		if (panel === 'title') this.titleInitialType = undefined;
		this.active = this.active === panel ? null : panel;
	};

	searchSeries = (): void => {
		this.titleInitialType = 'tv';
		this.active = 'title';
	};
}
