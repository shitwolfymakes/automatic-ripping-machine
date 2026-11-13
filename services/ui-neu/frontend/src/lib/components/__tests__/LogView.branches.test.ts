import { describe, it, expect, afterEach, vi } from 'vitest';
import { tick, createRawSnippet } from 'svelte';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/test-utils';
import LogView from '$lib/components/LogView.svelte';
import { setUiPref } from '$lib/stores/ui-prefs';
import type { LogEntry } from '$lib/api/logs';

// Branch pins for LogView, beside LogView.test.ts. One branch cannot be
// reached by a user, so nothing here forces it: onWindowKeydown's
// `frameEl === null` operand. The frame div is always rendered, so frameEl is
// set before any key can arrive. The coverage tool counts the operand as
// evaluated and reports no gap; only its true outcome is unreachable.
// (The scroll check's null-view return, which a user can't reach here either,
// now lives in FollowScroll, whose own tests cover it.)
// jsdom does not implement isContentEditable (it is undefined on every
// element), so the contentEditable test defines it on the element with
// Object.defineProperty, as a browser reports it.

// LogEntry types level, logger and event as string, but the component guards
// them with `??`, so a null is passed through a cast to pin that guard.
const NULL = null as unknown as string;

function entry(over: Partial<LogEntry> = {}): LogEntry {
	return {
		timestamp: '2026-09-05T10:00:00Z',
		level: 'info',
		logger: 'arm',
		event: 'line',
		job_id: 'job_a',
		label: null,
		service: 'arm-backend',
		...over
	};
}

const ENTRIES: LogEntry[] = [
	entry({ event: 'backend line', service: 'arm-backend' }),
	entry({ event: 'ripper line', service: 'arm-ripper-XYZ' }),
	entry({ event: 'transcode line', service: 'arm-transcode-t1' })
];

function textSnippet(text: string) {
	return createRawSnippet(() => ({
		render: () => `<span>${text}</span>`
	}));
}

/** Give the terminal a fixed geometry, scrolled `top` px from the top. */
function setScroll(view: HTMLElement, top: number) {
	Object.defineProperty(view, 'scrollHeight', { value: 1000, configurable: true });
	Object.defineProperty(view, 'clientHeight', { value: 200, configurable: true });
	Object.defineProperty(view, 'scrollTop', { value: top, configurable: true, writable: true });
}

async function scrollTo(view: HTMLElement, top: number) {
	setScroll(view, top);
	await fireEvent.scroll(view);
}

/** The message text of every rendered line, in order. */
function shown(): string[] {
	return screen.queryAllByTestId('job-log-line').map((l) => l.querySelector('.log-view-line')?.textContent ?? '');
}

const timeOf = (ts: string) => new Date(ts).toLocaleTimeString([], { hour12: false });

const originalClipboard = Object.getOwnPropertyDescriptor(navigator, 'clipboard');

function stubClipboard(writeText: unknown) {
	Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
}

afterEach(() => {
	cleanup();
	setUiPref('logWrap', true);
	vi.useRealTimers();
	vi.unstubAllGlobals();
	if (originalClipboard) Object.defineProperty(navigator, 'clipboard', originalClipboard);
	else Reflect.deleteProperty(navigator, 'clipboard');
});

describe('LogView service filter', () => {
	const MIXED = [
		entry({ event: 'b', service: 'arm-backend' }),
		entry({ event: 'r', service: 'arm-ripper-1' }),
		entry({ event: 't', service: 'arm-transcode-1' }),
		entry({ event: 'n', service: 'nginx' })
	];

	it.each([
		['backend', ['b']],
		['ripper', ['r']],
		['transcode', ['t']],
		['all', ['b', 'r', 't', 'n']]
	])('shows only the %s group, with All showing a stray service', async (key, expected) => {
		renderComponent(LogView, { props: { entries: MIXED } });
		await fireEvent.click(screen.getByTestId(`job-log-filter-${key}`));
		expect(shown()).toEqual(expected);
	});

	it('marks only the chosen service segment aria-checked', async () => {
		renderComponent(LogView, { props: { entries: MIXED } });
		const keys = ['all', 'backend', 'ripper', 'transcode'];
		for (const chosen of keys) {
			await fireEvent.click(screen.getByTestId(`job-log-filter-${chosen}`));
			for (const key of keys) {
				expect(screen.getByTestId(`job-log-filter-${key}`)).toHaveAttribute('aria-checked', String(key === chosen));
			}
		}
	});
});

describe('LogView level filter', () => {
	const LEVELS = [
		entry({ event: 'i', level: 'info' }),
		entry({ event: 'w', level: 'WARNING' }),
		entry({ event: 'e', level: 'Error' }),
		entry({ event: 'c', level: 'critical' }),
		entry({ event: 'd', level: 'debug' }),
		entry({ event: 'null', level: NULL })
	];

	it.each([
		['error', ['e']],
		['warning', ['w']],
		['info', ['i']],
		['debug', ['d']],
		['all', ['i', 'w', 'e', 'c', 'd', 'null']]
	])('matches %s case-insensitively, and a null level shows only under All', async (key, expected) => {
		renderComponent(LogView, { props: { entries: LEVELS } });
		await fireEvent.click(screen.getByTestId(`job-log-level-${key}`));
		expect(shown()).toEqual(expected);
	});

	it('marks only the chosen level segment aria-checked', async () => {
		renderComponent(LogView, { props: { entries: LEVELS } });
		const keys = ['all', 'error', 'warning', 'info', 'debug'];
		for (const chosen of keys) {
			await fireEvent.click(screen.getByTestId(`job-log-level-${chosen}`));
			for (const key of keys) {
				expect(screen.getByTestId(`job-log-level-${key}`)).toHaveAttribute('aria-checked', String(key === chosen));
			}
		}
	});
});

describe('LogView text filter', () => {
	it('needs a line to pass the service, level and text filters together', async () => {
		const entries = [
			entry({ event: 'disk full', service: 'arm-ripper-1', level: 'error' }),
			entry({ event: 'disk full', service: 'arm-backend', level: 'error' }),
			entry({ event: 'disk full', service: 'arm-ripper-1', level: 'info' }),
			entry({ event: 'tray open', service: 'arm-ripper-1', level: 'error' })
		];
		renderComponent(LogView, { props: { entries, search: true } });
		await fireEvent.click(screen.getByTestId('job-log-filter-ripper'));
		await fireEvent.click(screen.getByTestId('job-log-level-error'));
		await fireEvent.input(screen.getByTestId('job-log-search'), { target: { value: 'disk' } });
		expect(shown()).toEqual(['disk full']);
		expect(screen.getByTestId('job-log-count')).toHaveTextContent('Showing 1 of 4 lines');
	});

	it('matches event and logger joined by a space, never a line with neither', async () => {
		const entries = [
			entry({ event: 'alpha', logger: 'beta' }),
			entry({ event: 'alpha', logger: NULL }),
			entry({ event: NULL, logger: 'beta' }),
			entry({ event: NULL, logger: NULL })
		];
		renderComponent(LogView, { props: { entries, search: true } });
		const search = screen.getByTestId('job-log-search');

		await fireEvent.input(search, { target: { value: 'alpha beta' } });
		expect(screen.getAllByTestId('job-log-line')).toHaveLength(1);

		await fireEvent.input(search, { target: { value: 'alpha' } });
		expect(screen.getAllByTestId('job-log-line')).toHaveLength(2);

		await fireEvent.input(search, { target: { value: 'beta' } });
		expect(screen.getAllByTestId('job-log-line')).toHaveLength(2);

		await fireEvent.input(search, { target: { value: 'x' } });
		expect(screen.queryAllByTestId('job-log-line')).toHaveLength(0);
	});

	it('stops filtering by text once search is turned off', async () => {
		const { rerender } = renderComponent(LogView, { props: { entries: ENTRIES, search: true } });
		await fireEvent.input(screen.getByTestId('job-log-search'), { target: { value: 'ripper' } });
		expect(shown()).toEqual(['ripper line']);

		await rerender({ entries: ENTRIES, search: false });
		expect(shown()).toEqual(['backend line', 'ripper line', 'transcode line']);
	});
});

describe('LogView chips, tones and times', () => {
	const CHIP_BG = {
		backend: 'color-mix(in srgb, var(--color-primary) 26%, transparent)',
		ripper: 'color-mix(in srgb, var(--color-accent-1) 28%, transparent)',
		transcode: 'color-mix(in srgb, var(--color-accent-3) 22%, transparent)',
		other: 'color-mix(in srgb, var(--color-terminal-ink) 10%, transparent)'
	};
	const CHIP_TEXT = {
		backend: 'color-mix(in srgb, var(--color-primary) 45%, var(--color-terminal-ink))',
		ripper: 'color-mix(in srgb, var(--color-accent-1) 60%, var(--color-terminal-ink))',
		transcode: 'color-mix(in srgb, var(--color-accent-3) 45%, var(--color-terminal-ink))',
		other: 'color-mix(in srgb, var(--color-terminal-ink) 70%, transparent)'
	};

	it.each([
		['backend', 'arm-backend', 'Backend'],
		['ripper', 'arm-ripper-1', 'Ripper'],
		['transcode', 'arm-transcode-1', 'Transcode'],
		['other', 'nginx', 'Other']
	] as const)('gives a %s line its label and chip colours', (group, service, label) => {
		renderComponent(LogView, { props: { entries: [entry({ service })] } });
		const line = screen.getByTestId('job-log-line');
		const chip = line.querySelector<HTMLElement>('.log-view-chip')!;
		expect(line).toHaveAttribute('data-service', group);
		expect(chip).toHaveTextContent(label);
		expect(chip.style.getPropertyValue('--chip-bg')).toBe(CHIP_BG[group]);
		expect(chip.style.getPropertyValue('--chip-text')).toBe(CHIP_TEXT[group]);
	});

	it.each([
		['warning', 'warning'],
		['WARNING', 'warning'],
		['error', 'danger'],
		['Error', 'danger'],
		['critical', 'danger'],
		['CRITICAL', 'danger'],
		['debug', 'debug'],
		['Debug', 'debug']
	])('tones a %s line %s', (level, tone) => {
		renderComponent(LogView, { props: { entries: [entry({ level, event: 'x' })] } });
		expect(screen.getByText('x')).toHaveAttribute('data-tone', tone);
	});

	it.each([['info'], ['Info'], [NULL], ['trace']])('gives a %s line no tone', (level) => {
		renderComponent(LogView, { props: { entries: [entry({ level, event: 'x' })] } });
		expect(screen.getByText('x')).not.toHaveAttribute('data-tone');
	});

	it.each([
		['a valid timestamp', '2026-09-05T10:00:00Z', timeOf('2026-09-05T10:00:00Z')],
		['a null timestamp', null, ''],
		['an empty timestamp', '', ''],
		['an unparseable timestamp', 'not a date', '']
	])('shows the time column for %s', (_name, timestamp, expected) => {
		renderComponent(LogView, { props: { entries: [entry({ timestamp })] } });
		const time = screen.getByTestId('job-log-line').querySelector('.log-view-time')!;
		expect(time.textContent).toBe(expected);
		expect(time.textContent).not.toMatch(/AM|PM/i);
	});
});

describe('LogView follow label', () => {
	it('says one new line, singular, while paused', async () => {
		const { rerender } = renderComponent(LogView, { props: { entries: ENTRIES } });
		await scrollTo(screen.getByTestId('job-log-view'), 0);
		expect(screen.getByTestId('job-log-follow')).toHaveTextContent(/^Paused$/);

		await rerender({ entries: [...ENTRIES, entry({ event: 'late' })] });
		expect(screen.getByTestId('job-log-follow')).toHaveTextContent('Paused · 1 new line');
		expect(screen.getByTestId('job-log-follow')).not.toHaveTextContent('lines');
	});
});

describe('LogView copy', () => {
	it('writes one line per shown line, with an empty event as nothing', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		stubClipboard(writeText);
		const entries = [
			entry({ event: 'one', timestamp: '2026-09-05T10:00:00Z', service: 'arm-backend' }),
			entry({ event: NULL, timestamp: '2026-09-05T10:00:01Z', service: 'arm-ripper-1' }),
			entry({ event: 'three', timestamp: null, service: 'nginx' }),
			entry({ event: 'hidden', timestamp: '2026-09-05T10:00:03Z', service: 'arm-transcode-1' })
		];
		renderComponent(LogView, { props: { entries } });
		await fireEvent.click(screen.getByTestId('job-log-filter-all'));
		await fireEvent.click(screen.getByTestId('job-log-copy'));
		expect(writeText).toHaveBeenLastCalledWith(
			[
				`${timeOf('2026-09-05T10:00:00Z')} [Backend] one`,
				`${timeOf('2026-09-05T10:00:01Z')} [Ripper] `,
				' [Other] three',
				`${timeOf('2026-09-05T10:00:03Z')} [Transcode] hidden`
			].join('\n')
		);

		await fireEvent.click(screen.getByTestId('job-log-filter-backend'));
		await fireEvent.click(screen.getByTestId('job-log-copy'));
		expect(writeText).toHaveBeenLastCalledWith(`${timeOf('2026-09-05T10:00:00Z')} [Backend] one`);
	});

	it('shows Copied once the write resolves and Copy again 1500 ms later', async () => {
		vi.useFakeTimers();
		stubClipboard(vi.fn().mockResolvedValue(undefined));
		renderComponent(LogView, { props: { entries: ENTRIES } });
		const copy = screen.getByTestId('job-log-copy');
		expect(copy).toHaveTextContent('Copy');

		await fireEvent.click(copy);
		await vi.advanceTimersByTimeAsync(0);
		await tick();
		expect(copy).toHaveTextContent('Copied');

		await vi.advanceTimersByTimeAsync(1499);
		await tick();
		expect(copy).toHaveTextContent('Copied');

		await vi.advanceTimersByTimeAsync(1);
		await tick();
		expect(copy).toHaveTextContent(/^\s*Copy\s*$/);
	});

	it('restarts the 1500 ms when a second copy lands inside it', async () => {
		vi.useFakeTimers();
		stubClipboard(vi.fn().mockResolvedValue(undefined));
		renderComponent(LogView, { props: { entries: ENTRIES } });
		const copy = screen.getByTestId('job-log-copy');

		await fireEvent.click(copy);
		await vi.advanceTimersByTimeAsync(1000);
		await fireEvent.click(copy);
		await vi.advanceTimersByTimeAsync(1000);
		await tick();
		expect(copy).toHaveTextContent('Copied');

		await vi.advanceTimersByTimeAsync(500);
		await tick();
		expect(copy).toHaveTextContent(/^\s*Copy\s*$/);
	});

	it('leaves the label at Copy when the write is rejected, and throws nothing', async () => {
		vi.useFakeTimers();
		stubClipboard(vi.fn().mockRejectedValue(new Error('denied')));
		renderComponent(LogView, { props: { entries: ENTRIES } });
		const copy = screen.getByTestId('job-log-copy');

		await fireEvent.click(copy);
		await vi.advanceTimersByTimeAsync(2000);
		await tick();
		expect(copy).toHaveTextContent(/^\s*Copy\s*$/);
	});

	it('leaves the label at Copy when there is no clipboard', async () => {
		Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
		renderComponent(LogView, { props: { entries: ENTRIES } });
		const copy = screen.getByTestId('job-log-copy');

		await fireEvent.click(copy);
		await tick();
		expect(copy).toHaveTextContent(/^\s*Copy\s*$/);
	});

	it('leaves the label at Copy when navigator itself is undefined', async () => {
		renderComponent(LogView, { props: { entries: ENTRIES } });
		const copy = screen.getByTestId('job-log-copy');
		vi.stubGlobal('navigator', undefined);

		await fireEvent.click(copy);
		await tick();
		expect(copy).toHaveTextContent(/^\s*Copy\s*$/);
	});
});

describe('LogView follow and pause', () => {
	it('resumes following within 24px of the bottom and pauses at 24px or more', async () => {
		renderComponent(LogView, { props: { entries: ENTRIES } });
		const view = screen.getByTestId('job-log-view');
		const follow = screen.getByTestId('job-log-follow');

		// scrollHeight 1000, clientHeight 200: distance = 800 - scrollTop
		await scrollTo(view, 776);
		expect(follow).toHaveTextContent('Paused');
		expect(screen.getByTestId('job-log-jump')).toBeInTheDocument();

		await scrollTo(view, 777);
		expect(follow).toHaveTextContent('Following');
		expect(screen.queryByTestId('job-log-jump')).not.toBeInTheDocument();

		await scrollTo(view, 0);
		expect(follow).toHaveTextContent('Paused');
	});

	it('scrolls the terminal to the bottom for each new line while following', async () => {
		const { rerender } = renderComponent(LogView, { props: { entries: ENTRIES } });
		const view = screen.getByTestId('job-log-view');
		setScroll(view, 0);

		await rerender({ entries: [...ENTRIES, entry({ event: 'late' })] });
		expect(view.scrollTop).toBe(1000);
		expect(screen.getByTestId('job-log-follow')).toHaveTextContent('Following');
	});

	it('counts new lines while paused, and a filter change alone adds none', async () => {
		const { rerender } = renderComponent(LogView, { props: { entries: ENTRIES } });
		const view = screen.getByTestId('job-log-view');
		await scrollTo(view, 0);

		await fireEvent.click(screen.getByTestId('job-log-filter-ripper'));
		expect(screen.getByTestId('job-log-follow')).toHaveTextContent(/^Paused$/);
		await fireEvent.click(screen.getByTestId('job-log-filter-all'));
		expect(screen.getByTestId('job-log-follow')).toHaveTextContent(/^Paused$/);
		expect(view.scrollTop).toBe(0);

		await rerender({ entries: [...ENTRIES, entry({ event: 'late' })] });
		expect(screen.getByTestId('job-log-follow')).toHaveTextContent('Paused · 1 new line');
		expect(view.scrollTop).toBe(0);
	});

	it('shows Jump to latest only while paused, and clicking it follows and scrolls to the bottom', async () => {
		renderComponent(LogView, { props: { entries: ENTRIES } });
		const view = screen.getByTestId('job-log-view');
		expect(screen.queryByTestId('job-log-jump')).not.toBeInTheDocument();

		await scrollTo(view, 0);
		await fireEvent.click(screen.getByTestId('job-log-jump'));

		expect(view.scrollTop).toBe(1000);
		expect(screen.queryByTestId('job-log-jump')).not.toBeInTheDocument();
		expect(screen.getByTestId('job-log-follow')).toHaveTextContent('Following');
	});

	it('keeps the new-line count at 0 when it expands while following', async () => {
		const header = textSnippet('Log title');
		const { rerender } = renderComponent(LogView, { props: { entries: ENTRIES, header } });

		await rerender({ entries: ENTRIES, header, collapsed: true });
		await rerender({ entries: ENTRIES, header, collapsed: false });

		expect(screen.getByTestId('job-log-follow')).toHaveTextContent(/^Following$/);
		expect(screen.queryByTestId('job-log-jump')).not.toBeInTheDocument();
	});

	it('starts following when it first renders expanded after being collapsed', async () => {
		const header = textSnippet('Log title');
		const { rerender } = renderComponent(LogView, { props: { entries: ENTRIES, header, collapsed: true } });

		await rerender({ entries: ENTRIES, header, collapsed: false });
		expect(screen.getByTestId('job-log-follow')).toHaveTextContent(/^Following$/);
	});

	it('counts only the growth past the lowest appended seen while paused', async () => {
		const { rerender } = renderComponent(LogView, { props: { entries: ENTRIES, appended: 8 } });
		await scrollTo(screen.getByTestId('job-log-view'), 0);
		const follow = screen.getByTestId('job-log-follow');
		expect(follow).toHaveTextContent(/^Paused$/);

		// shrinking lowers the baseline to 5 and adds nothing
		await rerender({ entries: ENTRIES, appended: 5 });
		expect(follow).toHaveTextContent(/^Paused$/);

		// growing from the lowered baseline counts 1, not 0 and not -2
		await rerender({ entries: ENTRIES, appended: 6 });
		expect(follow).toHaveTextContent('Paused · 1 new line');
	});
});

describe('LogView "/" key', () => {
	/** Put an element inside the frame and focus it. */
	function addInFrame<T extends HTMLElement>(el: T): T {
		el.tabIndex = 0;
		screen.getByTestId('log-view').appendChild(el);
		el.focus();
		return el;
	}

	it('focuses the search and prevents the default when focus is inside the frame', async () => {
		renderComponent(LogView, { props: { entries: ENTRIES, search: true } });
		const filter = screen.getByTestId('job-log-filter-all');
		filter.focus();

		const notPrevented = await fireEvent.keyDown(filter, { key: '/' });
		expect(notPrevented).toBe(false);
		expect(document.activeElement).toBe(screen.getByTestId('job-log-search'));
	});

	it('does nothing when "/" is typed in an input', async () => {
		renderComponent(LogView, { props: { entries: ENTRIES, search: true } });
		const input = addInFrame(document.createElement('input'));

		const notPrevented = await fireEvent.keyDown(input, { key: '/' });
		expect(notPrevented).toBe(true);
		expect(document.activeElement).toBe(input);
	});

	it('does nothing when "/" is typed in a textarea', async () => {
		renderComponent(LogView, { props: { entries: ENTRIES, search: true } });
		const area = addInFrame(document.createElement('textarea'));

		const notPrevented = await fireEvent.keyDown(area, { key: '/' });
		expect(notPrevented).toBe(true);
		expect(document.activeElement).toBe(area);
	});

	it('does nothing when "/" is typed in a contentEditable element', async () => {
		renderComponent(LogView, { props: { entries: ENTRIES, search: true } });
		const editable = document.createElement('div');
		editable.contentEditable = 'true';
		// jsdom leaves isContentEditable undefined, so report it as a browser does
		Object.defineProperty(editable, 'isContentEditable', { value: true });
		addInFrame(editable);

		const notPrevented = await fireEvent.keyDown(editable, { key: '/' });
		expect(notPrevented).toBe(true);
		expect(document.activeElement).toBe(editable);
	});

	it('does nothing when focus is outside the frame', async () => {
		renderComponent(LogView, { props: { entries: ENTRIES, search: true } });
		const outside = document.createElement('button');
		document.body.appendChild(outside);
		outside.focus();

		const notPrevented = await fireEvent.keyDown(screen.getByTestId('job-log-filter-all'), { key: '/' });
		outside.remove();
		expect(notPrevented).toBe(true);
		expect(document.activeElement).not.toBe(screen.getByTestId('job-log-search'));
	});

	it('does nothing when search is off', async () => {
		renderComponent(LogView, { props: { entries: ENTRIES, search: false } });
		const filter = screen.getByTestId('job-log-filter-all');
		filter.focus();

		const notPrevented = await fireEvent.keyDown(filter, { key: '/' });
		expect(notPrevented).toBe(true);
		expect(document.activeElement).toBe(filter);
	});

	it('does nothing when collapsed', async () => {
		const header = createRawSnippet(() => ({ render: () => '<button data-testid="in-title">t</button>' }));
		renderComponent(LogView, { props: { entries: ENTRIES, search: true, collapsed: true, header } });
		const inTitle = screen.getByTestId('in-title');
		inTitle.focus();

		const notPrevented = await fireEvent.keyDown(inTitle, { key: '/' });
		expect(notPrevented).toBe(true);
		expect(document.activeElement).toBe(inTitle);
	});

	it('does nothing for another key', async () => {
		renderComponent(LogView, { props: { entries: ENTRIES, search: true } });
		const filter = screen.getByTestId('job-log-filter-all');
		filter.focus();

		const notPrevented = await fireEvent.keyDown(filter, { key: 'a' });
		expect(notPrevented).toBe(true);
		expect(document.activeElement).toBe(filter);
	});
});
