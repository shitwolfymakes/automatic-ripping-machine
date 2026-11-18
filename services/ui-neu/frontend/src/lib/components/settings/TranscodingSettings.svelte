<script lang="ts">
	import SchemaConfigForm from '$lib/components/settings/SchemaConfigForm.svelte';
	import GpusCard from '$lib/components/shared/GpusCard.svelte';
	import Toggle from '$lib/components/shared/Toggle.svelte';
	import { transcoderEnabled } from '$lib/stores/config';
	import type { SettingsGroup } from '$lib/types/api.gen';

	interface Props {
		group: SettingsGroup | undefined;
		config: Record<string, unknown>;
		onsaved: (payload: Record<string, unknown>) => void;
	}

	let { group, config, onsaved }: Props = $props();
</script>

<div data-page-section>
	{#if $transcoderEnabled && group}
		<SchemaConfigForm {group} {config} {onsaved}>
			{#snippet beforeSections()}
				<GpusCard />
			{/snippet}
		</SchemaConfigForm>
	{:else}
		<div class="stack" id="setting-transcode_enabled" data-testid="setting-transcode_enabled">
			<label class="field field-row settings-page-notif-toggle-row">
				<!-- Always rendered off: on a ripper-only box the backend column
				 still defaults to true, but it has no effect without capability. -->
				<Toggle checked={false} label="Enable transcoding" disabled />
				<span class="field-label">Enable transcoding</span>
			</label>
			<p class="field-help">This deployment is ripper-only; transcoding cannot be enabled here.</p>
		</div>
	{/if}
</div>

<style>
	/* the original toggle row was gap-3 (0.75rem), not field-row's 0.5rem. */
	.settings-page-notif-toggle-row {
		gap: 0.75rem;
	}
</style>
