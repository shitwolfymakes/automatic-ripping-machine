// The Files page's browsing state: the roots, the directory being viewed,
// its sort order and the selection on it.
import { fetchRoots, fetchDirectory } from '$lib/api/files';
import type { FileRoot, DirectoryListing } from '$lib/api/files';
import { sortEntries, nextSort, sortRoots, childSubpath, selectionKey as buildSelectionKey } from '$lib/utils/files';
import type { SortKey, SortDir } from '$lib/utils/files';
import { errorMessage } from '$lib/utils/errors';

export class FilesBrowser {
	roots = $state<FileRoot[]>([]);
	// Current navigation position: root key + subpath within that root
	current = $state<{ root: string; subpath: string }>({ root: '', subpath: '' });
	listing = $state<DirectoryListing | null>(null);
	loading = $state(true);
	error = $state<string | null>(null);
	filesError = $derived<Error | null>(this.error ? new Error(this.error) : null);

	// Sort state
	sortKey = $state<SortKey>('name');
	sortDir = $state<SortDir>('asc');

	// Selection state — key is `root::subpath` (built by selectionKey)
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- plain Set, copy-on-write; reassigning the $state field triggers updates
	selectedKeys = $state(new Set<string>());

	isReadonly = $derived(this.listing?.readonly === true);

	sortedEntries = $derived(this.listing ? sortEntries(this.listing.entries, this.sortKey, this.sortDir) : []);

	allSelected = $derived(
		this.sortedEntries.length > 0 && this.sortedEntries.every((e) => this.selectedKeys.has(this.selectionKey(e.name)))
	);

	// Build the item subpath for a named entry in the current directory
	itemSubpath = (entryName: string): string => {
		return childSubpath(this.current.subpath, entryName);
	};

	// Build a selection key (root::subpath) for an entry
	selectionKey = (entryName: string): string => {
		return buildSelectionKey(this.current.root, this.itemSubpath(entryName));
	};

	toggleSort = (key: SortKey) => {
		const next = nextSort(this.sortKey, this.sortDir, key);
		this.sortKey = next.key;
		this.sortDir = next.dir;
	};

	sortIconDir = (key: string): 'asc' | 'desc' | null => {
		if (this.sortKey !== key) return null;
		return this.sortDir;
	};

	toggleSelect = (entryName: string) => {
		const key = this.selectionKey(entryName);
		// eslint-disable-next-line svelte/prefer-svelte-reactivity -- copy-on-write; reassigning the $state variable triggers updates
		const next = new Set(this.selectedKeys);
		if (next.has(key)) next.delete(key);
		else next.add(key);
		this.selectedKeys = next;
	};

	toggleSelectAll = () => {
		if (!this.listing) return;
		if (this.allSelected) {
			// eslint-disable-next-line svelte/prefer-svelte-reactivity -- plain Set, copy-on-write; reassigning the $state field triggers updates
			this.selectedKeys = new Set();
		} else {
			// eslint-disable-next-line svelte/prefer-svelte-reactivity -- plain Set, copy-on-write; reassigning the $state field triggers updates
			this.selectedKeys = new Set(this.sortedEntries.map((e) => this.selectionKey(e.name)));
		}
	};

	loadRoots = async () => {
		try {
			this.roots = sortRoots(await fetchRoots());
			if (this.roots.length > 0 && !this.current.root) {
				this.current = { root: this.roots[0].key, subpath: '' };
			}
		} catch (e) {
			this.error = errorMessage(e, 'Failed to load roots');
		}
	};

	navigate = async (root: string, subpath: string) => {
		this.loading = true;
		this.error = null;
		this.current = { root, subpath };
		// eslint-disable-next-line svelte/prefer-svelte-reactivity -- plain Set, copy-on-write; reassigning the $state field triggers updates
		this.selectedKeys = new Set();
		try {
			this.listing = await fetchDirectory(root, subpath);
		} catch (e) {
			this.error = errorMessage(e, 'Failed to load directory');
			this.listing = null;
		} finally {
			this.loading = false;
		}
	};
}
