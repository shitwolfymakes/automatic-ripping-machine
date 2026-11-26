<script lang="ts">
	import { theme, toggleTheme } from '$lib/stores/theme';
	import { colorScheme, schemeLocksMode, allSchemes } from '$lib/stores/color-scheme';
	import type { UserThemes } from '$lib/stores/user-themes.svelte';
	import Glyph from '$lib/components/shared/Glyph.svelte';

	interface Props {
		themes: UserThemes;
	}

	let { themes }: Props = $props();
</script>

<div class="stack stack-lg" data-page-section>
	<h2 class="settings-page-section-title mb-4" data-page-section-title>Themes</h2>
	<section class="stack stack-lg">
		<!-- Feedback toast -->
		{#if themes.feedback}
			<div class="alert {themes.feedback.type === 'success' ? 'alert-success' : 'alert-danger'}">
				{themes.feedback.message}
			</div>
		{/if}

		<!-- Built-in Themes -->
		<div class="panel settings-page-panel-wide">
			<h3 class="settings-page-panel-title">Color Scheme</h3>
			<p class="settings-page-description settings-page-panel-hint">
				Choose an accent color for buttons, links, and highlights throughout the UI.
			</p>
			<div class="flex flex-wrap gap-3">
				{#each $allSchemes.filter((s) => s.builtin !== false) as scheme (scheme.id)}
					<button
						type="button"
						onclick={() => ($colorScheme = scheme.id)}
						class="scheme-swatch-btn"
						data-selected={$colorScheme === scheme.id}
					>
						<span class="scheme-swatch" style:--swatch={scheme.swatch}></span>
						<span class="scheme-swatch-label">{scheme.label}</span>
						{#if scheme.description}
							<span class="scheme-swatch-tooltip">{scheme.description}</span>
						{/if}
					</button>
				{/each}
			</div>
		</div>

		<!-- User Themes -->
		{#if $allSchemes.filter((s) => s.builtin === false).length > 0}
			<div class="panel settings-page-panel-wide">
				<h3 class="settings-page-panel-title">User Themes</h3>
				<p class="settings-page-description settings-page-panel-hint">
					Custom themes loaded from your themes directory.
				</p>
				<div class="flex flex-wrap gap-3">
					{#each $allSchemes.filter((s) => s.builtin === false) as scheme (scheme.id)}
						<div class="relative">
							<button
								type="button"
								onclick={() => ($colorScheme = scheme.id)}
								class="scheme-swatch-btn"
								data-selected={$colorScheme === scheme.id}
							>
								<span class="scheme-swatch" style:--swatch={scheme.swatch}></span>
								<span class="scheme-swatch-label">{scheme.label}</span>
								{#if scheme.author}
									<span class="scheme-swatch-author">by {scheme.author}</span>
								{/if}
							</button>
							<div class="absolute -right-1 -top-1 flex gap-0.5">
								<button
									type="button"
									onclick={() => themes.deleteTheme(scheme.id, scheme.label)}
									class="btn btn-icon scheme-swatch-delete"
									title="Delete"
								>
									<Glyph name="x" class="h-3 w-3" />
								</button>
							</div>
						</div>
					{/each}
				</div>
				{#if themes.feedback}
					<p class="mt-3 settings-page-feedback" data-error={themes.feedback.type !== 'success'}>
						{themes.feedback.message}
					</p>
				{/if}
			</div>
		{/if}

		<!-- Dark Mode -->
		<div class="panel settings-page-panel-wide">
			<div class="flex items-center justify-between">
				<div>
					<h3 class="settings-page-panel-title settings-page-panel-title-flush">Dark Mode</h3>
					{#if $schemeLocksMode}
						<p class="settings-page-description">Locked by theme</p>
					{:else}
						<p class="settings-page-description">Toggle between light and dark mode.</p>
					{/if}
				</div>
				{#if !$schemeLocksMode}
					<div class="flex items-center gap-2">
						<button
							type="button"
							onclick={toggleTheme}
							role="switch"
							aria-checked={$theme === 'dark'}
							aria-label="Dark mode"
							class="toggle toggle-lg"
						>
							<span class="toggle-thumb"></span>
						</button>
						<span class="settings-page-toggle-label" data-on={$theme === 'dark'}>
							{$theme === 'dark' ? 'On' : 'Off'}
						</span>
					</div>
				{/if}
			</div>
		</div>
	</section>
</div>

<style>
	.settings-page-section-title {
		font-size: 1.125rem;
		line-height: 1.75rem;
		font-weight: 600;
		color: var(--color-text);
	}
	/* the section-card h3s in Themes were text-base font-semibold (1rem/
	   1.5rem), distinct from .panel-title's uppercase eyebrow look. */
	.settings-page-panel-title {
		margin-bottom: 0.25rem;
		font-size: 1rem;
		line-height: 1.5rem;
		font-weight: 600;
		color: var(--color-text);
	}
	/* Dark Mode's and Image Cache's h3 had no mb-1 in the original (only
	   Color Scheme's and User Themes' did). */
	.settings-page-panel-title-flush {
		margin-bottom: 0;
	}
	/* most "muted description under a heading" paragraphs on this page were
	   text-sm (0.875rem/1.25rem), not panel-hint's 0.75rem - panel-hint is
	   sized for a note under a form control, a visibly smaller role. */
	.settings-page-description {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.settings-page-panel-hint {
		margin-bottom: 1rem;
		margin-top: 0;
	}
	.settings-page-toggle-label {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--color-text-faint);
	}
	.settings-page-toggle-label[data-on='true'] {
		color: var(--color-primary-text);
	}
	.settings-page-feedback {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
	.settings-page-feedback[data-error='true'] {
		color: var(--color-danger);
	}
	/* the Themes tab's four cards were p-6 (1.5rem) in the original, not
	   .panel's own p-4 (1rem) default. */
	.settings-page-panel-wide {
		padding: 1.5rem;
	}

	/* Color scheme swatch buttons (Themes tab): a bordered pill holding a
	   round color sample, its label, and (built-in schemes) a hover tooltip
	   or (user themes) a delete button. No block covers this shape. */
	.scheme-swatch-btn {
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.375rem;
		border: 2px solid var(--color-border);
		border-radius: var(--radius-lg);
		padding: 0.75rem 1rem;
		background: none;
		cursor: pointer;
		transition:
			border-color var(--motion-fast) var(--ease),
			background-color var(--motion-fast) var(--ease);
	}
	.scheme-swatch-btn:hover {
		border-color: var(--color-border-strong);
	}
	.scheme-swatch-btn[data-selected='true'] {
		border-color: var(--color-primary);
		background: var(--color-primary-tint-3);
	}
	.scheme-swatch {
		display: block;
		width: 2rem;
		height: 2rem;
		border-radius: 9999px;
		background: var(--swatch);
	}
	.scheme-swatch-label {
		font-size: 0.75rem;
		line-height: 1rem;
		font-weight: 500;
		color: var(--color-text-secondary);
	}
	.scheme-swatch-author {
		font-size: 0.625rem;
		color: var(--color-text-faint);
	}
	.scheme-swatch-tooltip {
		position: absolute;
		top: -2rem;
		left: 50%;
		transform: translateX(-50%);
		white-space: nowrap;
		border-radius: var(--radius-sm);
		background: var(--color-surface-raised);
		padding: 0.25rem 0.5rem;
		font-size: 0.625rem;
		color: var(--color-text);
		opacity: 0;
		pointer-events: none;
		transition: opacity var(--motion-fast) var(--ease);
		box-shadow: var(--shadow-1);
	}
	.scheme-swatch-btn:hover .scheme-swatch-tooltip {
		opacity: 1;
	}
	.scheme-swatch-delete {
		position: absolute;
	}
</style>
