<script lang="ts">
	interface Props {
		disctype: string | null | undefined;
		size?: string;
		/** The disc type's name is written beside the icon: the icon adds no name of its own. */
		decorative?: boolean;
	}

	let { disctype, size = 'h-6 w-6', decorative = false }: Props = $props();

	const iconMap: Record<string, { src: string; alt: string }> = {
		dvd: { src: '/img/disc-dvd.svg', alt: 'DVD' },
		bluray: { src: '/img/disc-bluray.svg', alt: 'Blu-ray' },
		bluray4k: { src: '/img/disc-bluray4k.svg', alt: '4K UHD' },
		music: { src: '/img/disc-music.svg', alt: 'CD' },
		data: { src: '/img/disc-data.svg', alt: 'Data' }
	};

	let icon = $derived(iconMap[disctype ?? ''] ?? { src: '/img/disc-unknown.svg', alt: 'Unknown' });
</script>

<img
	src={icon.src}
	alt={decorative ? '' : icon.alt}
	class="{size} inline-block"
	title={decorative ? undefined : icon.alt}
/>
