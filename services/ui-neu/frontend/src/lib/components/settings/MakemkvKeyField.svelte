<script lang="ts">
	import { onMount } from 'svelte';
	import type { ConfigFieldMeta, ConfigView, DriveView } from '$lib/types/api.gen';
	import ChoiceCard from '$lib/components/settings/ChoiceCard.svelte';
	import StatusStrip from '$lib/components/shared/StatusStrip.svelte';
	import SecretInput from './SecretInput.svelte';
	import { fetchConfigView, HIDDEN_SECRET } from '$lib/api/config';
	import { fetchDrives } from '$lib/api/drives';
	import { usePoll } from '$lib/utils/poll';
	import { makemkvKeyStatus } from '$lib/drives/makemkv';

	// MakeMKV key: the free monthly beta key (value null) or a purchased key.
	// ARM can't test a key on demand; a drive's ripper verifies it and reports
	// back, so the status line polls the reported state.
	// Rendered for the `makemkv_key` widget in Settings > Metadata and setup.
	let {
		field,
		value = $bindable(),
		onclear
	}: { field: ConfigFieldMeta; value: unknown; onclear?: () => void } = $props();

	let mode = $state<'beta' | 'own'>('beta');
	let cfg = $state<ConfigView | null>(null);
	let drives = $state<DriveView[]>([]);

	onMount(() => {
		mode = value ? 'own' : 'beta';
		const poll = usePoll(async () => {
			const [c, d] = await Promise.all([fetchConfigView(), fetchDrives()]);
			cfg = c;
			drives = d;
		}, 5000);
		return () => poll.stop();
	});

	function choose(v: string) {
		mode = v as 'beta' | 'own';
		if (mode === 'beta' && value) {
			value = null;
			onclear?.();
		}
	}

	const status = $derived(makemkvKeyStatus(cfg, drives));
</script>

<div class="makemkv-key-field stack">
	<div>
		<div class="field-label makemkv-key-field-title">{field.label}</div>
		<p class="field-help">MakeMKV reads and decrypts DVDs and Blu-rays. Both kinds of key work the same for ripping.</p>
	</div>
	<ChoiceCard
		name="makemkv-key"
		value={mode}
		legend="Which MakeMKV key"
		onchange={choose}
		options={[
			{
				value: 'beta',
				title: 'Use the free beta key',
				badge: 'Default',
				description: 'ARM fetches it for you and renews it automatically each month.'
			},
			{ value: 'own', title: 'I have a purchased key', description: 'Use your own registration key. It never expires.' }
		]}
	/>
	<p class="makemkv-key-field-buy">
		Registration keys are sold at
		<a href="https://www.makemkv.com/buy/" target="_blank" rel="noopener noreferrer">makemkv.com/buy</a>; the beta key
		is free but changes monthly.
	</p>
	{#if mode === 'own'}
		<div class="field">
			<label class="field-label" for="makemkv-key-input">Registration key</label>
			<div class="makemkv-key-field-row">
				<SecretInput
					id="makemkv-key-input"
					class="field-control w-full mono"
					autocomplete="off"
					bind:value
					placeholder="T-..."
					revealLabel="Show registration key"
				/>
			</div>
			{#if value === HIDDEN_SECRET}
				<p class="field-help"><span class="chip chip-sm chip-success">Saved</span> Type a new key to replace it.</p>
			{/if}
		</div>
	{/if}
	{#if status}
		<div class="makemkv-key-field-status">
			<span class="makemkv-key-field-status-label">Key status</span>
			<StatusStrip tone={status.tone} title={status.title} message={status.message} />
		</div>
	{/if}
</div>

<style>
	.makemkv-key-field-buy {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
	.makemkv-key-field {
		gap: 0.75rem;
	}
	.makemkv-key-field-title {
		color: var(--color-text);
		font-weight: 600;
	}
	.makemkv-key-field-row {
		display: flex;
		gap: 0.5rem;
	}
	.makemkv-key-field-status {
		display: grid;
		gap: 0.25rem;
	}
	.makemkv-key-field-status-label {
		font-size: 0.75rem;
		font-weight: 600;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: var(--color-text-faint);
	}
</style>
