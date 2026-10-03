<script lang="ts">
	import Glyph from './Glyph.svelte';
	import { middleTruncate } from '$lib/utils/truncate';

	interface Props {
		name: string;
		/** What the virtual drive rips: an .iso file or a disc folder. */
		kind?: 'iso' | 'folder';
	}

	let { name, kind = 'iso' }: Props = $props();
	let isFolder = $derived(kind === 'folder');

	// Desktop keeps 36 characters, mobile (below the 640px breakpoint) keeps
	// 26. Both truncations are rendered and CSS (the sm: breakpoint) picks
	// which one shows, rather than a matchMedia listener in script.
	let desktopName = $derived(middleTruncate(name, 36));
	let mobileName = $derived(middleTruncate(name, 26));
</script>

<span class="chip chip-info chip-sm" title={name} aria-label="{isFolder ? 'Disc folder' : 'ISO file'} {name}">
	<span class="inline-flex items-center gap-1 iso-source-chip-lead">
		<Glyph name={isFolder ? 'folder' : 'disc-3'} class="h-3 w-3" />
		{isFolder ? 'Folder' : 'ISO'}
	</span>
	<span class="hidden sm:inline iso-source-chip-name-desktop">{desktopName}</span>
	<span class="sm:hidden iso-source-chip-name-mobile">{mobileName}</span>
</span>

<style>
	/* the lead segment (icon + "ISO" / "Folder") reads as one unit, distinct from the
	   file name that follows it */
	.iso-source-chip-lead {
		font-weight: 600;
	}
</style>
