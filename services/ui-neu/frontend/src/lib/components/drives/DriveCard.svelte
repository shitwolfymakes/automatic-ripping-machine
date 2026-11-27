<script lang="ts">
	// A drive's card: the skeleton while it loads, then the essentials or the full variant.
	import type { DriveView as Drive, SessionView, TranscodePresetView } from '$lib/types/api.gen';
	import type { GlobalRipSettings, PrescanKey } from '$lib/drives/settings';
	import DriveCardEssentials from './drive-card/DriveCardEssentials.svelte';
	import DriveCardFull from './drive-card/DriveCardFull.svelte';
	import SkeletonCard from '../shared/SkeletonCard.svelte';

	interface Props {
		drive?: Drive;
		onupdate?: () => void | Promise<void>;
		sessions?: SessionView[];
		// Transcode presets, used only to tell passthrough sessions apart
		// from encode ones on a ripper-only deployment (see DriveCardFull's
		// pickerSessions).
		transcodePresets?: TranscodePresetView[];
		globalDefaults?: Partial<Record<PrescanKey, number>>;
		/** 'essentials': name + 4K only, for the setup walkthrough. */
		variant?: 'full' | 'essentials';
		/** The global auto-rip default a drive with no mode of its own follows. */
		globalAutoRip?: boolean;
		/** The global rip settings a drive with no override of its own follows. */
		globalRip?: GlobalRipSettings;
	}

	let {
		drive,
		onupdate,
		globalDefaults = {},
		sessions = [],
		transcodePresets = [],
		variant = 'full',
		globalAutoRip = true,
		globalRip = { rip_end_on_completion_message: false }
	}: Props = $props();
</script>

{#if !drive}
	<SkeletonCard />
{:else if variant === 'essentials'}
	<DriveCardEssentials {drive} {onupdate} />
{:else}
	<DriveCardFull {drive} {onupdate} {sessions} {transcodePresets} {globalDefaults} {globalAutoRip} {globalRip} />
{/if}
