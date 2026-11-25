<script lang="ts" generics="K extends string">
	// One radio group of segment buttons in the log terminal's toolbar.
	interface Props {
		/** The group's aria-label. */
		label: string;
		/** The segments, in order. */
		options: { key: K; label: string }[];
		/** The chosen segment's key. */
		value: K;
		/** Each button's data-testid is `<testid>-<key>`. */
		testid: string;
		/** A segment was clicked. */
		onpick: (key: K) => void;
	}

	let { label, options, value, testid, onpick }: Props = $props();
</script>

<div class="log-view-segment-group" role="radiogroup" aria-label={label}>
	{#each options as f (f.key)}
		<button
			type="button"
			role="radio"
			aria-checked={value === f.key}
			data-testid="{testid}-{f.key}"
			onclick={() => {
				onpick(f.key);
			}}
			class="log-view-segment">{f.label}</button
		>
	{/each}
</div>

<style>
	.log-view-segment-group {
		display: flex;
		gap: 2px;
	}
	.log-view-segment {
		border-radius: var(--radius-sm);
		padding: 0.25rem 0.5625rem;
		font-size: 0.75rem;
		line-height: 1rem;
		font-weight: 500;
		color: color-mix(in srgb, var(--color-terminal-ink) 65%, transparent);
		background: transparent;
		transition:
			background-color var(--motion-fast) var(--ease),
			color var(--motion-fast) var(--ease);
	}
	.log-view-segment:hover {
		background: color-mix(in srgb, var(--color-terminal-ink) 6%, transparent);
	}
	.log-view-segment[aria-checked='true'] {
		background: color-mix(in srgb, var(--color-primary) 32%, transparent);
		color: color-mix(in srgb, var(--color-primary) 40%, var(--color-terminal-ink));
	}
</style>
