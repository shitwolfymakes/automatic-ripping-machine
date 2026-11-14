import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor, within } from '$lib/testing/render';
import type { DiscRouteSummary, SetupView } from '$lib/types/api.gen';

// Pins what DiscsStep does today. SetupConfigFields is replaced by a stub
// whose save() a test controls, and the routes call is the only I/O faked. No
// branch is left open.

const fetchDiscRoutes = vi.fn();
vi.mock('$lib/api/setup', () => ({ fetchDiscRoutes: () => fetchDiscRoutes() }));
vi.mock('../../SetupConfigFields.svelte', async () => ({
	default: (await import('./fixtures/SetupConfigFieldsControlledStub.svelte')).default
}));

import DiscsStep from '../DiscsStep.svelte';
import { saveControl } from './fixtures/setup-config-fields-control';

const view = (): SetupView => ({
	completed_at: null,
	progress: {},
	current_step: 'discs',
	admin_default_password: false,
	checklist_dismissed: false
});
const route = (over: Partial<DiscRouteSummary> = {}): DiscRouteSummary => ({
	kind: 'movie',
	session_id: 'ses_a',
	session_name: 'Movie session',
	rip_summary: 'Rip main feature',
	transcode_summary: 'H.265',
	output_template: null,
	...over
});
type Step = { commit(): Promise<string | false> };

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
	saveControl.result = true;
});

describe('DiscsStep routes', () => {
	it('shows Loading... until the routes arrive', async () => {
		fetchDiscRoutes.mockReturnValue(new Promise(() => {}));
		renderComponent(DiscsStep, { props: { view: view() } });
		expect(await screen.findByText('Loading...')).toBeInTheDocument();
		expect(screen.queryByText('Example movie')).toBeNull();
	});

	it('shows no rows when the routes fail to load', async () => {
		fetchDiscRoutes.mockRejectedValue(new Error('500'));
		renderComponent(DiscsStep, { props: { view: view() } });
		await waitFor(() => expect(screen.queryByText('Loading...')).toBeNull());
		expect(screen.queryByText('Rips')).toBeNull();
		expect(screen.getByText('You can change these later in Settings, Sessions.')).toBeInTheDocument();
	});

	it('shows a row per route with its kind label, and an unknown kind as itself', async () => {
		fetchDiscRoutes.mockResolvedValue([
			route({ kind: 'movie' }),
			route({ kind: 'tv' }),
			route({ kind: 'music' }),
			route({ kind: 'data' }),
			route({ kind: 'iso' }),
			route({ kind: 'bluray-extra' as DiscRouteSummary['kind'] })
		]);
		renderComponent(DiscsStep, { props: { view: view() } });
		for (const label of ['Movie', 'TV', 'Music CD', 'Data', 'ISO', 'bluray-extra']) {
			expect(await screen.findByText(label)).toBeInTheDocument();
		}
		expect(screen.getAllByText('Rips')).toHaveLength(6);
	});

	it('shows the rip, encode and output cells of a route with an output template', async () => {
		fetchDiscRoutes.mockResolvedValue([route({ output_template: '{title} ({year})/{title}.{ext}' })]);
		renderComponent(DiscsStep, { props: { view: view() } });
		const table = within(await screen.findByTestId('disc-routes'));
		expect(await table.findByText('Rip main feature')).toBeInTheDocument();
		expect(table.getByText('Movie session')).toBeInTheDocument();
		expect(table.getByText('H.265')).toBeInTheDocument();
		expect(table.getAllByText('Fight Club (1999)/Fight Club.mkv')).toHaveLength(2);
		expect(table.queryByText('Not set')).toBeNull();
	});

	it('shows the empty cells of a route with no session, encode or output template', async () => {
		fetchDiscRoutes.mockResolvedValue([
			route({ session_name: null, rip_summary: null, transcode_summary: null, output_template: null })
		]);
		renderComponent(DiscsStep, { props: { view: view() } });
		expect(await screen.findByText('No session')).toBeInTheDocument();
		expect(screen.getByText('No encode')).toBeInTheDocument();
		expect(screen.getByText('Not set')).toBeInTheDocument();
		expect(screen.queryByText('Example movie')).toBeNull();
	});

	it('shows no example movie when only a TV route has a template', async () => {
		fetchDiscRoutes.mockResolvedValue([
			route({ kind: 'tv', output_template: '{show}/{episode}.{ext}' }),
			route({ kind: 'movie', output_template: '' })
		]);
		renderComponent(DiscsStep, { props: { view: view() } });
		await screen.findByText('Movie');
		expect(screen.queryByText('Example movie')).toBeNull();
	});

	it('shows the example movie for a movie route with a template', async () => {
		fetchDiscRoutes.mockResolvedValue([route({ kind: 'movie', output_template: '{title}.{ext}' })]);
		renderComponent(DiscsStep, { props: { view: view() } });
		expect(await screen.findByText('Example movie')).toBeInTheDocument();
		expect(screen.getByText('Fight Club.mkv', { selector: 'code' })).toBeInTheDocument();
	});
});

describe('DiscsStep commit', () => {
	it('resolves false when the config fields do not save', async () => {
		fetchDiscRoutes.mockResolvedValue([]);
		saveControl.result = false;
		const { component } = renderComponent(DiscsStep, { props: { view: view() } });
		expect(await (component as unknown as Step).commit()).toBe(false);
	});

	it('resolves done when the config fields save', async () => {
		fetchDiscRoutes.mockResolvedValue([]);
		const { component } = renderComponent(DiscsStep, { props: { view: view() } });
		expect(await (component as unknown as Step).commit()).toBe('done');
	});
});
