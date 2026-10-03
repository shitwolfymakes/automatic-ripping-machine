<script lang="ts" module>
	export interface ChoiceOption {
		value: string;
		title: string;
		description: string;
		badge?: string;
	}
</script>

<script lang="ts">
	// A radio group drawn as cards: one choice described by what the operator
	// will experience. Native radios, so arrow keys move between options.

	let {
		name,
		value,
		options,
		onchange,
		disabled = false,
		legend
	}: {
		name: string;
		value: string;
		options: ChoiceOption[];
		onchange: (v: string) => void;
		disabled?: boolean;
		legend?: string;
	} = $props();
</script>

<fieldset class="choice-card-group" {disabled}>
	{#if legend}<legend class="choice-card-legend">{legend}</legend>{/if}
	{#each options as o (o.value)}
		<label class="choice-card" data-selected={o.value === value}>
			<input
				type="radio"
				class="choice-card-radio"
				{name}
				value={o.value}
				checked={o.value === value}
				onchange={() => onchange(o.value)}
			/>
			<span class="choice-card-body">
				<span class="choice-card-title">{o.title}</span>
				{#if o.badge}<span class="badge badge-sm badge-info choice-card-badge">{o.badge}</span>{/if}
				<span class="choice-card-desc">{o.description}</span>
			</span>
		</label>
	{/each}
</fieldset>

<style>
	.choice-card-group {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
		gap: 0.75rem;
		margin: 0;
		border: 0;
		padding: 0;
		min-width: 0;
	}
	.choice-card-legend {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
	}
	.choice-card {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		background: var(--color-surface);
		padding: 1rem;
		cursor: pointer;
		transition:
			border-color var(--motion-fast) var(--ease),
			background var(--motion-fast) var(--ease);
	}
	.choice-card:hover {
		border-color: var(--color-border-strong);
	}
	.choice-card[data-selected='true'] {
		border: 2px solid var(--color-primary);
		padding: calc(1rem - 1px);
		background: var(--color-primary-tint-2);
	}
	.choice-card:focus-within {
		outline: 2px solid var(--color-primary);
		outline-offset: 2px;
	}
	fieldset:disabled .choice-card {
		cursor: not-allowed;
		opacity: 0.6;
	}
	.choice-card-radio {
		margin-top: 0.25rem;
		flex: none;
		accent-color: var(--color-primary);
	}
	.choice-card-body {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 0.25rem;
		min-width: 0;
	}
	.choice-card-title {
		font-weight: 600;
		color: var(--color-text);
	}
	.choice-card-desc {
		font-size: 0.875rem;
		line-height: 1.4;
		color: var(--color-text-muted);
	}
</style>
