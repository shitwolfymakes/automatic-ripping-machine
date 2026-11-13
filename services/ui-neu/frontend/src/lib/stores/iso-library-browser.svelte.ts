// What the ISO picker has loaded from the library (the ISO listing or the
// disc-folder listing), with its loading, not-configured and error states,
// where only the newest load's answer is applied.
import { fetchIsoFolders, fetchIsoLibrary } from '$lib/api/iso';
import { ApiError } from '$lib/api/client';
import type { IsoFolderListing, IsoLibraryListing } from '$lib/types/api.gen';

export class IsoLibraryBrowser {
	subpath = $state('');
	listing = $state<IsoLibraryListing | null>(null);
	folderListing = $state<IsoFolderListing | null>(null);
	hostPath = $state('');
	loading = $state(false);
	notConfigured = $state(false);
	loadError = $state<Error | null>(null);
	/** The row that holds the list's tab stop; each applied load puts it back
	 *  on the first row. */
	activeIndex = $state(0);

	// Monotonic request counter: a load's own response is applied only if it
	// is still the most recently started one — an older, slower-resolving
	// request (e.g. a folder navigated away from) is discarded instead of
	// clobbering the newer listing.
	#seq = 0;

	#begin(path: string): number {
		this.subpath = path;
		this.loading = true;
		this.notConfigured = false;
		this.loadError = null;
		return ++this.#seq;
	}

	#fail(seq: number, e: unknown): void {
		if (seq !== this.#seq) return;
		this.listing = null;
		this.folderListing = null;
		this.loading = false;
		if (e instanceof ApiError && e.status === 503) {
			this.notConfigured = true;
		} else {
			this.loadError = e instanceof Error ? e : new Error('Could not load the library.');
		}
	}

	/** Resolves true when this load's listing was applied, and false when it
	 *  failed or a newer load superseded it. */
	loadLibrary = async (path: string): Promise<boolean> => {
		const seq = this.#begin(path);
		try {
			const result = await fetchIsoLibrary(path);
			if (seq !== this.#seq) return false; // a newer navigation has since started; discard this stale response
			this.listing = result;
			this.hostPath = result.host_path;
			this.activeIndex = 0;
			// Clear loading BEFORE the caller's refocus wait, not in a trailing
			// `finally` — LoadState only mounts the ready rows once `loading`
			// goes false, and the caller's refocus needs those rows mounted.
			this.loading = false;
			return true;
		} catch (e) {
			this.#fail(seq, e);
			return false;
		}
	};

	loadFolders = async (): Promise<void> => {
		const seq = this.#begin('');
		try {
			const folders = await fetchIsoFolders();
			if (seq !== this.#seq) return;
			this.folderListing = folders;
			this.hostPath = folders.host_path;
			this.activeIndex = 0;
			this.loading = false;
		} catch (e) {
			this.#fail(seq, e);
		}
	};

	// Built from the server's own `listing.subpath`, not the optimistic
	// `subpath` state — the two can briefly disagree while a navigation is
	// in flight, and this is what decides the path sent to startIsoRip, so it
	// must always match whichever listing is actually on screen.
	entryPath = (name: string): string => {
		const base = this.listing?.subpath ?? '';
		return base ? `${base}/${name}` : name;
	};

	reset = (): void => {
		this.subpath = '';
		this.listing = null;
		this.folderListing = null;
		this.hostPath = '';
		this.notConfigured = false;
		this.loadError = null;
		this.activeIndex = 0;
	};
}
