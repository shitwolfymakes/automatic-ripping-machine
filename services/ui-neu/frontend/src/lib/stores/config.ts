import { writable } from 'svelte/store';
import { fetchConfig } from '$lib/api/config';

const _transcoderEnabled = writable<boolean>(true);
// Configured default metadata provider ('tmdb' | 'omdb'); null until hydrated.
const _metadataProvider = writable<string | null>(null);

export const transcoderEnabled = { subscribe: _transcoderEnabled.subscribe };
export const metadataProvider = { subscribe: _metadataProvider.subscribe };

export function setTranscoderEnabled(value: boolean): void {
	_transcoderEnabled.set(value);
}

export async function hydrateConfig(): Promise<void> {
	try {
		const cfg = await fetchConfig();
		_transcoderEnabled.set(cfg.transcoder_enabled);
		_metadataProvider.set(cfg.metadata_provider ?? null);
	} catch {
		_transcoderEnabled.set(true);
		_metadataProvider.set(null);
	}
}
