<script lang="ts">
	import { uiPrefs, setUiPref } from '$lib/stores/uiPrefs';
</script>

<div class="flex flex-col gap-6">
	<div>
		<h2 class="interface-settings-title">Interface</h2>
		<p class="interface-settings-description mt-1">
			How this browser shows ARM. These settings are saved on this device only.
		</p>
	</div>

	<section class="stack stack-lg">
		<div class="panel interface-settings-panel">
			<div class="flex items-start justify-between gap-4">
				<div>
					<h3 class="interface-settings-card-title">Resource stats</h3>
					<p class="interface-settings-description">
						CPU, memory and storage in the sidebar on wide screens and in the bar along the bottom on
						smaller ones. The Stats view in the mobile menu is always available.
					</p>
				</div>
				<div class="flex shrink-0 items-center gap-2">
					<button
						type="button"
						data-testid="pref-show-stats"
						onclick={() => setUiPref('showStats', !$uiPrefs.showStats)}
						role="switch"
						aria-checked={$uiPrefs.showStats}
						aria-label="Show resource stats"
						class="toggle toggle-lg"
					>
						<span class="toggle-thumb"></span>
					</button>
					<span class="interface-settings-toggle-label" data-on={$uiPrefs.showStats}>
						{$uiPrefs.showStats ? 'On' : 'Off'}
					</span>
				</div>
			</div>
		</div>

		<div class="panel interface-settings-panel">
			<div class="flex items-start justify-between gap-4">
				<div>
					<h3 class="interface-settings-card-title">Default dashboard layout</h3>
					<p class="interface-settings-description">
						How the job list opens. The Cards / Table buttons on the dashboard change it for that visit only.
					</p>
				</div>
				<div class="interface-settings-segment" role="radiogroup" aria-label="Dashboard layout">
					<button
						type="button"
						role="radio"
						aria-checked={$uiPrefs.dashboardView === 'card'}
						data-testid="pref-dashboard-card"
						onclick={() => setUiPref('dashboardView', 'card')}
						class="interface-settings-segment-btn"
					>Cards</button>
					<button
						type="button"
						role="radio"
						aria-checked={$uiPrefs.dashboardView === 'table'}
						data-testid="pref-dashboard-table"
						onclick={() => setUiPref('dashboardView', 'table')}
						class="interface-settings-segment-btn"
					>Table</button>
				</div>
			</div>
		</div>
	</section>
</div>

<style>
	.interface-settings-title { font-size: 1.125rem; line-height: 1.75rem; font-weight: 600; color: var(--color-text); }
	/* the original cards were p-6 (1.5rem), not .panel's own p-4 (1rem) default. */
	.interface-settings-panel { padding: 1.5rem; }
	/* the original description paragraphs were text-sm (0.875rem/1.25rem),
	   not panel-hint's 0.75rem - panel-hint is sized for a note under a
	   form control, a visibly smaller role. */
	.interface-settings-description { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	.interface-settings-card-title { font-size: 1rem; line-height: 1.5rem; font-weight: 600; color: var(--color-text); }
	.interface-settings-toggle-label { font-size: 0.75rem; font-weight: 500; color: var(--color-text-faint); }
	.interface-settings-toggle-label[data-on="true"] { color: var(--color-primary-text); }
	/* a segmented radiogroup, not a tab strip: no block covers this shape
	   (tabs-pills' metrics - 0.875rem tabs-tab text, unselected = transparent -
	   don't match this control's original text-xs px-3/py-1.5 pills on a
	   tinted 0.10-alpha unselected background). */
	.interface-settings-segment { display: flex; flex-shrink: 0; gap: 0.25rem; border-radius: var(--radius-lg); background: var(--color-primary-tint-1); padding: 0.25rem; }
	.interface-settings-segment-btn { border-radius: var(--radius-md); padding: 0.375rem 0.75rem; font-size: 0.75rem; line-height: 1rem; font-weight: 500; color: var(--color-text-secondary); background: var(--color-primary-tint-2); cursor: pointer; transition: background-color var(--motion-fast) var(--ease), color var(--motion-fast) var(--ease); }
	.interface-settings-segment-btn:hover { background: var(--color-primary-tint-3); }
	.interface-settings-segment-btn[aria-checked="true"] { background: var(--color-primary); color: var(--color-on-primary); }
</style>
