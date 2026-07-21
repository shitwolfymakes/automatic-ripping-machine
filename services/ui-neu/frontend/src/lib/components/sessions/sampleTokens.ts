import type { MediaType } from '$lib/types/api.gen';

export const MEDIA_SAMPLE: Record<MediaType, Record<string, string>> = {
	movie: { title: 'Fight Club', year: '1999', track: '01', duration_human: '2h 19m', transcode_slug: 'h265', ext: 'mkv' },
	tv: { show: 'Breaking Bad', year: '2008', season: '01', disc: '1', track: '03', episode: '03', episode_title: 'Bag', duration_human: '47m', transcode_slug: 'h265', ext: 'mkv' },
	music: { artist: 'Radiohead', album: 'OK Computer', disc: '1', track: '06', track_title: 'Karma Police', transcode_slug: 'flac', ext: 'flac' },
	data: { title: 'Install Disc' },
	iso: { title: 'The Matrix', year: '1999', ext: 'iso' }
};

export function resolveSample(template: string, mediaType: MediaType): string {
	const map = MEDIA_SAMPLE[mediaType] ?? {};
	return template.replace(/\{(\w+)\}/g, (m, key) => (key in map ? map[key] : m));
}
