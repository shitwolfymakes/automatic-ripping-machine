<script lang="ts">
	import { onMount } from 'svelte';
	import type { ConfigFieldMeta, ConfigView, DriveView } from '$lib/types/api.gen';
	import ChoiceCard from '$lib/components/ChoiceCard.svelte';
	import StatusStrip from '$lib/components/StatusStrip.svelte';
	import Glyph from '$lib/components/Glyph.svelte';
	import { fetchConfigView } from '$lib/api/config';
	import { fetchDrives } from '$lib/api/drives';
	import { usePoll } from '$lib/utils/poll';
	import { driveTitle } from '$lib/utils/drives';

	// MakeMKV key: the free monthly beta key (value null) or a purchased key.
	// ARM can't test a key on demand; a drive's ripper verifies it and reports
	// back, so the status line polls the reported state (setup spec §5.5).
	// Rendered for the `makemkv_key` widget in Settings > Metadata and setup.
	const HIDDEN = '<hidden>';
	let {
		field,
		value = $bindable(),
		onclear
	}: { field: ConfigFieldMeta; value: unknown; onclear?: () => void } = $props();

	let mode = $state<'beta' | 'own'>('beta');
	let reveal = $state(false);
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

	const enrolled = $derived(drives.filter((d) => d.lifecycle === 'enrolled' && d.kind !== 'virtual'));
	const checker = $derived(drives.find((d) => d.id === cfg?.makemkv_key_checked_by_drive_id) ?? null);
	const status = $derived.by(() => {
		if (!cfg) return null;
		if (cfg.makemkv_key_valid === true)
			return {
				tone: 'ok' as const,
				title: checker ? `Valid, checked by ${driveTitle(checker)}` : 'Valid',
				message: null
			};
		if (cfg.makemkv_key_valid === false)
			return { tone: 'danger' as const, title: 'Key not accepted', message: cfg.makemkv_key_state ?? null };
		if (enrolled.length === 0)
			return { tone: 'muted' as const, title: 'Will be checked when you enroll a drive', message: null };
		return { tone: 'busy' as const, title: 'Waiting for a drive to check the key...', message: null };
	});
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
	{#if mode === 'own'}
		<div class="field">
			<label class="field-label" for="makemkv-key-input">Registration key</label>
			<div class="makemkv-key-field-row">
				<input
					id="makemkv-key-input"
					class="field-control w-full mono"
					type={reveal ? 'text' : 'password'}
					autocomplete="off"
					value={value === HIDDEN ? '' : ((value as string | null) ?? '')}
					placeholder={value === HIDDEN ? '******** (set, leave blank to keep)' : 'T-...'}
					oninput={(e) => (value = (e.currentTarget as HTMLInputElement).value)}
				/>
				<button
					type="button"
					class="btn btn-icon"
					aria-label="Show registration key"
					aria-pressed={reveal}
					onclick={() => (reveal = !reveal)}
				>
					<Glyph name={reveal ? 'eye-off' : 'eye'} />
				</button>
			</div>
			{#if value === HIDDEN}
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
