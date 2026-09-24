<script lang="ts">
	import { onMount } from 'svelte';
	import { isAdmin } from '$lib/stores/auth';
	import { fetchSessionRoutes, upsertSessionRoute, deleteSessionRoute } from '$lib/api/sessionRoutes';
	import { fetchSessions } from '$lib/api/sessions';
	import type { DiscType, MediaType, SessionRouteView, SessionView } from '$lib/types/api.gen';

	let routes = $state<SessionRouteView[]>([]);
	let sessions = $state<SessionView[]>([]);
	let loading = $state(true);
	let feedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);
	// Row keys currently in flight (upsert or delete), keyed by "media_type/disc_type".
	let pending = $state<Set<string>>(new Set());

	const MEDIA_TYPES: Array<{ key: MediaType; label: string }> = [
		{ key: 'movie', label: 'Movie' },
		{ key: 'tv', label: 'TV' },
		{ key: 'music', label: 'Music' },
		{ key: 'data', label: 'Data' }
	];

	// disc_type null is the wildcard row for that media type.
	const DISC_SCOPES: Array<{ key: DiscType | null; label: string }> = [
		{ key: null, label: 'Any disc' },
		{ key: 'dvd', label: 'DVD' },
		{ key: 'bluray', label: 'Blu-ray' },
		{ key: 'cd', label: 'CD' }
	];

	function rowKey(mediaType: MediaType, discType: DiscType | null): string {
		return `${mediaType}/${discType ?? 'any'}`;
	}

	function routeFor(mediaType: MediaType, discType: DiscType | null): SessionRouteView | undefined {
		return routes.find((r) => r.media_type === mediaType && r.disc_type === discType);
	}

	function sessionsFor(mediaType: MediaType): SessionView[] {
		return sessions.filter((s) => s.media_type === mediaType);
	}

	async function load() {
		loading = true;
		try {
			[routes, sessions] = await Promise.all([fetchSessionRoutes(), fetchSessions()]);
		} catch (e) {
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Failed to load session routes' };
		} finally {
			loading = false;
		}
	}

	onMount(load);

	function showFeedback(type: 'success' | 'error', message: string) {
		feedback = { type, message };
		setTimeout(() => {
			feedback = null;
		}, 4000);
	}

	async function handleChange(mediaType: MediaType, discType: DiscType | null, sessionId: string) {
		if (!sessionId) {
			// M1: choosing "- none -" must clear a stored route, the same as
			// clicking Clear — otherwise the route stays stored while the
			// select shows none, and the two drift out of sync.
			const existing = routeFor(mediaType, discType);
			if (existing) {
				await handleClear(existing);
			}
			return;
		}
		const key = rowKey(mediaType, discType);
		pending = new Set(pending).add(key);
		try {
			const saved = await upsertSessionRoute({ media_type: mediaType, disc_type: discType, session_id: sessionId });
			const others = routes.filter((r) => !(r.media_type === mediaType && r.disc_type === discType));
			routes = [...others, saved];
		} catch (e) {
			showFeedback('error', e instanceof Error ? e.message : 'Failed to save route');
			await load();
		} finally {
			const next = new Set(pending);
			next.delete(key);
			pending = next;
		}
	}

	async function handleClear(route: SessionRouteView) {
		const key = rowKey(route.media_type, route.disc_type);
		pending = new Set(pending).add(key);
		try {
			await deleteSessionRoute(route.id);
			routes = routes.filter((r) => r.id !== route.id);
		} catch (e) {
			showFeedback('error', e instanceof Error ? e.message : 'Failed to clear route');
			await load();
		} finally {
			const next = new Set(pending);
			next.delete(key);
			pending = next;
		}
	}
</script>

<div class="rounded-lg border border-primary/20 bg-surface p-4 shadow-xs dark:bg-surface-dark">
	<h3 class="mb-1 text-base font-semibold text-gray-900 dark:text-white">Session Routing</h3>
	<p class="mb-4 text-sm text-gray-500 dark:text-gray-400">
		A route applies the chosen session when a disc's identified media type matches. The drive's default session
		overrides every route here, and a disc-type-specific route (DVD, Blu-ray, CD) beats the Any-disc wildcard
		for the same media type.
	</p>

	{#if feedback}
		<p class="mb-3 rounded px-3 py-2 text-sm {feedback.type === 'success' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'}">
			{feedback.message}
		</p>
	{/if}

	{#if loading}
		<p class="py-4 text-center text-sm text-gray-400">Loading...</p>
	{:else}
		<div class="space-y-4">
			{#each MEDIA_TYPES as mt (mt.key)}
				{@const options = sessionsFor(mt.key)}
				<div>
					<h4 class="mb-1.5 text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">{mt.label}</h4>
					<div class="space-y-1.5">
						{#each DISC_SCOPES as scope (scope.key ?? 'any')}
							{@const route = routeFor(mt.key, scope.key)}
							{@const key = rowKey(mt.key, scope.key)}
							{@const rowBusy = pending.has(key)}
							<div class="flex flex-wrap items-center gap-2 rounded-lg border border-primary/10 px-3 py-2 dark:border-primary/10">
								<span class="w-20 shrink-0 text-xs font-medium text-gray-600 dark:text-gray-300">{scope.label}</span>
								<select
									id="route-{key}"
									aria-label="{mt.label} / {scope.label} session"
									value={route?.session_id ?? ''}
									disabled={!$isAdmin || rowBusy || options.length === 0}
									onchange={(e) => handleChange(mt.key, scope.key, (e.target as HTMLSelectElement).value)}
									class="min-w-0 flex-1 rounded-md border border-primary/15 bg-primary/5 px-2 py-1.5 text-xs text-gray-900 disabled:opacity-50 dark:border-primary/20 dark:bg-primary/10 dark:text-white"
								>
									<option value="">- none -</option>
									{#each options as s (s.id)}
										<option value={s.id}>{s.name}{s.is_builtin ? ' (built-in)' : ''}</option>
									{/each}
								</select>
								{#if $isAdmin && route}
									<button
										type="button"
										onclick={() => handleClear(route)}
										disabled={rowBusy}
										aria-label="Clear {mt.label} / {scope.label} route"
										class="shrink-0 rounded-md border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
									>
										Clear
									</button>
								{/if}
							</div>
						{/each}
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>
