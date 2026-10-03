<script lang="ts">
	import type { SetupView } from '$lib/types/api.gen';
	import Glyph from '$lib/components/Glyph.svelte';
	import SetupConfigFields from '../SetupConfigFields.svelte';
	import type { StepCommitResult } from '../steps';

	// Step 5 (optional): title lookup keys, tested in place (setup spec §5.6).
	let { view }: { view: SetupView; setBlocked?: (reason: string | null) => void } = $props();
	void view;
	let fields: SetupConfigFields | undefined = $state();

	// Built-in services that need nothing from the operator: static facts, not settings.
	const KEYLESS = [
		{ name: 'TVmaze', what: 'TV episode lookup' },
		{ name: 'MusicBrainz', what: 'Music CDs' },
		{ name: 'ARM disc database', what: 'Disc fingerprints from other ARM users' },
		{ name: 'TheDiscDB', what: 'Disc maps that label titles and pick the main feature' }
	];

	export async function commit(): Promise<StepCommitResult> {
		if (!fields || !(await fields.save())) return false;
		return fields.isSet('tmdb_api_key') || fields.isSet('omdb_api_key') ? 'done' : 'attention';
	}
</script>

<div class="stack stack-lg">
	<SetupConfigFields bind:this={fields} step="metadata" />

	<section class="panel stack">
		<h2 class="metadata-step-title">Already working</h2>
		<p class="metadata-step-help">TV episode lookup, music CDs and disc matching work without any key.</p>
		<ul class="metadata-step-keyless">
			{#each KEYLESS as k (k.name)}
				<li class="list-row list-row-compact metadata-step-row">
					<span class="metadata-step-name">{k.name}</span>
					<span class="metadata-step-what">{k.what}</span>
					<span class="chip chip-sm chip-success"><Glyph name="check" class="h-3 w-3" />No key needed</span>
				</li>
			{/each}
		</ul>
	</section>

	<p class="metadata-step-help">
		<Glyph name="info" class="inline h-4 w-4" /> If you skip this step, ARM names files from the disc label and you'll confirm
		titles by hand.
	</p>
</div>

<style>
	.metadata-step-title {
		font-size: 1.0625rem;
		font-weight: 600;
	}
	.metadata-step-help {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
	.metadata-step-keyless {
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.metadata-step-row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.25rem 1rem;
		cursor: default;
	}
	.metadata-step-name {
		min-width: 9rem;
		font-weight: 600;
	}
	.metadata-step-what {
		flex: 1 1 10rem;
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
</style>
