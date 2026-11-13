// The review card's expanded sections: which one is open (one at a time),
// the Info field to focus, and the search type the title search opens with.
type ReviewSection = 'info' | 'title' | 'music' | 'episodes';

export class ReviewSections {
	active = $state<ReviewSection | null>(null);
	// The Info field to put the cursor in when the card opens Info itself (the Season row's link).
	infoFocus = $state<'season' | null>(null);
	// Search type TitleSearch opens with; set when the episode panel asks for a series search.
	titleInitialType = $state<'movie' | 'tv' | undefined>(undefined);

	// One section open at a time.
	open = (section: ReviewSection | null): void => {
		if (section !== 'info') this.infoFocus = null;
		this.active = section;
	};

	isOpen = (section: ReviewSection): boolean => this.active === section;

	toggle = (section: ReviewSection): void => {
		if (section === 'title') this.titleInitialType = undefined;
		this.open(this.isOpen(section) ? null : section);
	};

	// "Season not set" on the Season row: Info with the cursor in Season.
	openSeason = (): void => {
		this.infoFocus = 'season';
		this.open('info');
	};

	searchSeries = (): void => {
		this.open('title');
		this.titleInitialType = 'tv';
	};

	close = (section: ReviewSection): void => {
		if (this.isOpen(section)) this.active = null;
	};
}
