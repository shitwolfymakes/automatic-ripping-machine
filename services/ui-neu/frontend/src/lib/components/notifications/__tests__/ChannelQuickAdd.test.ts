import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import type { Catalog } from '$lib/types/notifications';

const catalog: Catalog = {
	featured: ['ntfy'],
	services: [{ id: 'ntfy', name: 'ntfy', docs_url: '', url_scheme: 'ntfy', required_fields: [], advanced_fields: [] }]
};
const eventTypes = [
	{ key: 'rip.completed', label: 'Rip completed' },
	{ key: 'rip.needs_user_input', label: 'Needs your review' },
	{ key: 'rip.failed', label: 'Rip failed' }
];
const createChannel = vi.fn((b: unknown) => Promise.resolve({ id: 1, ...(b as object) }));
const testConfig = vi.fn((_b?: unknown) => Promise.resolve({ ok: true }));
vi.mock('$lib/api/channels', () => ({
	fetchServices: () => Promise.resolve(catalog),
	fetchEventTypes: () => Promise.resolve(eventTypes),
	fetchScripts: () => Promise.resolve([]),
	createChannel: (b: unknown) => createChannel(b),
	testConfig: (b: unknown) => testConfig(b)
}));
const saveArmConfig = vi.fn((_c?: unknown) => Promise.resolve({ success: true }));
vi.mock('$lib/api/settings', () => ({ saveArmConfig: (c: unknown) => saveArmConfig(c) }));

import ChannelQuickAdd from '../ChannelQuickAdd.svelte';

type QuickAdd = { save(): Promise<'created' | 'empty'> };

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

async function pickNtfy() {
	await fireEvent.click(await screen.findByRole('button', { name: /select a service/i }));
	await fireEvent.click(screen.getAllByRole('button', { name: /ntfy/ })[0]);
}

describe('ChannelQuickAdd', () => {
	it('states the inbox is always on and save() with nothing picked is empty', async () => {
		const { component } = renderComponent(ChannelQuickAdd);
		expect(screen.getByText(/always shows notifications in its own inbox/i)).toBeInTheDocument();
		await screen.findByRole('button', { name: /select a service/i });
		expect(await (component as unknown as QuickAdd).save()).toBe('empty');
		expect(createChannel).not.toHaveBeenCalled();
		expect(saveArmConfig).not.toHaveBeenCalled();
	});

	it('turns notifications on and creates the channel with the default events', async () => {
		const { component } = renderComponent(ChannelQuickAdd);
		await pickNtfy();
		expect(await (component as unknown as QuickAdd).save()).toBe('created');
		expect(saveArmConfig).toHaveBeenCalledWith({ notifications_enabled: true });
		expect(createChannel).toHaveBeenCalledWith(
			expect.objectContaining({
				type: 'apprise',
				name: 'ntfy',
				subscribed_events: ['rip.completed', 'rip.needs_user_input', 'rip.failed']
			})
		);
	});

	it('Send test reports the result inline', async () => {
		renderComponent(ChannelQuickAdd);
		await pickNtfy();
		await fireEvent.click(screen.getByRole('button', { name: /send test/i }));
		await waitFor(() => expect(screen.getByText('Test sent')).toBeInTheDocument());
		testConfig.mockResolvedValueOnce({ ok: false, error: 'topic not found' } as never);
		await fireEvent.click(screen.getByRole('button', { name: /send test/i }));
		await waitFor(() => expect(screen.getByText('topic not found')).toBeInTheDocument());
	});
});
