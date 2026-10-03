<script lang="ts">
	import { onMount } from 'svelte';
	import { transcoderEnabled } from '$lib/stores/config';

	let settings = $state<Record<string, string | null> | null>(null);
	let loading = $state(true);

	const allKeyPaths = [
		{ key: 'RAW_PATH', label: 'Raw Path', desc: 'Where ripped files are stored temporarily' },
		{ key: 'COMPLETED_PATH', label: 'Completed Path', desc: 'Where finished media files are moved' },
		{ key: 'TRANSCODE_PATH', label: 'Transcode Path', desc: 'Working directory for transcoding' },
		{ key: 'RIPMETHOD', label: 'Rip Method', desc: 'How discs are ripped (mkv or backup)' },
		{ key: 'METADATA_PROVIDER', label: 'Metadata Provider', desc: 'Service for looking up movie/show info' },
	];
	const keyPaths = $derived(
		$transcoderEnabled ? allKeyPaths : allKeyPaths.filter(k => k.key !== 'TRANSCODE_PATH')
	);

	onMount(async () => {
		try {
			const resp = await fetch('/api/settings');
			if (resp.ok) {
				const data = await resp.json();
				settings = data.arm_config;
			}
		} catch { /* non-critical */ }
		loading = false;
	});
</script>

<div class="stack stack-lg">
	<div class="settings-review-step-header">
		<h2 class="settings-review-step-title">Review Settings</h2>
		<p class="settings-review-step-subtitle">
			Verify your key configuration values. You can change these later in Settings.
		</p>
	</div>

	{#if loading}
		<div class="settings-review-step-loading">Loading settings...</div>
	{:else if settings}
		<div class="stack stack-sm">
			{#each keyPaths as { key, label, desc }}
				<div class="panel">
					<div class="flex items-center justify-between">
						<div>
							<div class="settings-review-step-label">{label}</div>
							<div class="settings-review-step-desc">{desc}</div>
						</div>
						<code class="mono settings-review-step-value">
							{settings[key] ?? 'not set'}
						</code>
					</div>
				</div>
			{/each}
		</div>

		<div class="settings-review-step-header">
			<a href="/settings" class="btn btn-link">
				Edit all settings -&gt;
			</a>
		</div>
	{:else}
		<div class="alert alert-danger alert-lg">
			Could not load settings.
		</div>
	{/if}
</div>

<style>
	.settings-review-step-header { text-align: center; }
	.settings-review-step-title { font-size: 1.5rem; line-height: 2rem; font-weight: 700; color: var(--color-text); }
	.settings-review-step-subtitle { margin-top: 0.5rem; color: var(--color-text-muted); }
	.settings-review-step-loading { padding: 2rem 0; text-align: center; color: var(--color-text-faint); }
	.settings-review-step-label { font-size: 0.875rem; line-height: 1.25rem; font-weight: 500; color: var(--color-text); }
	.settings-review-step-desc { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-faint); }
	.settings-review-step-value { border-radius: var(--radius-sm); padding: 0.25rem 0.5rem; font-size: 0.75rem; line-height: 1rem; color: var(--color-text-secondary); background: var(--color-primary-tint-2); }
</style>
