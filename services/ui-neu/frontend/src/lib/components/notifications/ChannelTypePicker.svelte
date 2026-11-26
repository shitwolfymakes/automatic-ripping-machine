<script lang="ts">
	// The add-channel form's delivery-type cards: one radio card per
	// type, the service type marked as recommended.
	import type { ChannelType } from '$lib/types/notifications';

	interface Props {
		/** The type picked now. */
		selected: ChannelType;
		onpick: (type: ChannelType) => void;
	}
	let { selected, onpick }: Props = $props();

	const types: { key: ChannelType; label: string; recommended?: boolean }[] = [
		{ key: 'apprise', label: 'Service (Apprise)', recommended: true },
		{ key: 'webhook', label: 'Webhook' },
		{ key: 'bash', label: 'Bash script' }
	];
</script>

<fieldset class="add-channel-form-types">
	<legend class="sr-only">Delivery type</legend>
	{#each types as t (t.key)}
		<label class="channel-type-option" data-selected={selected === t.key}>
			<input
				type="radio"
				name="delivery"
				class="sr-only"
				aria-label={t.label}
				checked={selected === t.key}
				onchange={() => onpick(t.key)}
			/>
			<span class="channel-type-option-label">{t.label}</span>
			{#if t.recommended}<span class="badge badge-sm channel-type-option-badge">RECOMMENDED</span>{/if}
		</label>
	{/each}
</fieldset>

<style>
	.add-channel-form-types {
		position: relative;
		display: grid;
		grid-template-columns: 1fr;
		gap: 0.75rem;
	}
	@media (min-width: 640px) {
		.add-channel-form-types {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	/* channel-type-option: a selectable card, one per delivery type. No block
	   covers this shape (a bordered card wrapping a hidden radio input, with
	   a data-selected state on the label carrying the selected look; the radio
	   itself carries the checked state for assistive tech). */
	.channel-type-option {
		position: relative;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		background: var(--color-primary-tint-1);
		padding: 1rem;
		cursor: pointer;
	}
	.channel-type-option[data-selected='true'] {
		border-color: var(--color-primary);
		background: var(--color-primary-tint-2);
	}
	.channel-type-option-label {
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 600;
		color: var(--color-text-secondary);
	}
	/* this badge is bg-primary/15 text-primary rather than badge-sm's default tint-2/primary-text
	   pairing (the nearest documented tint, tint-3 at 20%, is visibly more saturated than the 15%
	   wanted here - color-mix against --color-primary at an exact 15% gives it, the same pattern
	   tokens.css itself uses for tint-1/2/3), and its size (9.5px) sits a hair under badge-sm's
	   0.625rem. */
	.channel-type-option-badge {
		position: absolute;
		top: 0.75rem;
		right: 0.75rem;
		background: color-mix(in srgb, var(--color-primary) 15%, transparent);
		color: var(--color-primary);
		font-size: 9.5px;
		letter-spacing: 0.05em;
	}
</style>
