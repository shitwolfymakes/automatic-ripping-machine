import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/testing/render';
import type { Catalog } from '$lib/types/notifications';
import type { SetupView } from '$lib/types/api.gen';

// Pins what NotificationsStep's commit() does with the real ChannelQuickAdd.
// Only the I/O boundary is faked: the channels and settings api modules.
// One branch cannot be reached from the rendered step, so nothing here forces
// it: commit's `if (!quick) return 'skip'`, since `bind:this` sets `quick` at
// mount, before the wizard can call commit.

const catalog: Catalog = {
	featured: ['ntfy'],
	services: [{ id: 'ntfy', name: 'ntfy', docs_url: '', url_scheme: 'ntfy', required_fields: [], advanced_fields: [] }]
};
const eventTypes = [{ key: 'rip.completed', label: 'Rip completed' }];
const createChannel = vi.fn((b: unknown) => Promise.resolve({ id: 1, ...(b as object) }));
vi.mock('$lib/api/channels', () => ({
	fetchServices: () => Promise.resolve(catalog),
	fetchEventTypes: () => Promise.resolve(eventTypes),
	fetchScripts: () => Promise.resolve([]),
	createChannel: (b: unknown) => createChannel(b),
	testConfig: () => Promise.resolve({ ok: true })
}));
vi.mock('$lib/api/settings', () => ({ saveArmConfig: () => Promise.resolve({ success: true }) }));

import NotificationsStep from '../NotificationsStep.svelte';

type Step = { commit(): Promise<'done' | 'skip' | false> };

const view = { completed_at: null, progress: {}, current_step: 'notifications' } as unknown as SetupView;

function renderStep(): Step {
	const { component } = renderComponent(NotificationsStep, { props: { view } });
	return component as unknown as Step;
}

async function pickNtfy() {
	await fireEvent.click(await screen.findByRole('button', { name: /select a service/i }));
	await fireEvent.click(screen.getAllByRole('button', { name: /ntfy/ })[0]);
}

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('NotificationsStep commit', () => {
	it('is done once a channel is created', async () => {
		const step = renderStep();
		await pickNtfy();
		expect(await step.commit()).toBe('done');
		expect(createChannel).toHaveBeenCalledTimes(1);
	});

	it('skips when no service is picked', async () => {
		const step = renderStep();
		await screen.findByRole('button', { name: /select a service/i });
		expect(await step.commit()).toBe('skip');
		expect(createChannel).not.toHaveBeenCalled();
	});

	it('stays on the step and shows why when adding the channel fails, and clears it on a retry', async () => {
		createChannel.mockRejectedValueOnce(new Error('channel rejected'));
		const step = renderStep();
		await pickNtfy();
		expect(await step.commit()).toBe(false);
		expect(await screen.findByRole('alert')).toHaveTextContent('channel rejected');
		expect(await step.commit()).toBe('done');
		await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
	});
});
