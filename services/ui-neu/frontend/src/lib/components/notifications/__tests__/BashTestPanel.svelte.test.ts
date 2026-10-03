import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import BashTestPanel from '../BashTestPanel.svelte';

const previewBash = vi.fn();
vi.mock('$lib/api/channels', async (orig) => ({ ...(await orig<typeof import('$lib/api/channels')>()), previewBash: (...a: unknown[]) => previewBash(...a) }));

const eventTypes = [
	{ key: 'rip.completed', label: 'Rip completed', variables: ['job_title'], default_title: 't', default_body: 'b' },
	{ key: 'rip.failed', label: 'Rip failed', variables: ['job_title'], default_title: 't', default_body: 'b' }
];
const preview = {
	title: 'ARM: rip failed - The Matrix', body: 'failed', argv: ['/usr/bin/env', 'bash', '/scripts/a.sh', 'ARM: rip failed - The Matrix', 'failed'],
	inputs: { TO: 'oncall@x', SMTP_PASS: '<hidden>' }, env: { ARM_EVENT_TYPE: 'rip.failed', TO: 'oncall@x', SMTP_PASS: '<hidden>' }, error: null, result: null
};

describe('BashTestPanel', () => {
	afterEach(() => { cleanup(); previewBash.mockReset(); });

	it('previews the selected event, marks customized events, and runs the test', async () => {
		previewBash.mockResolvedValue(preview);
		renderComponent(BashTestPanel, { props: { config: { type: 'bash', script: 'a.sh', inputs: { TO: 'me@x' } }, templates: { 'rip.failed': { inputs: { TO: 'oncall@x' } } }, events: ['rip.completed', 'rip.failed'], eventTypes } });
		await fireEvent.click(screen.getByText('Test'));
		const select = (await screen.findByLabelText('Simulate event')) as HTMLSelectElement;
		expect(select.options[1].textContent).toContain('customized');
		await fireEvent.change(select, { target: { value: 'rip.failed' } });
		await waitFor(() => expect(previewBash).toHaveBeenLastCalledWith(expect.objectContaining({ event_type: 'rip.failed', run: false })));
		expect(await screen.findByText('oncall@x')).toBeTruthy();
		expect(screen.getByText('<hidden>')).toBeTruthy();
		previewBash.mockResolvedValue({ ...preview, result: { ok: false, exit_code: 67, duration_ms: 400, stdout: '', stderr: 'curl: (67) Login denied', error: 'script exit code 67: curl: (67) Login denied' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Run test' }));
		await waitFor(() => expect(previewBash).toHaveBeenLastCalledWith(expect.objectContaining({ run: true })));
		expect(await screen.findByText(/exit code 67/)).toBeTruthy();
		expect(screen.getByText(/Login denied/)).toBeTruthy();
	});

	it('turns a missing required input into a labelled hint and disables Run test', async () => {
		previewBash.mockResolvedValue({ ...preview, argv: [], inputs: {}, env: {}, error: 'input SECTION is required' });
		const inputs = [{ key: 'SECTION', label: 'Library section id', required: true, secret: false, default: '', values: null }];
		renderComponent(BashTestPanel, { props: { config: { type: 'bash', script: 'a.sh' }, templates: {}, events: ['rip.completed'], eventTypes, inputs } });
		await fireEvent.click(screen.getByText('Test'));
		expect(await screen.findByText('Fill in Library section id above to preview this hook.')).toBeTruthy();
		expect(screen.queryByText('input SECTION is required')).toBeNull();
		expect((screen.getByRole('button', { name: 'Run test' }) as HTMLButtonElement).disabled).toBe(true);
	});

	it('shows other hook errors instead of the grid', async () => {
		previewBash.mockResolvedValue({ ...preview, argv: [], inputs: {}, env: {}, error: 'script must be a file name inside the scripts directory, not a path' });
		renderComponent(BashTestPanel, { props: { config: { type: 'bash', script: 'a.sh' }, templates: {}, events: ['rip.completed'], eventTypes } });
		await fireEvent.click(screen.getByText('Test'));
		expect(await screen.findByText(/file name inside the scripts directory/)).toBeTruthy();
		expect((screen.getByRole('button', { name: 'Run test' }) as HTMLButtonElement).disabled).toBe(true);
	});
});
