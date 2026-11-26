<script lang="ts">
	// What applying the chosen session would do to this job (its rip preset, its
	// transcode preset and the output paths), or why its output paths cannot be
	// resolved.
	import type { JobNamingPreviewResponse, RipPresetView, SessionView, TranscodePresetView } from '$lib/types/api.gen';

	interface Props {
		/** The chosen session. */
		session: SessionView;
		/** The rip presets the names come from; until they load, the box shows the ids. */
		ripPresets: RipPresetView[];
		/** The transcode presets the names come from; until they load, the box shows 'No transcode'. */
		transcodePresets: TranscodePresetView[];
		/** The output paths applying the session would give this job, or null before they resolve. */
		preview: JobNamingPreviewResponse | null;
		/** True while the output paths are resolving. */
		loading: boolean;
		/** Why the output paths could not be resolved, or null when they could. */
		problem: string | null;
	}

	let { session, ripPresets, transcodePresets, preview, loading, problem }: Props = $props();

	const ripById = $derived(new Map(ripPresets.map((p) => [p.id, p])));
	const tcById = $derived(new Map(transcodePresets.map((p) => [p.id, p])));

	const ripPreset = $derived(ripById.get(session.rip_preset_id) ?? null);
	const transcodePreset = $derived(
		session.transcode_preset_id ? (tcById.get(session.transcode_preset_id) ?? null) : null
	);
</script>

<div data-testid="recipe-preview" class="code-block apply-session-recipe">
	<p class="apply-session-recipe-title">Recipe</p>
	<dl class="apply-session-recipe-list">
		<div class="apply-session-recipe-row">
			<dt class="apply-session-recipe-dt">Rip:</dt>
			<dd data-testid="recipe-rip-preset" class="apply-session-recipe-dd">
				{ripPreset?.name ?? session.rip_preset_id}
			</dd>
		</div>
		<div class="apply-session-recipe-row">
			<dt class="apply-session-recipe-dt">Transcode:</dt>
			<dd data-testid="recipe-transcode-preset" class="apply-session-recipe-dd">
				{transcodePreset?.name ?? 'No transcode'}
			</dd>
		</div>
		<div class="apply-session-recipe-row apply-session-recipe-row-col">
			<dt class="apply-session-recipe-dt">Output:</dt>
			<dd data-testid="recipe-output-path" class="apply-session-recipe-dd apply-session-recipe-output">
				{#if loading}
					<span class="apply-session-recipe-faint">Resolving...</span>
				{:else if preview}
					<ul class="apply-session-recipe-output-list">
						{#each preview.items as item (item.track_id)}
							<li class="apply-session-recipe-output-item" title={item.output_path}>{item.output_path}</li>
						{/each}
					</ul>
					{#if preview.items.length === 0}
						<span class="apply-session-recipe-faint">No tracks to transcode with this session.</span>
					{/if}
				{/if}
			</dd>
		</div>
	</dl>
</div>
{#if problem}
	<p data-testid="recipe-output-problem" class="apply-session-problem">
		<svg class="apply-session-problem-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				stroke-width="2"
				d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"
			/>
		</svg>
		<span>{problem}</span>
	</p>
{/if}

<style>
	/* original recipe box: rounded-lg border border-gray-200 bg-gray-50
	   px-3 py-2 text-sm - code-block's own font-mono/0.72rem sizing is for
	   literal preformatted text; this dl reads as prose, so type is reset
	   back to text-sm/text-secondary while keeping code-block's box (border,
	   radius, tint background). */
	.apply-session-recipe {
		margin-top: 0.75rem;
		font-family: var(--font-sans);
		font-size: 0.875rem;
		line-height: 1.25rem;
		white-space: normal;
	}
	.apply-session-recipe-title {
		font-weight: 500;
		color: var(--color-text-secondary);
	}
	.apply-session-recipe-list {
		margin-top: 0.25rem;
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
		color: var(--color-text-muted);
	}
	.apply-session-recipe-row {
		display: flex;
		gap: 0.25rem;
	}
	.apply-session-recipe-row-col {
		flex-direction: column;
	}
	.apply-session-recipe-dt {
		flex-shrink: 0;
	}
	.apply-session-recipe-dd {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		color: var(--color-text);
	}
	.apply-session-recipe-output {
		font-family: var(--font-mono);
		font-size: 0.75rem;
		white-space: normal;
	}
	.apply-session-recipe-faint {
		color: var(--color-text-faint);
	}
	.apply-session-recipe-output-list {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}
	.apply-session-recipe-output-item {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.apply-session-problem {
		margin-top: 0.5rem;
		display: flex;
		align-items: flex-start;
		gap: 0.375rem;
		font-size: 0.875rem;
		color: var(--color-on-warning-soft);
	}
	.apply-session-problem-icon {
		flex-shrink: 0;
		margin-top: 0.125rem;
		width: 1rem;
		height: 1rem;
	}
</style>
