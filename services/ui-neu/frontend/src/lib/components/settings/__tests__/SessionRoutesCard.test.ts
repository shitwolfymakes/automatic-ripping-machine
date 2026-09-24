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
		// Test-only helper — not part of the real module's public API.
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

async function setRole(r: string | null) {
	const auth = (await import('$lib/stores/auth')) as unknown as { __setRole: (r: string | null) => void };
	auth.__setRole(r);
}

const musicSession: SessionView = {
	id: 'ses_music',
	name: 'Music -> FLAC',
	media_type: 'music',
	is_builtin: true,
	rip_preset_id: 'rpr_music',
	transcode_preset_id: null,
	output_path_template: '{artist}/{album}/{track}.{ext}',
	overrides_json: null,
	created_by_user_id: null,
	created_at: null,
	updated_at: null
} as unknown as SessionView;

const movieSession: SessionView = {
	id: 'ses_movie',
	name: 'Movie -> MKV',
	media_type: 'movie',
	is_builtin: true,
	rip_preset_id: 'rpr_movie',
	transcode_preset_id: null,
	output_path_template: '{title}.{ext}',
	overrides_json: null,
	created_by_user_id: null,
	created_at: null,
	updated_at: null
} as unknown as SessionView;

const seededRoutes: SessionRouteView[] = [
	{ id: 'srt_a', media_type: 'music', disc_type: 'cd', session_id: 'ses_music', created_at: null, updated_at: null },
	{ id: 'srt_b', media_type: 'music', disc_type: null, session_id: 'ses_music', created_at: null, updated_at: null }
];

afterEach(async () => {
	cleanup();
	vi.clearAllMocks();
	await setRole('admin');
});

describe('SessionRoutesCard', () => {
	it('help text matches the compatibility-gated drive-default override (Fix 76-8)', async () => {
		fetchSessionRoutes.mockResolvedValue([]);
		fetchSessions.mockResolvedValue([musicSession, movieSession]);
		renderComponent(SessionRoutesCard, { props: {} });

		await waitFor(() => expect(screen.getAllByRole('combobox')).toHaveLength(16));
		// The drive default only wins when compatible with the disc's media
		// type; an incompatible default falls through to routes (G-17). The old
		// copy claimed the default "overrides every route" unconditionally,
		// which is what this pins away from.
		expect(screen.getByText(/wins when it is compatible/i)).toBeInTheDocument();
		expect(screen.queryByText(/overrides every route/i)).not.toBeInTheDocument();
	});

	it('renders a row for every media type x disc-scope combination', async () => {
		fetchSessionRoutes.mockResolvedValue([]);
		fetchSessions.mockResolvedValue([musicSession, movieSession]);
		renderComponent(SessionRoutesCard, { props: {} });

		// 4 media types x 4 disc scopes (any/dvd/bluray/cd) = 16 rows
		await waitFor(() => expect(screen.getAllByRole('combobox')).toHaveLength(16));
	});

	it('shows the seeded music routes selected on load', async () => {
		fetchSessionRoutes.mockResolvedValue(seededRoutes);
		fetchSessions.mockResolvedValue([musicSession, movieSession]);
		renderComponent(SessionRoutesCard, { props: {} });

		const cdSelect = (await screen.findByLabelText(/music.*cd session/i)) as HTMLSelectElement;
		expect(cdSelect.value).toBe('ses_music');

		const anySelect = screen.getByLabelText(/music.*any disc session/i) as HTMLSelectElement;
		expect(anySelect.value).toBe('ses_music');
	});

	it('changing a row dropdown upserts the route', async () => {
		fetchSessionRoutes.mockResolvedValue([]);
		fetchSessions.mockResolvedValue([musicSession]);
		upsertSessionRoute.mockResolvedValue({
			id: 'srt_new',
			media_type: 'music',
			disc_type: 'cd',
			session_id: 'ses_music',
			created_at: null,
			updated_at: null
		});
		renderComponent(SessionRoutesCard, { props: {} });

		const cdSelect = await screen.findByLabelText(/music.*cd session/i);
		await fireEvent.change(cdSelect, { target: { value: 'ses_music' } });

		await waitFor(() =>
			expect(upsertSessionRoute).toHaveBeenCalledWith({
				media_type: 'music',
				disc_type: 'cd',
				session_id: 'ses_music'
			})
		);
	});

	it('clearing a row with a route deletes it', async () => {
		fetchSessionRoutes.mockResolvedValue(seededRoutes);
		fetchSessions.mockResolvedValue([musicSession]);
		deleteSessionRoute.mockResolvedValue(undefined);
		renderComponent(SessionRoutesCard, { props: {} });

		await screen.findByLabelText(/music.*cd session/i);
		await fireEvent.click(screen.getByRole('button', { name: /clear music.*cd route/i }));

		await waitFor(() => expect(deleteSessionRoute).toHaveBeenCalledWith('srt_a'));
	});

	it('selecting "- none -" on a row with an existing route deletes it (M1)', async () => {
		fetchSessionRoutes.mockResolvedValue(seededRoutes);
		fetchSessions.mockResolvedValue([musicSession]);
		deleteSessionRoute.mockResolvedValue(undefined);
		renderComponent(SessionRoutesCard, { props: {} });

		const cdSelect = (await screen.findByLabelText(/music.*cd session/i)) as HTMLSelectElement;
		expect(cdSelect.value).toBe('ses_music');
		await fireEvent.change(cdSelect, { target: { value: '' } });

		await waitFor(() => expect(deleteSessionRoute).toHaveBeenCalledWith('srt_a'));
		expect(upsertSessionRoute).not.toHaveBeenCalled();
	});

	it('selecting "- none -" on a row with no existing route is a no-op', async () => {
		fetchSessionRoutes.mockResolvedValue([]);
		fetchSessions.mockResolvedValue([musicSession]);
		renderComponent(SessionRoutesCard, { props: {} });

		const cdSelect = (await screen.findByLabelText(/music.*cd session/i)) as HTMLSelectElement;
		await fireEvent.change(cdSelect, { target: { value: '' } });

		expect(deleteSessionRoute).not.toHaveBeenCalled();
		expect(upsertSessionRoute).not.toHaveBeenCalled();
	});

	it('renders a data/data route in the Other routes list, not duplicated in the grid', async () => {
		const dataSession: SessionView = {
			id: 'ses_data',
			name: 'Data -> Copy',
			media_type: 'data',
			is_builtin: true,
			rip_preset_id: 'rpr_data',
			transcode_preset_id: null,
			output_path_template: '{title}/',
			overrides_json: null,
			created_by_user_id: null,
			created_at: null,
			updated_at: null
		} as unknown as SessionView;
		const otherRoute: SessionRouteView = {
			id: 'srt_other',
			media_type: 'data',
			disc_type: 'data',
			session_id: 'ses_data',
			created_at: null,
			updated_at: null
		};
		fetchSessionRoutes.mockResolvedValue([otherRoute]);
		fetchSessions.mockResolvedValue([musicSession, dataSession]);
		renderComponent(SessionRoutesCard, { props: {} });

		await screen.findByText(/other routes/i);
		expect(screen.getByText(/data \/ data/i)).toBeInTheDocument();

		// Not duplicated into the grid: the grid's Data/CD row must still show
		// its own "- none -" state, unaffected by the data/data route.
		const dataCdSelect = screen.getByLabelText(/data.*cd session/i) as HTMLSelectElement;
		expect(dataCdSelect.value).toBe('');
	});

	it('clearing an Other-routes row calls the delete API', async () => {
		const dataSession: SessionView = {
			id: 'ses_data',
			name: 'Data -> Copy',
			media_type: 'data',
			is_builtin: true,
			rip_preset_id: 'rpr_data',
			transcode_preset_id: null,
			output_path_template: '{title}/',
			overrides_json: null,
			created_by_user_id: null,
			created_at: null,
			updated_at: null
		} as unknown as SessionView;
		const otherRoute: SessionRouteView = {
			id: 'srt_other',
			media_type: 'data',
			disc_type: 'data',
			session_id: 'ses_data',
			created_at: null,
			updated_at: null
		};
		fetchSessionRoutes.mockResolvedValue([otherRoute]);
		fetchSessions.mockResolvedValue([dataSession]);
		deleteSessionRoute.mockResolvedValue(undefined);
		renderComponent(SessionRoutesCard, { props: {} });

		await screen.findByText(/other routes/i);
		await fireEvent.click(screen.getByRole('button', { name: /clear.*data -> copy/i }));

		await waitFor(() => expect(deleteSessionRoute).toHaveBeenCalledWith('srt_other'));
	});

	it('does not show an Other routes section when every route is grid-covered', async () => {
		fetchSessionRoutes.mockResolvedValue(seededRoutes);
		fetchSessions.mockResolvedValue([musicSession, movieSession]);
		renderComponent(SessionRoutesCard, { props: {} });

		await screen.findByLabelText(/music.*cd session/i);
		expect(screen.queryByText(/other routes/i)).not.toBeInTheDocument();
	});

	it('is read-only for a non-writer: selects disabled, no clear buttons', async () => {
		await setRole('guest');
		fetchSessionRoutes.mockResolvedValue(seededRoutes);
		fetchSessions.mockResolvedValue([musicSession]);
		renderComponent(SessionRoutesCard, { props: {} });

		const cdSelect = (await screen.findByLabelText(/music.*cd session/i)) as HTMLSelectElement;
		expect(cdSelect.disabled).toBe(true);
		expect(screen.queryByRole('button', { name: /clear music.*cd route/i })).not.toBeInTheDocument();
	});
});
