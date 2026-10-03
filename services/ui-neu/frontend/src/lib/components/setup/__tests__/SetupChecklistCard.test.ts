import { describe, it, expect, vi, afterEach } from 'vitest';
import { readable } from 'svelte/store';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';

const fetchSetup = vi.fn();
const dismissSetupChecklist = vi.fn();
vi.mock('$lib/api/setup', () => ({
	fetchSetup: () => fetchSetup(),
	dismissSetupChecklist: () => dismissSetupChecklist(),
	putSetupStep: vi.fn()
}));
vi.mock('$lib/stores/auth', () => ({ isAdmin: readable(true) }));
const gotoMock = vi.fn();
vi.mock('$app/navigation', () => ({ goto: (...a: unknown[]) => gotoMock(...a) }));

import SetupChecklistCard from '../SetupChecklistCard.svelte';

const base = { current_step: 'finish', admin_default_password: false, checklist_dismissed: false };
const allDone = Object.fromEntries(
	['account', 'system', 'drives', 'makemkv', 'metadata', 'discs', 'transcoding', 'notifications', 'finish'].map((s) => [
		s,
		{ state: 'done' }
	])
);

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('SetupChecklistCard', () => {
	it('lists skipped and needs-attention steps with a count', async () => {
		fetchSetup.mockResolvedValue({
			...base,
			completed_at: '2026-10-01T00:00:00Z',
			progress: { ...allDone, system: { state: 'attention' }, notifications: { state: 'skipped' } }
		});
		renderComponent(SetupChecklistCard);
		expect(await screen.findByTestId('setup-checklist')).toHaveTextContent('6 of 8 done');
		expect(screen.getByTestId('setup-checklist-row-system')).toHaveTextContent('Needs attention');
		expect(screen.getByRole('link', { name: /fix/i })).toHaveAttribute('href', '/setup/system');
		expect(screen.getByRole('link', { name: /set up/i })).toHaveAttribute('href', '/setup/notifications');
		expect(screen.queryByRole('button', { name: /resume setup/i })).toBeNull();
	});

	it('stays hidden when everything is done or it was dismissed', async () => {
		fetchSetup.mockResolvedValue({ ...base, completed_at: '2026-10-01T00:00:00Z', progress: allDone });
		renderComponent(SetupChecklistCard);
		await waitFor(() => expect(fetchSetup).toHaveBeenCalled());
		expect(screen.queryByTestId('setup-checklist')).toBeNull();
		cleanup();
		fetchSetup.mockResolvedValue({
			...base,
			checklist_dismissed: true,
			completed_at: '2026-10-01T00:00:00Z',
			progress: { ...allDone, system: { state: 'attention' } }
		});
		renderComponent(SetupChecklistCard);
		await waitFor(() => expect(fetchSetup).toHaveBeenCalledTimes(2));
		expect(screen.queryByTestId('setup-checklist')).toBeNull();
	});

	it('after Finish later it offers Resume setup', async () => {
		fetchSetup.mockResolvedValue({ ...base, completed_at: null, progress: { account: { state: 'done' } } });
		renderComponent(SetupChecklistCard);
		await fireEvent.click(await screen.findByRole('button', { name: /resume setup/i }));
		expect(gotoMock).toHaveBeenCalledWith('/setup');
	});

	it('dismiss hides it and tells the server', async () => {
		fetchSetup.mockResolvedValue({ ...base, completed_at: null, progress: {} });
		dismissSetupChecklist.mockResolvedValue({ ...base, completed_at: null, progress: {}, checklist_dismissed: true });
		renderComponent(SetupChecklistCard);
		await fireEvent.click(await screen.findByRole('button', { name: /dismiss setup checklist/i }));
		expect(dismissSetupChecklist).toHaveBeenCalled();
		await waitFor(() => expect(screen.queryByTestId('setup-checklist')).toBeNull());
	});
});
