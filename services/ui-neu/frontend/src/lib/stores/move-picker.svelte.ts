// The Files page's bulk move dialog: whether it is open, the folder it is
// browsing, that folder's listing and the subfolders offered as targets.
import { fetchDirectory } from '$lib/api/files';
import type { DirectoryListing } from '$lib/api/files';
import { moveTargetFolders } from '$lib/files/files';
import type { FilesBrowser } from './files-browser.svelte';

export class MovePicker {
	readonly #browser!: FilesBrowser;

	isOpen = $state(false);
	location = $state<{ root: string; subpath: string }>({ root: '', subpath: '' });
	listing = $state<DirectoryListing | null>(null);
	loading = $state(false);

	// Is the picker browsing the same folder the files are being moved from?
	atSource = $derived(
		this.location.root === this.#browser.current.root && this.location.subpath === this.#browser.current.subpath
	);

	// Subfolders in the picker (excluding items being moved)
	folders = $derived.by(() => {
		if (!this.listing) return [];
		// Only exclude selected folders when the picker is browsing the same dir as the source.
		return moveTargetFolders(this.listing.entries, this.#browser.selectedKeys, this.atSource);
	});

	// Can we go up from picker?
	canGoUp = $derived(this.location.subpath !== '' || this.location.root !== this.#browser.current.root);

	constructor(browser: FilesBrowser) {
		this.#browser = browser;
	}

	open = async () => {
		if (this.#browser.selectedKeys.size === 0) return;
		this.location = { root: this.#browser.current.root, subpath: this.#browser.current.subpath };
		this.isOpen = true;
		await this.load(this.#browser.current.root, this.#browser.current.subpath);
	};

	load = async (root: string, subpath: string) => {
		this.loading = true;
		try {
			this.listing = await fetchDirectory(root, subpath);
			this.location = { root, subpath };
		} catch {
			// stay on current listing
		} finally {
			this.loading = false;
		}
	};

	goUp = async () => {
		if (!this.canGoUp) return;
		// Go up within the same root. At the top of a root there is nowhere to
		// go, since the picker does not switch roots.
		if (this.listing?.parent_subpath != null) {
			await this.load(this.location.root, this.listing.parent_subpath);
		}
	};

	close = () => {
		this.isOpen = false;
		this.listing = null;
	};

	displayPath(): string {
		const rootObj = this.#browser.roots.find((r) => r.key === this.location.root);
		const rootLabel = rootObj?.label ?? this.location.root;
		if (!this.location.subpath) return rootLabel;
		return `${rootLabel}/${this.location.subpath}`;
	}
}
