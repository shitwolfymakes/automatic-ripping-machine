<script lang="ts">
	import { errorMessage } from '$lib/utils/errors';
	// The Routing view: a media-type by disc-type matrix, each cell the session
	// a disc of that kind routes to. Loads and saves its own routes.
	import { onMount } from 'svelte';
	import { isAdmin } from '$lib/stores/auth';
	import { fetchSessionRoutes, upsertSessionRoute, deleteSessionRoute } from '$lib/api/session-routes';
	import { fetchSessions } from '$lib/api/sessions';
	import type { DiscType, MediaType, SessionRouteView, SessionView } from '$lib/types/api.gen';
	import {
		DISC_SCOPES,
		MEDIA_TYPES,
		otherRouteView,
		otherRoutes,
		routeCellView,
		routeFor,
		rowKey,
		sessionOptionLabel,
		sessionsFor,
		withRoute
	} from '$lib/sessions/routes';
	import { PendingKeys } from '$lib/stores/pending-keys.svelte';
	import { TimedFeedback } from '$lib/stores/timed-feedback.svelte';
	import FeedbackAlert from '$lib/components/shared/FeedbackAlert.svelte';
	import MediaPill from '../shared/MediaPill.svelte';

	let routes = $state<SessionRouteView[]>([]);
	let sessions = $state<SessionView[]>([]);
	let loading = $state(true);
	const feedback = new TimedFeedback();
	// Cell keys in flight (upsert or delete), keyed by "media_type/disc_type".
	const pending = new PendingKeys();

	const others = $derived(otherRoutes(routes));

	async function load() {
		loading = true;
		try {
			[routes, sessions] = await Promise.all([fetchSessionRoutes(), fetchSessions()]);
		} catch (e) {
			feedback.hold('error', errorMessage(e, 'Failed to load session routes'));
		} finally {
			loading = false;
		}
	}

	onMount(load);

	// A failed change reloads, which rebuilds every cell from the stored routes
	// and so puts the select the user changed back where it was.
	async function handleChange(mediaType: MediaType, discType: DiscType | null, sessionId: string) {
		if (!sessionId) {
			// "None" clears a stored route; with no route there is nothing to do.
			const existing = routeFor(routes, mediaType, discType);
			if (existing) await handleClear(existing);
			return;
		}
		await pending.run(rowKey(mediaType, discType), async () => {
			try {
				const saved = await upsertSessionRoute({ media_type: mediaType, disc_type: discType, session_id: sessionId });
				routes = withRoute(routes, mediaType, discType, saved);
			} catch (e) {
				feedback.show('error', errorMessage(e, 'Failed to save route'));
				await load();
			}
		});
	}

	async function handleClear(route: SessionRouteView) {
		await pending.run(rowKey(route.media_type, route.disc_type), async () => {
			try {
				await deleteSessionRoute(route.id);
				routes = routes.filter((r) => r.id !== route.id);
			} catch (e) {
				feedback.show('error', errorMessage(e, 'Failed to clear route'));
				await load();
			}
		});
	}
</script>

<section class="stack stack-sm">
	<div>
		<h3 class="routing-title">Routing</h3>
		<p class="routing-lede">
			A route applies the chosen session when a disc's identified media type matches. A drive's default session wins
			when it fits the disc's media type. A disc-type route (DVD, Blu-ray, CD) beats Any disc.
		</p>
	</div>

	<FeedbackAlert feedback={feedback.current} />

	{#if loading}
		<p class="routing-loading">Loading...</p>
	{:else}
		<div class="routing-box">
			<table class="routing-table">
				<thead>
					<tr>
						<th scope="col">Media</th>
						{#each DISC_SCOPES as scope (scope.key ?? 'any')}
							<th scope="col">{scope.label}</th>
						{/each}
					</tr>
				</thead>
				<tbody>
					{#each MEDIA_TYPES as mt (mt.key)}
						<tr>
							<th scope="row"><MediaPill mediaType={mt.key} /></th>
							{#each DISC_SCOPES as scope (scope.key ?? 'any')}
								{@const route = routeFor(routes, mt.key, scope.key)}
								{@const options = sessionsFor(sessions, mt.key, route)}
								{@const cell = routeCellView(route, options.length, pending.has(rowKey(mt.key, scope.key)), $isAdmin)}
								<td>
									<select
										aria-label="{mt.label}, {scope.label}"
										class={cell.className}
										value={cell.value}
										disabled={cell.disabled}
										onchange={(e) => handleChange(mt.key, scope.key, e.currentTarget.value)}
									>
										<option value="">None</option>
										{#each options as s (s.id)}
											<option value={s.id}>{sessionOptionLabel(s)}</option>
										{/each}
									</select>
								</td>
							{/each}
						</tr>
					{/each}
				</tbody>
			</table>
		</div>

		{#if others.length > 0}
			<div class="routing-other">
				<h4 class="eyebrow">Other routes</h4>
				<ul class="stack stack-sm routing-other-list">
					{#each others as route (route.id)}
						{@const { label, name } = otherRouteView(route, sessions)}
						<li class="routing-other-row">
							<span class="routing-other-label">
								<span class="routing-other-key">{label}:</span>
								{name}
							</span>
							{#if $isAdmin}
								<button
									type="button"
									class="btn btn-sm"
									disabled={pending.has(rowKey(route.media_type, route.disc_type))}
									aria-label="Clear {label} route ({name})"
									onclick={() => handleClear(route)}>Clear</button
								>
							{/if}
						</li>
					{/each}
				</ul>
			</div>
		{/if}
	{/if}
</section>

<style>
	.routing-title {
		font-size: 1rem;
		line-height: 1.5rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.routing-lede {
		margin-top: 0.25rem;
		font-size: 0.8125rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.routing-loading {
		padding: 1rem 0;
		text-align: center;
		font-size: 0.875rem;
		color: var(--color-text-faint);
	}
	/* a narrow window scrolls the matrix inside its box, never the page */
	.routing-box {
		overflow-x: auto;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		background: var(--color-surface);
	}
	.routing-table {
		width: 100%;
		min-width: 40rem;
		border-collapse: collapse;
		table-layout: fixed;
	}
	.routing-table th,
	.routing-table td {
		padding: 0.625rem 1rem;
		text-align: left;
	}
	.routing-table thead th {
		font-size: 0.6875rem;
		font-weight: 400;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--color-text-muted);
	}
	.routing-table tbody tr {
		border-top: 1px solid var(--color-border);
	}
	.routing-table th:first-child {
		width: 6.875rem;
	}
	.routing-cell {
		width: 100%;
		min-width: 0;
		height: 2.125rem;
		padding: 0 0.625rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-surface);
		font-family: inherit;
		font-size: 0.8125rem;
	}
	.routing-cell-set {
		border-color: var(--color-border-strong);
		color: var(--color-text);
	}
	.routing-cell-empty {
		color: var(--color-text-muted);
	}
	.routing-other-list {
		list-style: none;
		padding: 0;
	}
	.routing-other-row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		padding: 0.5rem 0.75rem;
	}
	.routing-other-label {
		min-width: 0;
		flex: 1 1 0%;
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-secondary);
	}
	.routing-other-key {
		font-weight: 500;
	}
</style>
