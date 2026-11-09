// The Files page's browsing state: the roots, the directory being viewed,
// its sort order and the selection on it.
import { fetchRoots, fetchDirectory } from '$lib/api/files';
import type { FileRoot, DirectoryListing } from '$lib/api/files';

const rootOrder: Record<string, number> = { raw: 0, transcode: 1, completed: 2, music: 3 };

export class FilesBrowser {
	roots = $state<FileRoot[]>([]);
	// Current navigation position: root key + subpath within that root
	current = $state<{ root: string; subpath: string }>({ root: '', subpath: '' });
	listing = $state<DirectoryListing | null>(null);
	loading = $state(true);
	error = $state<string | null>(null);
	filesError = $derived<Error | null>(this.error ? new Error(this.error) : null);

	// Sort state
	sortKey = $state<'name' | 'size' | 'modified'>('name');
	sortDir = $state<'asc' | 'desc'>('asc');

	// Selection state — key is `subpath/name` within the current root
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- plain Set, copy-on-write; reassigning the $state field triggers updates
	selectedKeys = $state(new Set<string>());

	isReadonly = $derived(this.listing?.readonly === true);

	sortedEntries = $derived.by(() => {
		if (!this.listing) return [];
		return [...this.listing.entries].sort((a, b) => {
			if (a.type !== b.type) return a.type === 'directory' ? -1 : 1;
			let cmp: number;
			if (this.sortKey === 'size') {
				cmp = (a.size ?? 0) - (b.size ?? 0);
			} else if (this.sortKey === 'modified') {
				cmp = (a.modified ?? '').localeCompare(b.modified ?? '');
			} else {
				cmp = a.name.toLowerCase().localeCompare(b.name.toLowerCase());
			}
			return this.sortDir === 'asc' ? cmp : -cmp;
		});
	});

	allSelected = $derived(
		this.sortedEntries.length > 0 && this.sortedEntries.every((e) => this.selectedKeys.has(this.selectionKey(e.name)))
	);

	// Build the item subpath for a named entry in the current directory
	itemSubpath = (entryName: string): string => {
		return this.current.subpath ? `${this.current.subpath}/${entryName}` : entryName;
	};

	// Build a selection key (root::subpath) for an entry
	selectionKey = (entryName: string): string => {
		return `${this.current.root}::${this.itemSubpath(entryName)}`;
	};

	toggleSort = (key: 'name' | 'size' | 'modified') => {
		if (this.sortKey === key) {
			this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
		} else {
			this.sortKey = key;
			this.sortDir = key === 'modified' ? 'desc' : 'asc';
		}
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
			this.roots = (await fetchRoots()).sort((a, b) => (rootOrder[a.key ?? ''] ?? 99) - (rootOrder[b.key ?? ''] ?? 99));
			if (this.roots.length > 0 && !this.current.root) {
				this.current = { root: this.roots[0].key, subpath: '' };
			}
		} catch (e) {
			this.error = e instanceof Error ? e.message : 'Failed to load roots';
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
			this.error = e instanceof Error ? e.message : 'Failed to load directory';
			this.listing = null;
		} finally {
			this.loading = false;
		}
	};
}
