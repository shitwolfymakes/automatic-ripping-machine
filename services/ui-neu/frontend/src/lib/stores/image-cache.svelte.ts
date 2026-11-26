// The Settings page's image cache: its stats, the loading and busy flags,
// the clear confirmation and the feedback line.
import { fetchImageCacheStats, clearImageCache, type ImageCacheStats } from '$lib/api/maintenance';
import { errorMessage } from '$lib/utils/errors';
import { plural } from '$lib/utils/plural';

export class ImageCache {
	stats = $state<ImageCacheStats | null>(null);
	loading = $state(false);
	busy = $state(false);
	confirmOpen = $state(false);
	feedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	load = async (): Promise<void> => {
		this.loading = true;
		try {
			this.stats = await fetchImageCacheStats();
		} catch {
			this.stats = null;
		}
		this.loading = false;
	};

	clear = async (): Promise<void> => {
		this.busy = true;
		this.confirmOpen = false;
		try {
			const result = await clearImageCache();
			const cleared = result.cleared ?? 0;
			const freedMb = ((result.freed_bytes ?? 0) / 1048576).toFixed(1);
			this.feedback = {
				type: 'success',
				message: `Cleared ${cleared} cached ${plural(cleared, 'image')} (${freedMb} MB)`
			};
			this.stats = await fetchImageCacheStats();
		} catch (e) {
			this.feedback = { type: 'error', message: errorMessage(e, 'Failed to clear cache') };
		}
		this.busy = false;
	};
}
