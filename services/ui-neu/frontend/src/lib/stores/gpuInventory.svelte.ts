// The transcoder page's per-GPU inventory rows: loading them and keeping them
// in step with the transcode events.
import { fetchGpus } from '$lib/api/gpus';
import { wsClient } from '$lib/api/ws';
import type { GpuView } from '$lib/types/api.gen';

const GPU_RELOAD_DEBOUNCE_MS = 300;

export class GpuInventory {
	rows = $state<GpuView[]>([]);

	load = async (): Promise<void> => {
		try {
			this.rows = await fetchGpus();
		} catch {
			// The summary counts still render; the per-device rows just stay hidden.
			this.rows = [];
		}
	};

	watch = (): (() => void) => {
		// Claims, releases and probes all land on transcode.events; reload the
		// per-device rows so they agree with the polled summary count. A burst
		// of task events (a batch finishing) coalesces into one reload.
		wsClient.start();
		let gpuReload: ReturnType<typeof setTimeout> | null = null;
		const unsubscribeGpus = wsClient.subscribe('transcode.events', () => {
			if (gpuReload !== null) clearTimeout(gpuReload);
			gpuReload = setTimeout(() => {
				gpuReload = null;
				this.load();
			}, GPU_RELOAD_DEBOUNCE_MS);
		});
		return () => {
			unsubscribeGpus();
			if (gpuReload !== null) clearTimeout(gpuReload);
		};
	};
}
