import { describe, it, expect, afterEach, vi } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/test-utils';
import { createRawSnippet } from 'svelte';
import LogView from '$lib/components/LogView.svelte';
import { setUiPref } from '$lib/stores/uiPrefs';
import type { LogEntry } from '$lib/api/logs';

const ENTRIES: LogEntry[] = [
	{
		timestamp: '2026-09-05T10:00:00Z',
		level: 'info',
		logger: 'arm',
		event: 'backend line',
		job_id: 'job_a',
		label: null,
		service: 'arm-backend'
	},
	{
		timestamp: '2026-09-05T10:00:01Z',
		level: 'warning',
		logger: 'ripper',
		event: 'ripper line',
		job_id: 'job_a',
		label: null,
		service: 'arm-ripper-XYZ'
	},
	{
		timestamp: '2026-09-05T10:00:02Z',
		level: 'error',
		logger: 'transcode',
		event: 'transcode line',
		job_id: 'job_a',
		label: null,
		service: 'arm-transcode-t1'
	}
];

function textSnippet(text: string) {
	return createRawSnippet(() => ({
		render: () => `<span>${text}</span>`
	}));
}

/** Simulate the user scrolling the terminal away from the bottom. */
async function scrollUp(view: HTMLElement) {
	Object.defineProperty(view, 'scrollHeight', { value: 1000, configurable: true });
	Object.defineProperty(view, 'clientHeight', { value: 200, configurable: true });
	Object.defineProperty(view, 'scrollTop', { value: 0, configurable: true, writable: true });
	await fireEvent.scroll(view);
}

describe('LogView', () => {
	afterEach(() => {
		cleanup();
		setUiPref('logWrap', true);
	});

	it('renders all lines by default', () => {
		renderComponent(LogView, { props: { entries: ENTRIES } });
		expect(screen.getByText('backend line')).toBeInTheDocument();
		expect(screen.getByText('ripper line')).toBeInTheDocument();
		expect(screen.getByText('transcode line')).toBeInTheDocument();
	});

	it('shows the empty state when there are no lines', () => {
		renderComponent(LogView, { props: { entries: [] } });
		expect(screen.getByText('No log lines for this job yet.')).toBeInTheDocument();
	});

	it('shows the error state', () => {
		renderComponent(LogView, { props: { entries: [], error: new Error('boom') } });
		expect(screen.getByText(/boom/)).toBeInTheDocument();
	});

	it('shows a loading line inside the terminal area instead of the empty state', () => {
		renderComponent(LogView, { props: { entries: [], loading: true } });
		expect(screen.getByText('Loading log...')).toBeInTheDocument();
		expect(screen.queryByText('No log lines for this job yet.')).not.toBeInTheDocument();
	});

	it('filters by service', async () => {
		renderComponent(LogView, { props: { entries: ENTRIES } });
		const ripperBtn = screen.getByTestId('job-log-filter-ripper');
		await fireEvent.click(ripperBtn);

		expect(screen.getByText('ripper line')).toBeInTheDocument();
		expect(screen.queryByText('backend line')).not.toBeInTheDocument();
		expect(screen.queryByText('transcode line')).not.toBeInTheDocument();
		expect(ripperBtn).toHaveAttribute('aria-checked', 'true');
	});

	it('filters by level', async () => {
		renderComponent(LogView, { props: { entries: ENTRIES } });
		const errorBtn = screen.getByTestId('job-log-level-error');
		await fireEvent.click(errorBtn);

		expect(screen.getByText('transcode line')).toBeInTheDocument();
		expect(screen.queryByText('backend line')).not.toBeInTheDocument();
		expect(screen.queryByText('ripper line')).not.toBeInTheDocument();
		expect(errorBtn).toHaveAttribute('aria-checked', 'true');
	});

	it('does not render a search input by default', () => {
		renderComponent(LogView, { props: { entries: ENTRIES } });
		expect(screen.queryByTestId('job-log-search')).not.toBeInTheDocument();
	});

	it('filters by text search on message or logger, case-insensitively, when search is enabled', async () => {
		renderComponent(LogView, { props: { entries: ENTRIES, search: true } });
		const search = screen.getByTestId('job-log-search');
		expect(search).toHaveAttribute('placeholder', 'Filter lines');

		await fireEvent.input(search, { target: { value: 'RIPPER' } });

		expect(screen.getByText('ripper line')).toBeInTheDocument();
		expect(screen.queryByText('backend line')).not.toBeInTheDocument();
		expect(screen.queryByText('transcode line')).not.toBeInTheDocument();
	});

	it('matches case only while the Aa toggle is pressed', async () => {
		renderComponent(LogView, { props: { entries: ENTRIES, search: true } });
		await fireEvent.input(screen.getByTestId('job-log-search'), { target: { value: 'RIPPER' } });
		expect(screen.getByText('ripper line')).toBeInTheDocument();

		const caseBtn = screen.getByTestId('job-log-search-case');
		expect(caseBtn).toHaveAttribute('aria-pressed', 'false');
		await fireEvent.click(caseBtn);
		expect(caseBtn).toHaveAttribute('aria-pressed', 'true');
		expect(screen.queryByText('ripper line')).not.toBeInTheDocument();
		expect(screen.getByTestId('job-log-search-count')).toHaveTextContent('0 matches');
	});

	it('shows the match count and a clear control only while a query is set', async () => {
		renderComponent(LogView, { props: { entries: ENTRIES, search: true } });
		expect(screen.queryByTestId('job-log-search-count')).not.toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Clear filter' })).not.toBeInTheDocument();

		const search = screen.getByTestId<HTMLInputElement>('job-log-search');
		await fireEvent.input(search, { target: { value: 'line' } });
		expect(screen.getByTestId('job-log-search-count')).toHaveTextContent('3 matches');

		await fireEvent.input(search, { target: { value: 'ripper' } });
		expect(screen.getByTestId('job-log-search-count')).toHaveTextContent('1 match');

		await fireEvent.click(screen.getByRole('button', { name: 'Clear filter' }));
		expect(search.value).toBe('');
		expect(screen.getByText('backend line')).toBeInTheDocument();
		expect(screen.queryByTestId('job-log-search-count')).not.toBeInTheDocument();
		expect(document.activeElement).toBe(search);
	});

	it('shows the line count in the status bar, as "showing X of Y" once a filter hides something', async () => {
		renderComponent(LogView, { props: { entries: ENTRIES } });
		expect(screen.getByTestId('job-log-count')).toHaveTextContent('3 lines');

		await fireEvent.click(screen.getByTestId('job-log-filter-ripper'));
		expect(screen.getByTestId('job-log-count')).toHaveTextContent('Showing 1 of 3 lines');
	});

	it('shows jump-to-latest after scrolling up, and following resumes on click', async () => {
		renderComponent(LogView, { props: { entries: ENTRIES } });
		expect(screen.getByTestId('job-log-follow')).toHaveTextContent('Following');

		await scrollUp(screen.getByTestId('job-log-view'));

		const jump = screen.getByTestId('job-log-jump');
		expect(jump).toBeInTheDocument();
		expect(screen.getByTestId('job-log-follow')).toHaveTextContent('Paused');

		await fireEvent.click(jump);
		expect(screen.queryByTestId('job-log-jump')).not.toBeInTheDocument();
		expect(screen.getByTestId('job-log-follow')).toHaveTextContent('Following');
	});

	it('counts the lines that arrive while paused and resets on jump', async () => {
		const { rerender } = renderComponent(LogView, { props: { entries: ENTRIES } });
		await scrollUp(screen.getByTestId('job-log-view'));

		const more: LogEntry[] = [
			...ENTRIES,
			{ ...ENTRIES[0], timestamp: '2026-09-05T10:00:03Z', event: 'late one' },
			{ ...ENTRIES[0], timestamp: '2026-09-05T10:00:04Z', event: 'late two' }
		];
		await rerender({ entries: more });
		expect(screen.getByTestId('job-log-follow')).toHaveTextContent('Paused · 2 new lines');

		await fireEvent.click(screen.getByTestId('job-log-jump'));
		expect(screen.getByTestId('job-log-follow')).toHaveTextContent('Following');
	});

	it('counts paused arrivals from appended once a capped feed stops growing', async () => {
		const { rerender } = renderComponent(LogView, { props: { entries: ENTRIES, appended: 5 } });
		await scrollUp(screen.getByTestId('job-log-view'));

		// the cap dropped as many old lines as arrived: same length, new tail
		const shifted: LogEntry[] = [
			...ENTRIES.slice(3),
			{ ...ENTRIES[0], timestamp: '2026-09-05T10:00:03Z', event: 'late one' },
			{ ...ENTRIES[0], timestamp: '2026-09-05T10:00:04Z', event: 'late two' },
			{ ...ENTRIES[0], timestamp: '2026-09-05T10:00:05Z', event: 'late three' }
		].slice(-ENTRIES.length);
		await rerender({ entries: shifted, appended: 8 });
		expect(screen.getByTestId('job-log-follow')).toHaveTextContent('Paused · 3 new lines');
	});

	it('follows the latest line again when a collapsed view is expanded', async () => {
		const header = textSnippet('Log title');
		const { rerender } = renderComponent(LogView, { props: { entries: ENTRIES, header } });
		await scrollUp(screen.getByTestId('job-log-view'));
		expect(screen.getByTestId('job-log-follow')).toHaveTextContent('Paused');

		await rerender({ entries: ENTRIES, header, collapsed: true });
		await rerender({ entries: ENTRIES, header, collapsed: false });

		const view = screen.getByTestId('job-log-view');
		expect(screen.getByTestId('job-log-follow')).toHaveTextContent('Following');
		expect(screen.queryByTestId('job-log-jump')).not.toBeInTheDocument();
		expect(view.scrollTop).toBe(view.scrollHeight);
	});

	it('renders each line with time, service chip and message', () => {
		renderComponent(LogView, { props: { entries: ENTRIES } });
		const lines = screen.getAllByTestId('job-log-line');
		expect(lines).toHaveLength(3);
		expect(lines[0]).toHaveAttribute('data-service', 'backend');
		expect(lines[1]).toHaveAttribute('data-service', 'ripper');
		expect(lines[2]).toHaveAttribute('data-service', 'transcode');
	});

	it('tones warning, error and debug lines', () => {
		const withDebug: LogEntry[] = [...ENTRIES, { ...ENTRIES[0], level: 'debug', event: 'debug line' }];
		renderComponent(LogView, { props: { entries: withDebug } });
		expect(screen.getByText('backend line')).not.toHaveAttribute('data-tone');
		expect(screen.getByText('ripper line')).toHaveAttribute('data-tone', 'warning');
		expect(screen.getByText('transcode line')).toHaveAttribute('data-tone', 'danger');
		expect(screen.getByText('debug line')).toHaveAttribute('data-tone', 'debug');
	});

	it('applies the maxHeightClass prop to the scroll container', () => {
		renderComponent(LogView, { props: { entries: ENTRIES, maxHeightClass: 'max-h-[70vh]' } });
		expect(screen.getByTestId('job-log-view')).toHaveClass('max-h-[70vh]');
	});

	it('renders one terminal frame holding the toolbar, the lines and the status bar', () => {
		renderComponent(LogView, { props: { entries: ENTRIES } });
		const frame = screen.getByTestId('log-view');
		expect(frame).toHaveClass('log-view-frame');
		expect(frame).toContainElement(screen.getByTestId('job-log-filter-all'));
		expect(frame).toContainElement(screen.getByTestId('job-log-view'));
		expect(frame).toContainElement(screen.getByTestId('job-log-count'));
		expect(screen.queryByTestId('log-view-titlebar')).not.toBeInTheDocument();
	});

	it('renders the header snippet in a title bar, and only the title bar when collapsed', async () => {
		const { rerender } = renderComponent(LogView, {
			props: { entries: ENTRIES, header: textSnippet('Log title'), collapsed: true }
		});
		expect(screen.getByTestId('log-view-titlebar')).toHaveTextContent('Log title');
		expect(screen.getByTestId('log-view')).toHaveAttribute('data-collapsed', 'true');
		expect(screen.queryByTestId('job-log-view')).not.toBeInTheDocument();
		expect(screen.queryByTestId('job-log-filter-all')).not.toBeInTheDocument();
		expect(screen.queryByTestId('job-log-count')).not.toBeInTheDocument();

		await rerender({ entries: ENTRIES, header: textSnippet('Log title'), collapsed: false });
		expect(screen.getByTestId('log-view')).not.toHaveAttribute('data-collapsed');
		expect(screen.getByTestId('job-log-view')).toBeInTheDocument();
	});

	it('toggles line wrapping and persists it as a UI preference', async () => {
		renderComponent(LogView, { props: { entries: ENTRIES } });
		const wrap = screen.getByTestId('job-log-wrap');
		expect(wrap).toHaveAttribute('aria-pressed', 'true');
		expect(screen.getByTestId('job-log-view')).toHaveAttribute('data-wrap', 'true');

		await fireEvent.click(wrap);
		expect(wrap).toHaveAttribute('aria-pressed', 'false');
		expect(screen.getByTestId('job-log-view')).toHaveAttribute('data-wrap', 'false');
		expect(JSON.parse(localStorage.getItem('arm_ui_prefs') ?? '{}').logWrap).toBe(false);
	});

	it('copies the filtered lines as plain text', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
		renderComponent(LogView, { props: { entries: ENTRIES } });
		await fireEvent.click(screen.getByTestId('job-log-filter-ripper'));

		const copy = screen.getByTestId('job-log-copy');
		await fireEvent.click(copy);

		expect(writeText).toHaveBeenCalledTimes(1);
		expect(writeText.mock.calls[0][0]).toMatch(/^\d{2}:\d{2}:\d{2} \[Ripper\] ripper line$/);
		await vi.waitFor(() => expect(copy).toHaveTextContent('Copied'));
	});

	it('focuses the search field on "/" while focus is inside the frame', async () => {
		renderComponent(LogView, { props: { entries: ENTRIES, search: true } });
		const filterAll = screen.getByTestId('job-log-filter-all');
		filterAll.focus();
		await fireEvent.keyDown(filterAll, { key: '/' });
		expect(document.activeElement).toBe(screen.getByTestId('job-log-search'));
	});
});
