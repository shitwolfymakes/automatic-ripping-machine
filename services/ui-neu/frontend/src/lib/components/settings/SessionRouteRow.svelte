<script lang="ts">
	// One cell of Settings > Session Routing's grid, choosing the session a
	// media and disc type routes to, or clearing it.
	import { isAdmin } from '$lib/stores/auth';
	import type { SessionRouteView, SessionView } from '$lib/types/api.gen';

	let {
		rowId,
		mediaLabel,
		scopeLabel,
		route,
		options,
		busy,
		onchange,
		onclear
	}: {
		rowId: string;
		mediaLabel: string;
		scopeLabel: string;
		route: SessionRouteView | undefined;
		options: readonly SessionView[];
		busy: boolean;
		onchange: (sessionId: string) => void;
		onclear: (route: SessionRouteView) => void;
	} = $props();
</script>

<div class="panel-section session-route-row">
	<span class="session-route-row-scope-label">{scopeLabel}</span>
	<select
		id="route-{rowId}"
		aria-label="{mediaLabel} / {scopeLabel} session"
		value={route?.session_id ?? ''}
		disabled={!$isAdmin || busy || options.length === 0}
		onchange={(e) => onchange((e.target as HTMLSelectElement).value)}
		class="field-control session-route-row-select"
	>
		<option value="">- none -</option>
		{#each options as s (s.id)}
			<option value={s.id}>{s.name}{s.is_builtin ? ' (built-in)' : ''}</option>
		{/each}
	</select>
	{#if $isAdmin && route}
		<button
			type="button"
			onclick={() => onclear(route)}
			disabled={busy}
			aria-label="Clear {mediaLabel} / {scopeLabel} route"
			class="btn btn-sm"
		>
			Clear
		</button>
	{/if}
</div>

<style>
	/* the original row was a bordered, unfilled box (rounded-lg
	   border-primary/10 px-3 py-2) - panel-section's shape, but without its
	   tint-1 fill and at a tighter 10% border + own padding. */
	.session-route-row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		border-color: var(--color-primary-tint-2);
		background: none;
		padding: 0.5rem 0.75rem;
	}
	.session-route-row-scope-label {
		width: 5rem;
		flex-shrink: 0;
		font-size: 0.75rem;
		line-height: 1rem;
		font-weight: 500;
		color: var(--color-text-secondary);
	}
	.session-route-row-select {
		min-width: 0;
		flex: 1 1 0%;
		width: auto;
		min-height: 0;
		padding: 0.375rem 0.5rem;
		font-size: 0.75rem;
	}
</style>
