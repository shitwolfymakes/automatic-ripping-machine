import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/testing/render';
import type { Catalog } from '$lib/types/notifications';

// Branch pins for ChannelQuickAdd. One branch cannot be reached from the
// rendered component, so nothing here forces it:
// - sendTest's `body.subscribed_events[0] ?? 'rip.completed'` fallback, the
//   `?? 'rip.completed'` half: the compact form's Send test is disabled until
//   the form is ready, and a ready form has at least one event, so
//   subscribed_events is never empty when sendTest runs.

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
const fetchServices = vi.fn(() => Promise.resolve(catalog));
const fetchEventTypes = vi.fn(() => Promise.resolve(eventTypes));
vi.mock('$lib/api/channels', () => ({
	fetchServices: () => fetchServices(),
	fetchEventTypes: () => fetchEventTypes(),
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

	it('shows the Error message in an alert, and no form, when the services fetch rejects', async () => {
		fetchServices.mockRejectedValueOnce(new Error('services down'));
		renderComponent(ChannelQuickAdd);
		expect(await screen.findByRole('alert')).toHaveTextContent('services down');
		expect(screen.queryByRole('button', { name: /select a service/i })).not.toBeInTheDocument();
	});

	it('shows the event types Error message in an alert when the event types fetch rejects', async () => {
		fetchEventTypes.mockRejectedValueOnce(new Error('events down'));
		renderComponent(ChannelQuickAdd);
		expect(await screen.findByRole('alert')).toHaveTextContent('events down');
		expect(screen.queryByRole('button', { name: /select a service/i })).not.toBeInTheDocument();
	});

	it('shows a generic load message when a fetch rejects with something that is not an Error', async () => {
		fetchServices.mockRejectedValueOnce('nope');
		renderComponent(ChannelQuickAdd);
		expect(await screen.findByRole('alert')).toHaveTextContent('Could not load the notification services.');
	});

	it('Send test that fails with no error says the test did not arrive, with no message line', async () => {
		testConfig.mockResolvedValueOnce({ ok: false } as never);
		renderComponent(ChannelQuickAdd);
		await pickNtfy();
		await fireEvent.click(screen.getByRole('button', { name: /send test/i }));
		await waitFor(() => expect(screen.getByText("The test didn't arrive")).toBeInTheDocument());
		expect(screen.getByRole('status')).toHaveTextContent(/^\s*The test didn't arrive\s*$/);
	});

	it('Send test that rejects with an Error shows its message under the title', async () => {
		testConfig.mockRejectedValueOnce(new Error('network down'));
		renderComponent(ChannelQuickAdd);
		await pickNtfy();
		await fireEvent.click(screen.getByRole('button', { name: /send test/i }));
		await waitFor(() => expect(screen.getByText("The test didn't arrive")).toBeInTheDocument());
		expect(screen.getByText('network down')).toBeInTheDocument();
	});

	it('Send test that rejects with something that is not an Error shows no message line', async () => {
		testConfig.mockRejectedValueOnce('boom');
		renderComponent(ChannelQuickAdd);
		await pickNtfy();
		await fireEvent.click(screen.getByRole('button', { name: /send test/i }));
		await waitFor(() => expect(screen.getByText("The test didn't arrive")).toBeInTheDocument());
		expect(screen.queryByText('boom')).not.toBeInTheDocument();
	});

	it('save() with a service picked but every event unticked throws and saves nothing', async () => {
		const { component } = renderComponent(ChannelQuickAdd);
		await pickNtfy();
		await fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
		await expect((component as unknown as QuickAdd).save()).rejects.toThrow(
			'Fill in the service fields first, or skip this step.'
		);
		expect(saveArmConfig).not.toHaveBeenCalled();
		expect(createChannel).not.toHaveBeenCalled();
	});
});
