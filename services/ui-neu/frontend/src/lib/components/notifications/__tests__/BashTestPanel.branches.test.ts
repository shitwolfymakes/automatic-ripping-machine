import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/testing/render';
import BashTestPanel from '../BashTestPanel.svelte';

// Branch pins for BashTestPanel, beside BashTestPanel.svelte.test.ts. The
// branches left open below cannot be reached from the rendered component:
// - The `?? {}` fallback in contextRows (`bash.preview?.env ?? {}`): the
//   markup reads contextRows only inside the `{:else if bash.preview}` block,
//   so a preview is always set there, and every preview BashPreview stores
//   (from previewBash, or failedPreview when it throws) carries an `env`
//   object.
// - The `?? ''` fallback Svelte compiles around `{e.label}` in the option
//   text (`<option value={e.key}>{e.label}{isCustomized(templates[e.key])
//   ? ...`): label is a required string on EventTypeInfo, so it is never
//   nullish.

const previewBash = vi.fn();
vi.mock('$lib/api/channels', async (orig) => ({
	...(await orig<typeof import('$lib/api/channels')>()),
	previewBash: (...a: unknown[]) => previewBash(...a)
}));

const eventTypes = [
	{ key: 'rip.completed', label: 'Rip completed', variables: ['job_title'], default_title: 't', default_body: 'b' },
	{ key: 'rip.failed', label: 'Rip failed', variables: ['job_title'], default_title: 't', default_body: 'b' }
];
const preview = {
	title: 'ARM: rip failed - The Matrix',
	body: 'failed',
	argv: ['/usr/bin/env', 'bash', '/scripts/a.sh', 'ARM: rip failed - The Matrix', 'failed'],
	inputs: { TO: 'oncall@x', SMTP_PASS: '<hidden>' },
	env: { ARM_EVENT_TYPE: 'rip.failed', TO: 'oncall@x', SMTP_PASS: '<hidden>' },
	error: null,
	result: null
};
const okResult = { ok: true, exit_code: 0, duration_ms: 1200, stdout: 'out', stderr: 'err', error: null };

type Props = Partial<{
	templates: Record<string, { title?: string; body?: string; inputs?: Record<string, string> }>;
	inputs: Array<{ key: string; label: string; required: boolean; secret: boolean; default: string; values: null }>;
	events: string[];
}>;

async function openPanel(props: Props = {}) {
	renderComponent(BashTestPanel, {
		props: {
			config: { type: 'bash', script: 'a.sh' },
			templates: {},
			events: ['rip.completed', 'rip.failed'],
			eventTypes,
			...props
		}
	});
	await fireEvent.click(screen.getByText('Test'));
}

async function openAndRun(result: unknown) {
	previewBash.mockResolvedValueOnce(preview);
	await openPanel();
	await screen.findByText('What the script will receive');
	previewBash.mockResolvedValueOnce({ ...preview, result });
	await fireEvent.click(screen.getByRole('button', { name: 'Run test' }));
}

afterEach(() => {
	cleanup();
	previewBash.mockReset();
});

describe('BashTestPanel preview failures', () => {
	it('shows the message of an Error the preview rejects with', async () => {
		previewBash.mockRejectedValue(new Error('backend is down'));
		await openPanel();
		expect(await screen.findByText('backend is down')).toBeTruthy();
	});

	it('shows "preview failed" when the preview rejects with something that is not an Error', async () => {
		previewBash.mockRejectedValue('nope');
		await openPanel();
		expect(await screen.findByText('preview failed')).toBeTruthy();
	});
});

describe('BashTestPanel incomplete input', () => {
	it('names the key itself when the inputs prop does not list it', async () => {
		previewBash.mockResolvedValue({ ...preview, inputs: {}, env: {}, error: 'input MISSING_KEY is required' });
		await openPanel();
		expect(await screen.findByText('Fill in MISSING_KEY above to preview this hook.')).toBeTruthy();
	});
});

describe('BashTestPanel runTest', () => {
	it('shows no result block and no "last run" when the run response has no result', async () => {
		previewBash.mockResolvedValue(preview);
		await openPanel();
		await screen.findByText('What the script will receive');
		await fireEvent.click(screen.getByRole('button', { name: 'Run test' }));
		await waitFor(() => expect(previewBash).toHaveBeenLastCalledWith(expect.objectContaining({ run: true })));
		await waitFor(() =>
			expect((screen.getByRole('button', { name: 'Run test' }) as HTMLButtonElement).disabled).toBe(false)
		);
		expect(screen.queryByText('Result')).toBeNull();
		expect(screen.queryByText(/last run/)).toBeNull();
	});

	it('shows the message of an Error the run rejects with, with empty stderr and stdout', async () => {
		previewBash.mockResolvedValueOnce(preview);
		await openPanel();
		await screen.findByText('What the script will receive');
		previewBash.mockRejectedValueOnce(new Error('run blew up'));
		await fireEvent.click(screen.getByRole('button', { name: 'Run test' }));
		expect(await screen.findByText('Failed after 0.0s: run blew up')).toBeTruthy();
		expect(screen.getAllByText('(empty)')).toHaveLength(2);
		expect(screen.getByText('last run: failed')).toBeTruthy();
	});

	it('shows "test failed" when the run rejects with something that is not an Error', async () => {
		previewBash.mockResolvedValueOnce(preview);
		await openPanel();
		await screen.findByText('What the script will receive');
		previewBash.mockRejectedValueOnce('nope');
		await fireEvent.click(screen.getByRole('button', { name: 'Run test' }));
		expect(await screen.findByText('Failed after 0.0s: test failed')).toBeTruthy();
	});

	it('shows "Running..." on the button while the run is in flight', async () => {
		previewBash.mockResolvedValueOnce(preview);
		await openPanel();
		await screen.findByText('What the script will receive');
		let finish: (v: unknown) => void = () => {};
		previewBash.mockReturnValueOnce(new Promise((resolve) => (finish = resolve)));
		await fireEvent.click(screen.getByRole('button', { name: 'Run test' }));
		const busy = (await screen.findByRole('button', { name: 'Running...' })) as HTMLButtonElement;
		expect(busy.disabled).toBe(true);
		finish(preview);
		expect(await screen.findByRole('button', { name: 'Run test' })).toBeTruthy();
	});
});

describe('BashTestPanel result line', () => {
	it('reports a passing run with its exit code, duration, success alert and toggle label', async () => {
		await openAndRun(okResult);
		expect(await screen.findByText('Passed: exit code 0 after 1.2s')).toBeTruthy();
		expect(screen.getByText('last run: passed')).toBeTruthy();
		expect(document.querySelector('.bash-test-panel-result.alert-success')).not.toBeNull();
		expect(screen.getByText('out')).toBeTruthy();
		expect(screen.getByText('err')).toBeTruthy();
	});

	it('leaves the error off a failing run that has an exit code', async () => {
		await openAndRun({ ...okResult, ok: false, exit_code: 2, error: 'script exit code 2' });
		expect(await screen.findByText('Failed: exit code 2 after 1.2s')).toBeTruthy();
		expect(document.querySelector('.bash-test-panel-result.alert-danger')).not.toBeNull();
	});

	it('appends the error to a failing run with no exit code', async () => {
		await openAndRun({ ...okResult, ok: false, exit_code: null, error: 'timed out' });
		expect(await screen.findByText('Failed after 1.2s: timed out')).toBeTruthy();
	});

	it('shows neither exit code nor error for a failing run with no exit code and no error', async () => {
		await openAndRun({ ...okResult, ok: false, exit_code: null, error: null });
		expect(await screen.findByText('Failed after 1.2s')).toBeTruthy();
	});
});

describe('BashTestPanel context list', () => {
	const env = Object.fromEntries(Array.from({ length: 8 }, (_, i) => [`ARM_KEY_${i + 1}`, `value-${i + 1}`]));

	it('shows six ARM_ keys, expands to all of them, and collapses again', async () => {
		previewBash.mockResolvedValue({ ...preview, env: { ...env, PLAIN_KEY: 'plain-value' } });
		await openPanel();
		expect(await screen.findByText('ARM_KEY_6')).toBeTruthy();
		expect(screen.queryByText('ARM_KEY_7')).toBeNull();
		expect(screen.queryByText('PLAIN_KEY')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'Show all 8' }));
		expect(screen.getByText('ARM_KEY_8')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: 'Show fewer' }));
		expect(screen.queryByText('ARM_KEY_7')).toBeNull();
		expect(screen.getByRole('button', { name: 'Show all 8' })).toBeTruthy();
	});
});

describe('BashTestPanel customized label', () => {
	it('marks an event whose template has only a title', async () => {
		previewBash.mockResolvedValue(preview);
		await openPanel({ templates: { 'rip.completed': { title: 'custom' } } });
		expect(await screen.findByRole('option', { name: 'Rip completed (customized)' })).toBeTruthy();
		expect(screen.getByRole('option', { name: 'Rip failed' })).toBeTruthy();
	});

	it('marks an event whose template has only a body', async () => {
		previewBash.mockResolvedValue(preview);
		await openPanel({ templates: { 'rip.completed': { body: 'custom' } } });
		expect(await screen.findByRole('option', { name: 'Rip completed (customized)' })).toBeTruthy();
	});

	it('does not mark an event whose template inputs are empty', async () => {
		previewBash.mockResolvedValue(preview);
		await openPanel({ templates: { 'rip.completed': { inputs: {} } } });
		expect(await screen.findByRole('option', { name: 'Rip completed' })).toBeTruthy();
	});
});

describe('BashTestPanel default props', () => {
	it('lists no events and previews nothing without an eventTypes prop', async () => {
		renderComponent(BashTestPanel, {
			props: { config: { type: 'bash', script: 'a.sh' }, templates: {}, events: ['rip.completed'] }
		});
		await fireEvent.click(screen.getByText('Test'));
		const select = (await screen.findByLabelText('Simulate event')) as HTMLSelectElement;
		expect(select.options).toHaveLength(0);
		await new Promise((r) => setTimeout(r, 400));
		expect(previewBash).not.toHaveBeenCalled();
	});
});
