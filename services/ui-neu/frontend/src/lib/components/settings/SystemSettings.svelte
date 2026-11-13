<script lang="ts">
	import type { SettingsData } from '$lib/api/settings';
	import type { SettingsGroup } from '$lib/types/api.gen';
	import type { SetupRestart } from '$lib/stores/setup-restart.svelte';
	import ConfigSchemaField from '$lib/components/settings/ConfigSchemaField.svelte';
	import SystemHealth from '$lib/components/settings/SystemHealth.svelte';
	import DiagnosticsSection from '$lib/components/DiagnosticsSection.svelte';

	interface Props {
		settings: SettingsData;
		group: SettingsGroup | undefined;
		setup: SetupRestart;
	}

	let { settings, group, setup }: Props = $props();
</script>

<div class="stack stack-lg" data-page-section>
	<div class="stack stack-lg">
		<h2 class="settings-page-section-title" data-page-section-title>System</h2>

		<!-- Health check (API keys + path permissions) -->
		<!-- First-run walkthrough re-entry (setup spec §5.11) -->
		<section class="panel settings-page-setup-again" data-testid="run-setup-again">
			<div>
				<h3 class="settings-page-section-title">Setup walkthrough</h3>
				<p class="settings-page-setup-again-help">
					Walk through drives, keys and defaults again. Your current values are kept.
				</p>
			</div>
			<button type="button" class="btn" onclick={setup.run} disabled={setup.running}>
				{setup.running ? 'Opening...' : 'Run setup again'}
			</button>
		</section>

		<SystemHealth grouped />

		<!-- Read-only infra configuration (schema-driven) -->
		{#if group}
			<section class="stack">
				<h3 class="settings-page-section-title">Configuration (read-only)</h3>
				<div class="panel stack">
					{#each group.fields as f (f.key)}
						<ConfigSchemaField
							field={f}
							value={(settings.config as Record<string, unknown>)?.[f.key] ?? settings.infra?.[f.key]}
						/>
					{/each}
				</div>
			</section>
		{/if}
	</div>

	<!-- Diagnostics (moved here from the standalone Diagnostics tab) -->
	<section class="mt-6">
		<DiagnosticsSection />
	</section>
</div>

<style>
	.settings-page-section-title {
		font-size: 1.125rem;
		line-height: 1.75rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.settings-page-setup-again {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 1.25rem;
	}
	.settings-page-setup-again-help {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
</style>
