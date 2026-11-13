import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import type { SessionRouteView, SessionView } from '$lib/types/api.gen';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		isGuest: derived(_role, (r) => r === 'guest'),
		// Test-only helper, not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});

const fetchSessionRoutes = vi.fn();
const upsertSessionRoute = vi.fn();
const deleteSessionRoute = vi.fn();
vi.mock('$lib/api/session-routes', () => ({
	fetchSessionRoutes: (...args: unknown[]) => fetchSessionRoutes(...args),
	upsertSessionRoute: (...args: unknown[]) => upsertSessionRoute(...args),
	deleteSessionRoute: (...args: unknown[]) => deleteSessionRoute(...args)
}));

const fetchSessions = vi.fn();
vi.mock('$lib/api/sessions', () => ({
	fetchSessions: (...args: unknown[]) => fetchSessions(...args)
}));

import RoutingMatrix from '../RoutingMatrix.svelte';

async function setRole(r: string | null) {
	const auth = (await import('$lib/stores/auth')) as unknown as { __setRole: (r: string | null) => void };
	auth.__setRole(r);
}

function session(id: string, name: string, media: string, builtin = false): SessionView {
	return {
		id,
		name,
		media_type: media,
		is_builtin: builtin,
		rip_preset_id: 'rpr',
		transcode_preset_id: null,
		output_path_template: '{title}.{ext}',
		overrides_json: null,
		created_by_user_id: null,
		created_at: null,
		updated_at: null
	} as unknown as SessionView;
}

function route(id: string, media: string, disc: string | null, sessionId: string): SessionRouteView {
	return {
		id,
		media_type: media,
		disc_type: disc,
		session_id: sessionId,
		created_at: null,
		updated_at: null
	} as unknown as SessionRouteView;
}

const movie = session('ses_movie', 'Movie to Plex', 'movie', true);
const music = session('ses_music', 'Music to FLAC', 'music');
const musicCd = route('srt_cd', 'music', 'cd', 'ses_music');

async function renderMatrix(routes: SessionRouteView[] = [], sessions: SessionView[] = [movie, music]) {
	fetchSessionRoutes.mockResolvedValue(routes);
	fetchSessions.mockResolvedValue(sessions);
	renderComponent(RoutingMatrix, { props: {} });
	return (await screen.findByLabelText('Music, CD')) as HTMLSelectElement;
}

afterEach(async () => {
	cleanup();
	vi.clearAllMocks();
	await setRole('admin');
});

describe('RoutingMatrix layout', () => {
	it('shows the heading, the spec line and the four disc columns', async () => {
		await renderMatrix();
		expect(screen.getByRole('heading', { name: 'Routing' })).toBeInTheDocument();
		expect(
			screen.getByText(
				"A route applies the chosen session when a disc's identified media type matches. A drive's default session wins when it fits the disc's media type. A disc-type route (DVD, Blu-ray, CD) beats Any disc."
			)
		).toBeInTheDocument();
		for (const col of ['Any disc', 'DVD', 'Blu-ray', 'CD']) {
			expect(screen.getByRole('columnheader', { name: col })).toBeInTheDocument();
		}
	});

	it('has one row per media type, labelled by a media pill, and no ISO row', async () => {
		await renderMatrix();
		const rows = screen.getAllByRole('row').slice(1);
		expect(rows.map((r) => r.querySelector('.media-pill')?.textContent?.trim())).toEqual([
			'Movie',
			'TV',
			'Music',
			'Data'
		]);
		expect(screen.getAllByRole('combobox')).toHaveLength(16);
	});

	it('names each select "<Media>, <Disc>" and offers None plus that media type sessions', async () => {
		const cd = await renderMatrix();
		const labels = (el: HTMLSelectElement) => [...el.options].map((o) => o.textContent?.trim());
		expect(labels(cd)).toEqual(['None', 'Music to FLAC']);
		expect(labels(screen.getByLabelText('Movie, Any disc') as HTMLSelectElement)).toEqual([
			'None',
			'Movie to Plex (built-in)'
		]);
	});

	it('marks a cell with a route as set and an empty cell as dimmed', async () => {
		const cd = await renderMatrix([musicCd]);
		expect(cd.value).toBe('ses_music');
		expect(cd).toHaveClass('routing-cell-set');
		expect(cd).not.toHaveClass('routing-cell-empty');
		const dvd = screen.getByLabelText('Music, DVD');
		expect(dvd).toHaveClass('routing-cell-empty');
		expect(dvd).not.toHaveClass('routing-cell-set');
	});

	it('lists a route outside the matrix under Other routes, and clears it', async () => {
		const isoRoute = route('srt_iso', 'iso', null, 'ses_movie');
		deleteSessionRoute.mockResolvedValue(undefined);
		await renderMatrix([isoRoute]);
		expect(screen.getByText('Other routes')).toBeInTheDocument();
		const row = screen.getByText('ISO / Any disc:').closest('li') as HTMLElement;
		expect(row).toHaveTextContent('ISO / Any disc: Movie to Plex');
		expect(row.textContent).not.toContain('\u2192');
		await fireEvent.click(screen.getByRole('button', { name: /clear iso \/ any disc route/i }));
		await waitFor(() => expect(deleteSessionRoute).toHaveBeenCalledWith('srt_iso'));
		await waitFor(() => expect(screen.queryByText('Other routes')).not.toBeInTheDocument());
	});

	it('hides the Clear button on Other routes for a non-admin', async () => {
		await setRole('user');
		await renderMatrix([route('srt_iso', 'iso', null, 'ses_movie')]);
		expect(screen.getByText('Other routes')).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: /clear/i })).not.toBeInTheDocument();
	});

	it('shows a loading line until the data arrives', async () => {
		fetchSessionRoutes.mockReturnValue(new Promise(() => {}));
		fetchSessions.mockReturnValue(new Promise(() => {}));
		renderComponent(RoutingMatrix, { props: {} });
		expect(screen.getByText('Loading...')).toBeInTheDocument();
		expect(screen.queryByRole('table')).not.toBeInTheDocument();
	});

	it('disables every select for a non-admin', async () => {
		await setRole('user');
		const cd = await renderMatrix([musicCd]);
		expect(cd).toBeDisabled();
	});

	it('follows the role when it changes after the matrix has rendered', async () => {
		await setRole('admin');
		const cd = await renderMatrix([musicCd]);
		expect(cd).not.toBeDisabled();
		await setRole('user');
		await waitFor(() => expect(cd).toBeDisabled());
	});

	it('disables a select that has no session to offer', async () => {
		await renderMatrix([], [movie]);
		expect(screen.getByLabelText('Music, DVD')).toBeDisabled();
		expect(screen.getByLabelText('Movie, DVD')).not.toBeDisabled();
	});
});

describe('RoutingMatrix saves', () => {
	it('choosing a session upserts the route and marks the cell set', async () => {
		upsertSessionRoute.mockResolvedValue(route('srt_new', 'music', 'dvd', 'ses_music'));
		await renderMatrix();
		const dvd = screen.getByLabelText('Music, DVD') as HTMLSelectElement;
		await fireEvent.change(dvd, { target: { value: 'ses_music' } });
		await waitFor(() =>
			expect(upsertSessionRoute).toHaveBeenCalledWith({
				media_type: 'music',
				disc_type: 'dvd',
				session_id: 'ses_music'
			})
		);
		await waitFor(() => expect(dvd).toHaveClass('routing-cell-set'));
	});

	it('choosing None on a routed cell deletes the route', async () => {
		deleteSessionRoute.mockResolvedValue(undefined);
		const cd = await renderMatrix([musicCd]);
		await fireEvent.change(cd, { target: { value: '' } });
		await waitFor(() => expect(deleteSessionRoute).toHaveBeenCalledWith('srt_cd'));
		expect(upsertSessionRoute).not.toHaveBeenCalled();
		await waitFor(() => expect(cd).toHaveClass('routing-cell-empty'));
	});

	it('choosing None on an empty cell does nothing', async () => {
		const cd = await renderMatrix();
		await fireEvent.change(cd, { target: { value: '' } });
		expect(deleteSessionRoute).not.toHaveBeenCalled();
		expect(upsertSessionRoute).not.toHaveBeenCalled();
	});

	it('a rejected upsert reverts the select, shows the error and reloads', async () => {
		upsertSessionRoute.mockRejectedValue(new Error('save refused'));
		await renderMatrix();
		const dvd = screen.getByLabelText('Music, DVD') as HTMLSelectElement;
		await fireEvent.change(dvd, { target: { value: 'ses_music' } });
		expect(await screen.findByText('save refused')).toBeInTheDocument();
		await waitFor(() => expect(fetchSessionRoutes).toHaveBeenCalledTimes(2));
		const after = (await screen.findByLabelText('Music, DVD')) as HTMLSelectElement;
		expect(after.value).toBe('');
		expect(after).toHaveClass('routing-cell-empty');
	});

	it('a rejected upsert with a non-Error shows the generic message', async () => {
		upsertSessionRoute.mockRejectedValue('boom');
		await renderMatrix();
		await fireEvent.change(screen.getByLabelText('Music, DVD'), { target: { value: 'ses_music' } });
		expect(await screen.findByText('Failed to save route')).toBeInTheDocument();
	});

	it('a rejected delete keeps the route, shows the error and reloads', async () => {
		deleteSessionRoute.mockRejectedValue(new Error('clear refused'));
		const cd = await renderMatrix([musicCd]);
		await fireEvent.change(cd, { target: { value: '' } });
		expect(await screen.findByText('clear refused')).toBeInTheDocument();
		await waitFor(() => expect(fetchSessionRoutes).toHaveBeenCalledTimes(2));
		expect(((await screen.findByLabelText('Music, CD')) as HTMLSelectElement).value).toBe('ses_music');
	});

	it('a rejected delete with a non-Error shows the generic message', async () => {
		deleteSessionRoute.mockRejectedValue('boom');
		const cd = await renderMatrix([musicCd]);
		await fireEvent.change(cd, { target: { value: '' } });
		expect(await screen.findByText('Failed to clear route')).toBeInTheDocument();
	});

	it('shows the load error message, or a generic one for a non-Error', async () => {
		fetchSessionRoutes.mockRejectedValue(new Error('routes endpoint down'));
		fetchSessions.mockResolvedValue([]);
		renderComponent(RoutingMatrix, { props: {} });
		expect(await screen.findByText('routes endpoint down')).toBeInTheDocument();
		cleanup();
		fetchSessionRoutes.mockRejectedValue('boom');
		renderComponent(RoutingMatrix, { props: {} });
		expect(await screen.findByText('Failed to load session routes')).toBeInTheDocument();
	});

	it('the feedback message goes away after 4 seconds', async () => {
		vi.useFakeTimers();
		fetchSessionRoutes.mockResolvedValue([musicCd]);
		fetchSessions.mockResolvedValue([music]);
		deleteSessionRoute.mockRejectedValue(new Error('clear refused'));
		renderComponent(RoutingMatrix, { props: {} });
		await vi.advanceTimersByTimeAsync(0);
		await fireEvent.change(screen.getByLabelText('Music, CD'), { target: { value: '' } });
		await vi.advanceTimersByTimeAsync(0);
		expect(screen.getByText('clear refused')).toBeInTheDocument();
		await vi.advanceTimersByTimeAsync(4000);
		expect(screen.queryByText('clear refused')).not.toBeInTheDocument();
		vi.useRealTimers();
	});
});
