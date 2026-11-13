// The Files page's orphan folders modal: the folders on disk that no job
// owns, their selection, and the delete actions on them.
import { fetchOrphanFolders, deleteFolder as deleteOrphanFolder, bulkDeleteFolders } from '$lib/api/maintenance';
import type { OrphanFoldersResponse } from '$lib/api/maintenance';
import type { BulkFeedback } from '$lib/dashboard/bulk-delete-feedback';
import { cleanupFeedback } from '$lib/utils/files';
import { errorMessage } from '$lib/utils/errors';

export class OrphanFolders {
	isOpen = $state(false);
	data = $state<OrphanFoldersResponse | null>(null);
	loading = $state(false);
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- plain Set, copy-on-write; reassigning the $state field triggers updates
	selected = $state<Set<string>>(new Set());
	busy = $state(false);
	feedback = $state<BulkFeedback | null>(null);

	#reload = async () => {
		this.data = await fetchOrphanFolders();
		// eslint-disable-next-line svelte/prefer-svelte-reactivity -- plain Set, copy-on-write; reassigning the $state field triggers updates
		this.selected = new Set();
	};

	open = async () => {
		this.isOpen = true;
		this.loading = true;
		this.feedback = null;
		try {
			await this.#reload();
		} catch {
			this.data = null;
		}
		this.loading = false;
	};

	toggle = (path: string) => {
		// eslint-disable-next-line svelte/prefer-svelte-reactivity -- plain Set, copy-on-write; reassigning the $state field triggers updates
		const next = new Set(this.selected);
		if (next.has(path)) next.delete(path);
		else next.add(path);
		this.selected = next;
	};

	deleteOne = async (path: string) => {
		const name = path.split('/').pop();
		this.busy = true;
		try {
			await deleteOrphanFolder(path);
			this.feedback = { type: 'success', message: `Folder "${name}" deleted` };
			await this.#reload();
		} catch (e) {
			this.feedback = { type: 'error', message: errorMessage(e, 'Delete failed') };
		}
		this.busy = false;
	};

	deleteSelected = async () => {
		this.busy = true;
		try {
			const result = await bulkDeleteFolders([...this.selected]);
			this.feedback = cleanupFeedback(result.removed.length, 'folder', result.errors.length);
			await this.#reload();
		} catch (e) {
			this.feedback = { type: 'error', message: errorMessage(e, 'Bulk delete failed') };
		}
		this.busy = false;
	};
}
