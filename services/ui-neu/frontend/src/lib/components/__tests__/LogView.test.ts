import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/test-utils';
import LogView from '$lib/components/LogView.svelte';
import type { LogEntry } from '$lib/api/logs';

const ENTRIES: LogEntry[] = [
	{ timestamp: '2026-09-05T10:00:00Z', level: 'info', logger: 'arm', event: 'backend line', job_id: 'job_a', label: null, service: 'arm-backend' },
	{ timestamp: '2026-09-05T10:00:01Z', level: 'warning', logger: 'ripper', event: 'ripper line', job_id: 'job_a', label: null, service: 'arm-ripper-XYZ' },
	{ timestamp: '2026-09-05T10:00:02Z', level: 'error', logger: 'transcode', event: 'transcode line', job_id: 'job_a', label: null, service: 'arm-transcode-t1' }
];

afterEach(() => cleanup());

describe('LogView', () => {
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

	it('shows a count line only when a filter hides something', async () => {
		renderComponent(LogView, { props: { entries: ENTRIES } });
		expect(screen.queryByTestId('job-log-count')).not.toBeInTheDocument();

		const ripperBtn = screen.getByTestId('job-log-filter-ripper');
		await fireEvent.click(ripperBtn);

		expect(screen.getByTestId('job-log-count')).toHaveTextContent('Showing 1 of 3 lines');
	});

	it('shows jump-to-latest after scrolling up, and following resumes on click', async () => {
		renderComponent(LogView, { props: { entries: ENTRIES } });
		const view = screen.getByTestId('job-log-view');

		Object.defineProperty(view, 'scrollHeight', { value: 1000, configurable: true });
		Object.defineProperty(view, 'clientHeight', { value: 200, configurable: true });
		Object.defineProperty(view, 'scrollTop', { value: 0, configurable: true, writable: true });

		await fireEvent.scroll(view);

		const jump = screen.getByTestId('job-log-jump');
		expect(jump).toBeInTheDocument();

		await fireEvent.click(jump);
		expect(screen.queryByTestId('job-log-jump')).not.toBeInTheDocument();
	});

	it('renders each line with time, service chip and message', () => {
		renderComponent(LogView, { props: { entries: ENTRIES } });
		const lines = screen.getAllByTestId('job-log-line');
		expect(lines).toHaveLength(3);
		expect(lines[0]).toHaveAttribute('data-service', 'backend');
		expect(lines[1]).toHaveAttribute('data-service', 'ripper');
		expect(lines[2]).toHaveAttribute('data-service', 'transcode');
	});

	it('applies the maxHeightClass prop to the scroll container', () => {
		renderComponent(LogView, { props: { entries: ENTRIES, maxHeightClass: 'max-h-[70vh]' } });
		expect(screen.getByTestId('job-log-view')).toHaveClass('max-h-[70vh]');
	});
});
