import { describe, it, expect, vi, afterEach } from 'vitest';
import { tick } from 'svelte';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/testing/render';
import MatchPicker from '../MatchPicker.svelte';

// Branch pins for MatchPicker, beside MatchPicker.test.ts. Two branches cannot
// be reached from the rendered component, so nothing here forces them:
// - The `: null` side of selectedKey's ternary: selectedKey is only read in
//   the template, after `merged &&`, and merged is null whenever selectedRow
//   is. That holds for an empty first list and for a list that empties (the
//   empty-list tests render both), so selectedKey is never evaluated with a
//   null row.
// - select's `if (!row) return;` guard: select is only called with the index of
//   a rendered row, or with 0 when the list is non-empty, so `results[index]`
//   is always set when it runs.

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
const settle = async () => {
	await tick();
	await new Promise((r) => setTimeout(r, 0));
};

describe('MatchPicker empty list', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	it('shows 0 RESULTS, no detail pane and fetches nothing', () => {
		renderComponent(MatchPicker, { props: props({ results: [] }) });
		expect(screen.getByText('0 RESULTS')).toBeInTheDocument();
		expect(screen.queryByRole('heading')).toBeNull();
		expect(screen.queryByRole('button', { name: 'Use this match' })).toBeNull();
		expect(mockDetails).not.toHaveBeenCalled();
	});

	it('a list that empties shows 0 RESULTS, drops the detail pane and fetches nothing more', async () => {
		mockDetails.mockResolvedValue(detail('Kolchak: The Night Stalker', ['A']));
		const { rerender } = renderComponent(MatchPicker, { props: props() });
		await screen.findByText('A');
		expect(mockDetails).toHaveBeenCalledTimes(1);
		await rerender(props({ results: [] }));
		await settle();
		expect(screen.getByText('0 RESULTS')).toBeInTheDocument();
		expect(screen.queryByRole('heading')).toBeNull();
		expect(screen.queryByRole('button', { name: 'Use this match' })).toBeNull();
		expect(mockDetails).toHaveBeenCalledTimes(1);
	});
});

describe('MatchPicker details cache', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	it('going back to a loaded row reports the merged row at once and fetches nothing more', async () => {
		mockDetails.mockImplementation(async (_p, _t, id) =>
			id === '1' ? detail('Kolchak: The Night Stalker', ['A']) : detail('The Night Stalker', ['B'])
		);
		const onselect = vi.fn();
		renderComponent(MatchPicker, { props: props({ onselect }) });
		await screen.findByText('A');
		await fireEvent.click(screen.getByRole('button', { name: /^The Night Stalker/ }));
		await screen.findByText('B');
		onselect.mockClear();
		await fireEvent.click(screen.getByRole('button', { name: /^Kolchak/ }));
		expect(onselect).toHaveBeenCalledOnce();
		expect(onselect.mock.calls[0][0]).toMatchObject({
			title: 'Kolchak: The Night Stalker',
			facts: { cast: ['A'] }
		});
		expect(onselect.mock.calls[0][1]).toBe(0);
		expect(mockDetails).toHaveBeenCalledTimes(2);
	});

	it('a row whose fetch is still loading is not fetched twice', async () => {
		mockDetails.mockImplementation(() => new Promise(() => {}) as never);
		renderComponent(MatchPicker, { props: props() });
		expect(mockDetails).toHaveBeenCalledTimes(1);
		await fireEvent.click(screen.getByRole('button', { name: /^The Night Stalker/ }));
		expect(mockDetails).toHaveBeenCalledTimes(2);
		await fireEvent.click(screen.getByRole('button', { name: /^Kolchak/ }));
		await fireEvent.click(screen.getByRole('button', { name: /^The Night Stalker/ }));
		expect(mockDetails).toHaveBeenCalledTimes(2);
	});

	it('a row with a provider but no provider id is never fetched', () => {
		renderComponent(MatchPicker, {
			props: props({ results: [{ title: 'Y', kind: 'tv', provider: 'tvmaze', external_ids: {} }] })
		});
		expect(screen.getByRole('heading', { name: 'Y' })).toBeInTheDocument();
		expect(mockDetails).not.toHaveBeenCalled();
	});

	it('a row with an id but no provider is never fetched', () => {
		renderComponent(MatchPicker, {
			props: props({ results: [{ title: 'Z', kind: 'movie', provider: null, external_ids: { tvmaze: '5' } }] })
		});
		expect(screen.getByRole('heading', { name: 'Z' })).toBeInTheDocument();
		expect(mockDetails).not.toHaveBeenCalled();
	});
});

describe('MatchPicker stale fetches', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	it('a rejection after results change writes nothing into the new list', async () => {
		const rejects: ((e: unknown) => void)[] = [];
		const resolves: ((v: unknown) => void)[] = [];
		let call = 0;
		mockDetails.mockImplementation(
			() =>
				new Promise((res, rej) => {
					if (call++ === 0) rejects.push(rej);
					else resolves.push(res);
				}) as never
		);
		const onselect = vi.fn();
		const { rerender } = renderComponent(MatchPicker, { props: props({ results: [rows[0]], onselect }) });
		await rerender(props({ results: [{ ...rows[0] }], onselect }));
		expect(mockDetails).toHaveBeenCalledTimes(2);
		onselect.mockClear();
		rejects[0](new Error('old list failure'));
		await settle();
		expect(screen.queryByText('old list failure')).toBeNull();
		expect(screen.getByTestId('match-pane-skeleton')).toBeInTheDocument();
		expect(onselect).not.toHaveBeenCalled();
		resolves[0](detail('Kolchak: The Night Stalker', ['fresh cast']));
		await screen.findByText('fresh cast');
		expect(screen.queryByTestId('match-pane-skeleton')).toBeNull();
	});

	it('a resolve after results change reports nothing and leaves no loading flag', async () => {
		const resolves: ((v: unknown) => void)[] = [];
		mockDetails.mockImplementation(() => new Promise((res) => resolves.push(res)) as never);
		const onselect = vi.fn();
		const { rerender } = renderComponent(MatchPicker, { props: props({ results: [rows[0]], onselect }) });
		await rerender(props({ results: [], onselect }));
		onselect.mockClear();
		resolves[0](detail('Kolchak: The Night Stalker', ['late cast']));
		await settle();
		expect(screen.queryByText('late cast')).toBeNull();
		expect(onselect).not.toHaveBeenCalled();
		await rerender(props({ results: [{ ...rows[0] }], onselect }));
		expect(screen.getByTestId('match-pane-skeleton')).toBeInTheDocument();
	});

	it('a rejection that is not an Error shows "Could not load details"', async () => {
		mockDetails.mockRejectedValue('boom');
		renderComponent(MatchPicker, { props: props() });
		expect(await screen.findByText('Could not load details')).toBeInTheDocument();
	});

	it('a response with no candidates and no detail shows "No details found."', async () => {
		mockDetails.mockResolvedValue({ candidates: [] });
		renderComponent(MatchPicker, { props: props() });
		expect(await screen.findByText('No details found.')).toBeInTheDocument();
	});

	it('a response with no candidates shows its detail', async () => {
		mockDetails.mockResolvedValue({ candidates: [], detail: 'tvmaze: miss' });
		renderComponent(MatchPicker, { props: props() });
		expect(await screen.findByText('tvmaze: miss')).toBeInTheDocument();
	});
});
