<script lang="ts">
	import SchemaConfigForm from '$lib/components/settings/SchemaConfigForm.svelte';
	import GpusCard from '$lib/components/shared/GpusCard.svelte';
	import Toggle from '$lib/components/shared/Toggle.svelte';
	import FieldLabel from '$lib/components/shared/FieldLabel.svelte';
	import TranscodeCapabilityStatus from './TranscodeCapabilityStatus.svelte';
	import { transcoderEnabled } from '$lib/stores/config';
	import type { SettingsGroup } from '$lib/types/api.gen';

	interface Props {
		group: SettingsGroup | undefined;
		config: Record<string, unknown>;
		onsaved: (payload: Record<string, unknown>) => void;
	}

	let { group, config, onsaved }: Props = $props();

	// Known once the GPU card has loaded its list: whether any GPU is enabled.
	let gpuEnabled = $state<boolean | undefined>(undefined);
</script>

<div data-page-section>
	{#if $transcoderEnabled && group}
		<SchemaConfigForm {group} {config} {onsaved}>
			{#snippet beforeSections()}
				<TranscodeCapabilityStatus capable {gpuEnabled} />
			{/snippet}
			{#snippet beforeSave()}
				<GpusCard ongpus={(gpus) => (gpuEnabled = gpus.some((g) => g.enabled))} />
			{/snippet}
		</SchemaConfigForm>
	{:else}
		<div class="stack" id="setting-transcode_enabled" data-testid="setting-transcode_enabled">
			<TranscodeCapabilityStatus capable={$transcoderEnabled} />
			<div class="field field-row settings-page-notif-toggle-row">
				<!-- Always rendered off: on a ripper-only box the backend column
				 still defaults to true, but it has no effect without capability. -->
				<Toggle id="transcode-enabled" checked={false} label="Enable transcoding" disabled />
				<FieldLabel for="transcode-enabled" label="Enable transcoding" docsId="config.transcode_enabled" />
			</div>
			<p class="field-help">This deployment is ripper-only; transcoding cannot be enabled here.</p>
		</div>
	{/if}
</div>

<style>
	/* the toggle row gap is 0.75rem, not field-row's 0.5rem. */
	.settings-page-notif-toggle-row {
		gap: 0.75rem;
	}
</style>
