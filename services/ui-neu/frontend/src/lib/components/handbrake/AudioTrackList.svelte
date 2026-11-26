<script lang="ts">
	// Row editor for HandBrake's AudioList: one card per output track with
	// reorder and remove controls, and an Add track button below the list.
	// Each track renders the fields `visibleKeys` holds for it, and a track with none stays out.
	// A whole-list issue marks the list itself, which takes focus (tabindex -1) when Save sends it there.
	import type { HandbrakeSchemaSlimView, SettingIssue, SlimKey } from '$lib/types/api.gen';
	import { errorId, invalidAttrs } from '$lib/ui/form-validation';
	import {
		AUDIO_LIST_ID,
		addTrack,
		clearTrackField,
		listIssues,
		moveTrack,
		removeTrack,
		rowIssue,
		rowOptions,
		setTrackField,
		type AudioItem
	} from '$lib/handbrake/audio-tracks';
	import TunableField from './TunableField.svelte';

	interface Props {
		value: AudioItem[];
		// The fields each track shows, by track index.
		visibleKeys: SlimKey[][];
		schema: HandbrakeSchemaSlimView;
		issues: SettingIssue[];
		readonly: boolean;
		onchange: (v: AudioItem[]) => void;
	}

	let { value, visibleKeys, schema, issues, readonly, onchange }: Props = $props();

	const wholeList = $derived(listIssues(issues));
</script>

<div
	class="audio-tracks"
	id={AUDIO_LIST_ID}
	role="group"
	aria-label="Audio tracks"
	tabindex="-1"
	{...invalidAttrs(AUDIO_LIST_ID, wholeList[0]?.message)}
>
	{#if wholeList.length > 0}
		<div id={errorId(AUDIO_LIST_ID)}>
			{#each wholeList as issue (issue.message)}
				<p class="field-error" role="alert">{issue.message}</p>
			{/each}
		</div>
	{/if}
	{#each value as item, i (i)}
		{@const keys = visibleKeys[i] ?? []}
		{#if keys.length > 0}
			<section class="form-card form-card-nested audio-track" aria-label={`Audio track ${i + 1}`}>
				<div class="form-card-head audio-track-head">
					<h4 class="audio-track-title">Track {i + 1}</h4>
					{#if !readonly}
						<div class="audio-track-actions">
							<button
								type="button"
								class="btn btn-sm"
								aria-label={`Move track ${i + 1} up`}
								disabled={i === 0}
								onclick={() => onchange(moveTrack(value, i, -1))}>Move up</button
							>
							<button
								type="button"
								class="btn btn-sm"
								aria-label={`Move track ${i + 1} down`}
								disabled={i === value.length - 1}
								onclick={() => onchange(moveTrack(value, i, 1))}>Move down</button
							>
							<button
								type="button"
								class="btn btn-sm"
								aria-label={`Remove track ${i + 1}`}
								onclick={() => onchange(removeTrack(value, i))}>Remove</button
							>
						</div>
					{/if}
				</div>
				<div class="audio-track-fields">
					{#each keys as key (key.name)}
						<TunableField
							{key}
							value={item[key.name]}
							inherited={key.default}
							stored={item[key.name] !== undefined}
							options={rowOptions(key, item, schema)}
							issue={rowIssue(issues, i, key.name)}
							disabled={readonly}
							idPrefix={`audio-${i}-`}
							onchange={(v) => onchange(setTrackField(value, i, key.name, v))}
							onreset={() => onchange(clearTrackField(value, i, key.name))}
						/>
					{/each}
				</div>
			</section>
		{/if}
	{/each}
	{#if !readonly}
		<button type="button" class="btn-link audio-tracks-add" onclick={() => onchange(addTrack(value, schema))}
			>Add track</button
		>
	{/if}
</div>

<style>
	.audio-tracks {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}
	/* A whole-list issue outlines the list, focused or not. */
	.audio-tracks[aria-invalid='true'] {
		outline: 1px solid var(--color-danger);
		outline-offset: 4px;
		border-radius: var(--radius-sm);
	}
	.audio-track {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}
	.audio-track-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
	}
	.audio-track-title {
		margin: 0;
		font-size: 0.9375rem;
	}
	.audio-track-actions {
		display: flex;
		gap: 0.375rem;
	}
	.audio-track-fields {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(14rem, 100%), 1fr));
		gap: 0.75rem;
	}
	.audio-tracks-add {
		align-self: flex-start;
	}
</style>
