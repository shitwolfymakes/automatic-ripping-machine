import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import MatchPicker from './MatchPicker.svelte';

vi.mock('$lib/api/jobs', () => ({ fetchMatchDetails: vi.fn() }));
import { fetchMatchDetails } from '$lib/api/jobs';
const mockDetails = vi.mocked(fetchMatchDetails);

const rows = [
	{
		title: 'Kolchak: The Night Stalker',
		year: 1974,
		kind: 'tv',
		provider: 'tvmaze',
		external_ids: { tvmaze: '1' },
		facts: null
	},
	{ title: 'The Night Stalker', year: 1972, kind: 'tv', provider: 'tvmaze', external_ids: { tvmaze: '2' }, facts: null }
];
const props = (o = {}) => ({
	results: rows,
	query: 'Kolchak: The Night Stalker',
	year: '1974',
	providerLabel: 'TVmaze',
	canUse: true,
	useLabel: 'Use this match',
	applying: false,
	onclose: vi.fn(),
	onuse: vi.fn(),
	...o
});
const detail = (title: string, cast: string[]) => ({
	candidates: [{ title, kind: 'tv', provider: 'tvmaze', facts: { cast, genres: [], creators: [] } }]
});

describe('MatchPicker', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	it('shows the header and selects the first row, fetching its details', async () => {
		mockDetails.mockResolvedValue(detail('Kolchak: The Night Stalker', ['Darren McGavin']));
		renderComponent(MatchPicker, { props: props() });
		expect(screen.getByText('2 RESULTS')).toBeInTheDocument();
		expect(screen.getByText('"Kolchak: The Night Stalker" · 1974 · TVmaze')).toBeInTheDocument();
		expect(screen.getAllByRole('button', { pressed: true })).toHaveLength(1);
		expect(mockDetails).toHaveBeenCalledWith('tvmaze', 'tv', '1');
		await screen.findByText('Darren McGavin');
	});

	it('picking another row fetches its details once and reuses them later', async () => {
		mockDetails.mockImplementation(async (_p, _t, id) =>
			id === '1' ? detail('Kolchak: The Night Stalker', ['A']) : detail('The Night Stalker', ['B'])
		);
		renderComponent(MatchPicker, { props: props() });
		await screen.findByText('A');
		await fireEvent.click(screen.getByRole('button', { name: /^The Night Stalker/ }));
		await screen.findByText('B');
		await fireEvent.click(screen.getByRole('button', { name: /^Kolchak/ }));
		expect(screen.getByText('A')).toBeInTheDocument();
		expect(mockDetails).toHaveBeenCalledTimes(2);
	});

	it('a slow first details response does not replace the newer selection', async () => {
		let release!: (v: unknown) => void;
		mockDetails.mockImplementation((_p, _t, id) =>
			id === '1' ? (new Promise((r) => (release = r)) as never) : Promise.resolve(detail('The Night Stalker', ['B']))
		);
		const onselect = vi.fn();
		renderComponent(MatchPicker, { props: props({ onselect }) });
		await fireEvent.click(screen.getByRole('button', { name: /^The Night Stalker/ }));
		await screen.findByText('B');
		release(detail('Kolchak: The Night Stalker', ['A']));
		await waitFor(() => expect(mockDetails).toHaveBeenCalledTimes(2));
		expect(screen.getByRole('heading', { name: 'The Night Stalker' })).toBeInTheDocument();
		expect(onselect.mock.lastCall?.[1]).toBe(1);
	});

	it('a details error keeps the row and shows a note', async () => {
		mockDetails.mockResolvedValue({ candidates: [], detail: 'tvmaze: miss' });
		renderComponent(MatchPicker, { props: props() });
		await screen.findByText('tvmaze: miss');
		expect(screen.getByRole('heading', { name: 'Kolchak: The Night Stalker' })).toBeInTheDocument();
	});

	it('a rejected details call shows its message', async () => {
		mockDetails.mockRejectedValue(new Error('network down'));
		renderComponent(MatchPicker, { props: props() });
		await screen.findByText('network down');
	});

	it('Use passes the merged candidate; Close calls onclose', async () => {
		mockDetails.mockResolvedValue(detail('Kolchak: The Night Stalker', ['Darren McGavin']));
		const onuse = vi.fn();
		const onclose = vi.fn();
		renderComponent(MatchPicker, { props: props({ onuse, onclose }) });
		await screen.findByText('Darren McGavin');
		await fireEvent.click(screen.getByRole('button', { name: 'Use this match' }));
		expect(onuse.mock.calls[0][0]).toMatchObject({
			external_ids: { tvmaze: '1' },
			facts: { cast: ['Darren McGavin'] }
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
		expect(onclose).toHaveBeenCalledOnce();
	});

	it('a row without a provider id skips the details call', () => {
		renderComponent(MatchPicker, { props: props({ results: [{ title: 'X', kind: 'movie', provider: null }] }) });
		expect(mockDetails).not.toHaveBeenCalled();
		expect(screen.getByText('1 RESULT')).toBeInTheDocument();
	});
});
