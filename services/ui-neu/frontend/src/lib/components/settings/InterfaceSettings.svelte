<script lang="ts">
	import { uiPrefs, setUiPref } from '$lib/stores/uiPrefs';

	const card =
		'rounded-lg border border-primary/20 bg-surface p-6 shadow-xs dark:border-primary/20 dark:bg-surface-dark';
	const segment = (active: boolean) =>
		`rounded-md px-3 py-1.5 text-xs font-medium ${active ? 'bg-primary text-on-primary' : 'bg-primary/10 text-gray-600 hover:bg-primary/15 dark:bg-primary/15 dark:text-gray-300'}`;
</script>

<div class="flex flex-col gap-6">
	<div>
		<h2 class="text-lg font-semibold text-gray-900 dark:text-white">Interface</h2>
		<p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
			How this browser shows ARM. These settings are saved on this device only.
		</p>
	</div>

	<section class="space-y-6">
		<div class={card}>
			<div class="flex items-start justify-between gap-4">
				<div>
					<h3 class="text-base font-semibold text-gray-900 dark:text-white">Resource stats</h3>
					<p class="text-sm text-gray-500 dark:text-gray-400">
						CPU, memory and storage in the sidebar on wide screens and in the bar along the bottom on
						smaller ones. The Stats view in the mobile menu is always available.
					</p>
				</div>
				<div class="flex shrink-0 items-center gap-2">
					<button
						type="button"
						data-testid="pref-show-stats"
						onclick={() => setUiPref('showStats', !$uiPrefs.showStats)}
						class="relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out
							{$uiPrefs.showStats ? 'bg-primary' : 'bg-primary/30 dark:bg-primary/20'}"
						role="switch"
						aria-checked={$uiPrefs.showStats}
						aria-label="Show resource stats"
					>
						<span
							class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out
								{$uiPrefs.showStats ? 'translate-x-5' : 'translate-x-0'}"
						></span>
					</button>
					<span class="text-xs font-medium {$uiPrefs.showStats ? 'text-primary-text dark:text-primary-text-dark' : 'text-gray-400'}">
						{$uiPrefs.showStats ? 'On' : 'Off'}
					</span>
				</div>
			</div>
		</div>

		<div class={card}>
			<div class="flex items-start justify-between gap-4">
				<div>
					<h3 class="text-base font-semibold text-gray-900 dark:text-white">Default dashboard layout</h3>
					<p class="text-sm text-gray-500 dark:text-gray-400">
						How the job list opens. The Cards / Table buttons on the dashboard change it for that visit only.
					</p>
				</div>
				<div class="flex shrink-0 gap-1 rounded-lg bg-primary/5 p-1 dark:bg-primary/10" role="radiogroup" aria-label="Dashboard layout">
					<button
						type="button"
						role="radio"
						aria-checked={$uiPrefs.dashboardView === 'card'}
						data-testid="pref-dashboard-card"
						onclick={() => setUiPref('dashboardView', 'card')}
						class={segment($uiPrefs.dashboardView === 'card')}
					>Cards</button>
					<button
						type="button"
						role="radio"
						aria-checked={$uiPrefs.dashboardView === 'table'}
						data-testid="pref-dashboard-table"
						onclick={() => setUiPref('dashboardView', 'table')}
						class={segment($uiPrefs.dashboardView === 'table')}
					>Table</button>
				</div>
			</div>
		</div>
	</section>
</div>
