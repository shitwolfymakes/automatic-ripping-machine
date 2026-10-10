<script lang="ts">
	import { onMount } from 'svelte';
	import { isAdmin } from '$lib/stores/auth';
	import { reveal } from '$lib/transitions';
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

	// A route is grid-covered when both its media_type and disc_type appear
	// among the fixed 4x4 grid's rows/columns. Anything else (media_type=iso,
	// or disc_type=data/unknown) is creatable via the API and wins resolution
	// (resolve_routed_session_id), but has no cell in the grid to render in;
	// it must still be visible and clearable here, or it's silently stuck.
	const GRID_MEDIA_TYPES = new Set(MEDIA_TYPES.map((mt) => mt.key));
	const GRID_DISC_TYPES = new Set(DISC_SCOPES.map((s) => s.key));

	function isGridCovered(route: SessionRouteView): boolean {
		return GRID_MEDIA_TYPES.has(route.media_type) && GRID_DISC_TYPES.has(route.disc_type);
	}

	function otherRoutes(): SessionRouteView[] {
		return routes.filter((r) => !isGridCovered(r));
	}

	function sessionNameFor(sessionId: string): string {
		return sessions.find((s) => s.id === sessionId)?.name ?? sessionId;
	}

	function discLabel(discType: DiscType | null): string {
		return discType ?? 'Any disc';
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

<div class="panel">
	<h3 class="session-routes-card-title">Session Routing</h3>
	<p class="session-routes-card-intro">
		A route applies the chosen session when a disc's identified media type matches. The drive's default session
		wins when it is compatible with the disc's media type; otherwise these routes apply instead. A disc-type-specific
		route (DVD, Blu-ray, CD) beats the Any-disc wildcard for the same media type.
	</p>

	{#if feedback}
		<p in:reveal class="alert {feedback.type === 'success' ? 'alert-success' : 'alert-danger'} mb-3">
			{feedback.message}
		</p>
	{/if}

	{#if loading}
		<p class="session-routes-card-loading">Loading...</p>
	{:else}
		<div class="stack">
			{#each MEDIA_TYPES as mt (mt.key)}
				{@const options = sessionsFor(mt.key)}
				<div>
					<h4 class="eyebrow session-routes-card-group-title">{mt.label}</h4>
					<div class="stack stack-sm">
						{#each DISC_SCOPES as scope (scope.key ?? 'any')}
							{@const route = routeFor(mt.key, scope.key)}
							{@const key = rowKey(mt.key, scope.key)}
							{@const rowBusy = pending.has(key)}
							<div class="panel-section session-routes-card-row">
								<span class="session-routes-card-scope-label">{scope.label}</span>
								<select
									id="route-{key}"
									aria-label="{mt.label} / {scope.label} session"
									value={route?.session_id ?? ''}
									disabled={!$isAdmin || rowBusy || options.length === 0}
									onchange={(e) => handleChange(mt.key, scope.key, (e.target as HTMLSelectElement).value)}
									class="field-control session-routes-card-select"
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
										class="btn btn-sm"
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

		{#if otherRoutes().length > 0}
			<div class="session-routes-card-other">
				<h4 class="eyebrow session-routes-card-group-title">Other routes</h4>
				<div class="stack stack-sm">
					{#each otherRoutes() as route (route.id)}
						{@const key = rowKey(route.media_type, route.disc_type)}
						{@const rowBusy = pending.has(key)}
						<div class="panel-section session-routes-card-row">
							<span class="session-routes-card-other-label">
								<span class="session-routes-card-other-key">{route.media_type} / {discLabel(route.disc_type)}</span>
								<span class="session-routes-card-other-arrow">&rarr;</span>
								{sessionNameFor(route.session_id)}
							</span>
							{#if $isAdmin}
								<button
									type="button"
									onclick={() => handleClear(route)}
									disabled={rowBusy}
									aria-label="Clear {route.media_type} / {discLabel(route.disc_type)} route ({sessionNameFor(route.session_id)})"
									class="btn btn-sm"
								>
									Clear
								</button>
							{/if}
						</div>
					{/each}
				</div>
			</div>
		{/if}
	{/if}
</div>

<style>
	/* the original title was text-base font-semibold text-gray-900, mb-1 -
	   a plain heading, not panel-title's uppercase eyebrow look (matches
	   UsersCard's own title treatment). */
	.session-routes-card-title { margin-bottom: 0.25rem; font-size: 1rem; line-height: 1.5rem; font-weight: 600; color: var(--color-text); }
	.session-routes-card-intro { margin-bottom: 1rem; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	.session-routes-card-loading { padding: 1rem 0; text-align: center; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-faint); }
	/* the original group heading was text-xs font-bold uppercase
	   tracking-wider (12px/700/0.05em) - close to but not exactly .eyebrow's
	   own weight/tracking, so those two are overridden here. */
	.session-routes-card-group-title { margin-bottom: 0.375rem; font-weight: 700; letter-spacing: 0.05em; }
	/* the original row was a bordered, unfilled box (rounded-lg
	   border-primary/10 px-3 py-2) - panel-section's shape, but without its
	   tint-1 fill and at a tighter 10% border + own padding. */
	.session-routes-card-row { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; border-color: var(--color-primary-tint-2); background: none; padding: 0.5rem 0.75rem; }
	.session-routes-card-scope-label { width: 5rem; flex-shrink: 0; font-size: 0.75rem; line-height: 1rem; font-weight: 500; color: var(--color-text-secondary); }
	.session-routes-card-select { min-width: 0; flex: 1 1 0%; width: auto; min-height: 0; padding: 0.375rem 0.5rem; font-size: 0.75rem; }
	/* other-routes: API-created keys outside the grid; same row shape,
	   muted single-line label. */
	.session-routes-card-other { margin-top: 1rem; }
	.session-routes-card-other-label { min-width: 0; flex: 1 1 0%; font-size: 0.75rem; line-height: 1rem; color: var(--color-text-secondary); }
	.session-routes-card-other-key { font-weight: 500; }
	.session-routes-card-other-arrow { color: var(--color-text-faint); }
</style>
