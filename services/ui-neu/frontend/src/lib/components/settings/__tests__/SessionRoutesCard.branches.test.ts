import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import type { SessionRouteView, SessionView } from '$lib/types/api.gen';

// Branch pins for SessionRoutesCard, beside SessionRoutesCard.test.ts. One
// branch cannot be reached from the rendered component, so nothing here
// forces it:
// - The success side of the feedback banner's class: this card only ever
//   shows or holds an 'error', so the banner is never a success.

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
vi.mock('$lib/api/sessionRoutes', () => ({
	fetchSessionRoutes: (...args: unknown[]) => fetchSessionRoutes(...args),
	upsertSessionRoute: (...args: unknown[]) => upsertSessionRoute(...args),
	deleteSessionRoute: (...args: unknown[]) => deleteSessionRoute(...args)
}));

const fetchSessions = vi.fn();
vi.mock('$lib/api/sessions', () => ({
	fetchSessions: (...args: unknown[]) => fetchSessions(...args)
}));

import SessionRoutesCard from '../SessionRoutesCard.svelte';

function session(id: string, name: string, mediaType: string): SessionView {
	return {
		id,
		name,
		media_type: mediaType,
		is_builtin: false,
		rip_preset_id: 'rpr_x',
		transcode_preset_id: null,
		output_path_template: '{title}.{ext}',
		overrides_json: null,
		created_by_user_id: null,
		created_at: null,
		updated_at: null
	} as unknown as SessionView;
}

function route(id: string, mediaType: string, discType: string | null, sessionId: string): SessionRouteView {
	return {
		id,
		media_type: mediaType,
		disc_type: discType,
		session_id: sessionId,
		created_at: null,
		updated_at: null
	} as unknown as SessionRouteView;
}

const musicSession = session('ses_music', 'Music -> FLAC', 'music');
const movieSession = session('ses_movie', 'Movie -> MKV', 'movie');
const musicCd = route('srt_a', 'music', 'cd', 'ses_music');

async function setRole(r: string | null) {
	const auth = (await import('$lib/stores/auth')) as unknown as { __setRole: (r: string | null) => void };
	auth.__setRole(r);
}

afterEach(async () => {
	cleanup();
	vi.clearAllMocks();
	vi.useRealTimers();
	await setRole('admin');
});

describe('SessionRoutesCard rules', () => {
	it('still offers a routed session the row would not accept', async () => {
		fetchSessionRoutes.mockResolvedValue([route('srt_m', 'music', 'cd', 'ses_movie')]);
		fetchSessions.mockResolvedValue([musicSession, movieSession]);
		renderComponent(SessionRoutesCard, { props: {} });

		const select = (await screen.findByLabelText(/music.*cd session/i)) as HTMLSelectElement;
		await waitFor(() => expect(select.value).toBe('ses_movie'));
		expect([...select.options].map((o) => o.value)).toEqual(['', 'ses_movie', 'ses_music']);
	});

	it('a route to a session that no longer exists leaves the select without it', async () => {
		fetchSessionRoutes.mockResolvedValue([route('srt_m', 'music', 'cd', 'ses_gone')]);
		fetchSessions.mockResolvedValue([musicSession]);
		renderComponent(SessionRoutesCard, { props: {} });

		const select = (await screen.findByLabelText(/music.*cd session/i)) as HTMLSelectElement;
		expect([...select.options].map((o) => o.value)).toEqual(['', 'ses_music']);
		expect(screen.getByRole('button', { name: /clear music.*cd route/i })).toBeInTheDocument();
	});

	it('an Other routes row for a missing session shows the session id', async () => {
		fetchSessionRoutes.mockResolvedValue([route('srt_o', 'data', 'data', 'ses_gone')]);
		fetchSessions.mockResolvedValue([musicSession]);
		renderComponent(SessionRoutesCard, { props: {} });

		await screen.findByText(/other routes/i);
		expect(screen.getByText(/ses_gone/)).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /clear data \/ data route \(ses_gone\)/i })).toBeInTheDocument();
	});

	it('an Other routes row with no disc type reads "Any disc"', async () => {
		fetchSessionRoutes.mockResolvedValue([route('srt_i', 'iso', null, 'ses_music')]);
		fetchSessions.mockResolvedValue([musicSession]);
		renderComponent(SessionRoutesCard, { props: {} });

		await screen.findByText(/other routes/i);
		expect(screen.getByText('iso / Any disc')).toBeInTheDocument();
	});
});

describe('SessionRoutesCard rows', () => {
	it('marks a built-in session in the select', async () => {
		fetchSessionRoutes.mockResolvedValue([]);
		fetchSessions.mockResolvedValue([{ ...musicSession, is_builtin: true }]);
		renderComponent(SessionRoutesCard, { props: {} });

		const select = (await screen.findByLabelText(/music.*cd session/i)) as HTMLSelectElement;
		expect([...select.options].map((o) => o.textContent)).toEqual(['- none -', 'Music -> FLAC (built-in)']);
	});

	it('a non-admin gets no Clear button on an Other routes row', async () => {
		await setRole('guest');
		fetchSessionRoutes.mockResolvedValue([route('srt_o', 'data', 'data', 'ses_music')]);
		fetchSessions.mockResolvedValue([musicSession]);
		renderComponent(SessionRoutesCard, { props: {} });

		await screen.findByText(/other routes/i);
		expect(screen.queryByRole('button', { name: /clear/i })).not.toBeInTheDocument();
	});
});

describe('SessionRoutesCard saves', () => {
	it('a save replaces only the row it changed and keeps the other routes', async () => {
		const movieAny = route('srt_mv', 'movie', null, 'ses_movie');
		fetchSessionRoutes.mockResolvedValue([musicCd, movieAny]);
		fetchSessions.mockResolvedValue([musicSession, movieSession]);
		upsertSessionRoute.mockResolvedValue(route('srt_new', 'music', 'dvd', 'ses_music'));
		renderComponent(SessionRoutesCard, { props: {} });

		const dvd = (await screen.findByLabelText(/music.*dvd session/i)) as HTMLSelectElement;
		await fireEvent.change(dvd, { target: { value: 'ses_music' } });

		await waitFor(() => expect(screen.getByRole('button', { name: /clear music.*dvd route/i })).toBeInTheDocument());
		expect(screen.getByRole('button', { name: /clear music.*cd route/i })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /clear movie.*any disc route/i })).toBeInTheDocument();
	});

	it('shows the message when the routes fail to load with an Error', async () => {
		fetchSessionRoutes.mockRejectedValue(new Error('routes endpoint down'));
		fetchSessions.mockResolvedValue([]);
		renderComponent(SessionRoutesCard, { props: {} });

		expect(await screen.findByText('routes endpoint down')).toBeInTheDocument();
	});

	it('shows a generic message when the routes fail to load with a non-Error', async () => {
		fetchSessionRoutes.mockRejectedValue('boom');
		fetchSessions.mockResolvedValue([]);
		renderComponent(SessionRoutesCard, { props: {} });

		expect(await screen.findByText('Failed to load session routes')).toBeInTheDocument();
	});

	it('a failed save shows its Error message and reloads', async () => {
		fetchSessionRoutes.mockResolvedValue([]);
		fetchSessions.mockResolvedValue([musicSession]);
		upsertSessionRoute.mockRejectedValue(new Error('save refused'));
		renderComponent(SessionRoutesCard, { props: {} });

		const select = await screen.findByLabelText(/music.*cd session/i);
		await fireEvent.change(select, { target: { value: 'ses_music' } });

		expect(await screen.findByText('save refused')).toBeInTheDocument();
		await waitFor(() => expect(fetchSessionRoutes).toHaveBeenCalledTimes(2));
	});

	it('a failed save with a non-Error shows the generic message and reloads', async () => {
		fetchSessionRoutes.mockResolvedValue([]);
		fetchSessions.mockResolvedValue([musicSession]);
		upsertSessionRoute.mockRejectedValue('boom');
		renderComponent(SessionRoutesCard, { props: {} });

		const select = await screen.findByLabelText(/music.*cd session/i);
		await fireEvent.change(select, { target: { value: 'ses_music' } });

		expect(await screen.findByText('Failed to save route')).toBeInTheDocument();
		await waitFor(() => expect(fetchSessionRoutes).toHaveBeenCalledTimes(2));
	});

	it('a failed clear shows its Error message and reloads', async () => {
		fetchSessionRoutes.mockResolvedValue([musicCd]);
		fetchSessions.mockResolvedValue([musicSession]);
		deleteSessionRoute.mockRejectedValue(new Error('clear refused'));
		renderComponent(SessionRoutesCard, { props: {} });

		await screen.findByLabelText(/music.*cd session/i);
		await fireEvent.click(screen.getByRole('button', { name: /clear music.*cd route/i }));

		expect(await screen.findByText('clear refused')).toBeInTheDocument();
		await waitFor(() => expect(fetchSessionRoutes).toHaveBeenCalledTimes(2));
	});

	it('a failed clear with a non-Error shows the generic message and reloads', async () => {
		fetchSessionRoutes.mockResolvedValue([musicCd]);
		fetchSessions.mockResolvedValue([musicSession]);
		deleteSessionRoute.mockRejectedValue('boom');
		renderComponent(SessionRoutesCard, { props: {} });

		await screen.findByLabelText(/music.*cd session/i);
		await fireEvent.click(screen.getByRole('button', { name: /clear music.*cd route/i }));

		expect(await screen.findByText('Failed to clear route')).toBeInTheDocument();
		await waitFor(() => expect(fetchSessionRoutes).toHaveBeenCalledTimes(2));
	});

	it('the feedback message goes away after 4 seconds', async () => {
		vi.useFakeTimers();
		fetchSessionRoutes.mockResolvedValue([musicCd]);
		fetchSessions.mockResolvedValue([musicSession]);
		deleteSessionRoute.mockRejectedValue(new Error('clear refused'));
		renderComponent(SessionRoutesCard, { props: {} });
		await vi.advanceTimersByTimeAsync(0);

		await fireEvent.click(screen.getByRole('button', { name: /clear music.*cd route/i }));
		await vi.advanceTimersByTimeAsync(0);
		expect(screen.getByText('clear refused')).toBeInTheDocument();

		await vi.advanceTimersByTimeAsync(4000);
		expect(screen.queryByText('clear refused')).not.toBeInTheDocument();
	});
});
