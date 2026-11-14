// Branch pins for NotificationsTab, beside NotificationsTab.svelte.test.ts:
// load failures, the filter counts, add / toggle / save / delete failures, and
// every test-send path with its fallbacks. Two branches cannot be reached from
// the rendered tab, so nothing here forces them:
// - serviceNameFor's `c.type` arm: ChannelRow reads `serviceName` only for an
//   apprise row, and Svelte reads a prop only when the child uses it, so the
//   function never runs for a webhook or bash channel.
// - the delete dialog message's `: ''`: ConfirmDialog reads `message` only
//   while it is open, and it is open only while there is a delete target.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, waitFor, cleanup, within } from '$lib/testing/render';
import NotificationsTab from '../NotificationsTab.svelte';
import * as api from '$lib/api/channels';
import { toasts, dismissToast } from '$lib/stores/toast.svelte';
import type { Channel } from '$lib/types/notifications';
import { discordCatalog, appriseChannel, webhookChannel } from '../../../__fixtures__/apprise-fixtures';

const mockEventTypes = [
	{
		key: 'rip.completed',
		label: 'Rip completed',
		variables: [
			'job_title',
			'drive_id',
			'tracks_done',
			'tracks_total',
			'status',
			'job_id',
			'event_type',
			'occurred_at'
		],
		default_title: 'ARM: rip completed - {job_title}',
		default_body: '{job_title} finished ripping on drive {drive_id} ({tracks_done}/{tracks_total} tracks).'
	},
	{
		key: 'session.started',
		label: 'Session started',
		variables: ['session_id', 'drive_id', 'occurred_at'],
		default_title: 'ARM: session started',
		default_body: 'A new ripping session started on drive {drive_id}.'
	}
];

const sessionFirstEventTypes = [mockEventTypes[1], mockEventTypes[0]];

const storedFields = { webhook_id: '<hidden>', webhook_token: '<hidden>', thread: '5' };

function fieldsApprise(overrides: Partial<Channel> = {}): Channel {
	return appriseChannel({
		config: { type: 'apprise', url: 'discord://1/2', service_id: 'discord', fields: storedFields },
		...overrides
	});
}

function setChannels(channels: Channel[], eventTypes = mockEventTypes) {
	vi.spyOn(api, 'fetchChannels').mockResolvedValue(channels);
	vi.spyOn(api, 'fetchServices').mockResolvedValue(discordCatalog);
	vi.spyOn(api, 'fetchEventTypes').mockResolvedValue(eventTypes);
}

async function renderLoaded(channels: Channel[], eventTypes = mockEventTypes) {
	setChannels(channels, eventTypes);
	renderComponent(NotificationsTab);
	await screen.findByText(channels[0].name);
}

function toastTitled(title: string) {
	return toasts.value.find((t) => t.title === title);
}

async function expectToast(title: string, body?: string) {
	await waitFor(() => expect(toastTitled(title)).toBeDefined());
	if (body !== undefined) expect(toastTitled(title)?.body).toBe(body);
}

async function expandRow(name: string) {
	await fireEvent.click(screen.getByText(name));
}

async function clickEditorSendTest() {
	const buttons = await screen.findAllByRole('button', { name: /send test/i });
	await fireEvent.click(buttons.find((b) => b.textContent?.toLowerCase().includes('send test'))!);
}

async function dirtyThreadField() {
	const adv = (await screen.findByText(/Advanced \(/)).closest('details') as HTMLDetailsElement;
	adv.open = true;
	await fireEvent.input(await screen.findByLabelText(/Thread/i), { target: { value: '9' } });
}

async function openAddForm() {
	await fireEvent.click(await screen.findByRole('button', { name: /add your first channel/i }));
}

async function clickAddFormSendTest() {
	const form = document.querySelector('.add-channel-form') as HTMLElement;
	await fireEvent.click(within(form).getByRole('button', { name: 'Send test' }));
}

async function fillWebhookAddForm() {
	await fireEvent.click(screen.getByLabelText('Webhook'));
	await fireEvent.input(screen.getByLabelText('Channel Label'), { target: { value: 'New' } });
	await fireEvent.input(screen.getByLabelText(/Webhook URL/i), { target: { value: 'https://new' } });
	await fireEvent.click(screen.getByLabelText('Rip completed'));
}

async function openDeleteDialog(name: string) {
	await expandRow(name);
	await fireEvent.click(await screen.findByRole('button', { name: 'Delete' }));
	return within(await screen.findByRole('dialog'));
}

describe('NotificationsTab branches', () => {
	beforeEach(() => {
		setChannels([]);
	});
	afterEach(() => {
		for (const t of toasts.value) dismissToast(t.id);
		vi.restoreAllMocks();
		cleanup();
	});

	describe('load', () => {
		it('shows the Error message in the alert and no channel list when the fetch rejects', async () => {
			vi.spyOn(api, 'fetchChannels').mockRejectedValue(new Error('backend down'));
			renderComponent(NotificationsTab);
			expect(await screen.findByText('backend down')).toBeInTheDocument();
			expect(screen.queryByText('Channel')).not.toBeInTheDocument();
		});

		it('falls back to "Failed to load channels" when the rejection is not an Error', async () => {
			vi.spyOn(api, 'fetchChannels').mockRejectedValue('nope');
			renderComponent(NotificationsTab);
			expect(await screen.findByText('Failed to load channels')).toBeInTheDocument();
		});
	});

	describe('counts and filters', () => {
		const rows = () => [
			webhookChannel({ id: 1, name: 'Alpha' }),
			webhookChannel({ id: 2, name: 'Bravo', enabled: false }),
			webhookChannel({ id: 3, name: 'Charlie', last_error: 'bad url' })
		];

		it('shows each pill count', async () => {
			await renderLoaded(rows());
			expect(screen.getByRole('button', { name: 'All | 3' })).toBeInTheDocument();
			expect(screen.getByRole('button', { name: 'Enabled | 2' })).toBeInTheDocument();
			expect(screen.getByRole('button', { name: 'Paused | 1' })).toBeInTheDocument();
			expect(screen.getByRole('button', { name: 'Issues | 1' })).toBeInTheDocument();
		});

		it('selecting Enabled, Paused, Issues and All shows the matching rows', async () => {
			await renderLoaded(rows());
			const names = () => ['Alpha', 'Bravo', 'Charlie'].filter((n) => screen.queryByText(n));

			await fireEvent.click(screen.getByRole('button', { name: 'Enabled | 2' }));
			expect(names()).toEqual(['Alpha', 'Charlie']);
			await fireEvent.click(screen.getByRole('button', { name: 'Paused | 1' }));
			expect(names()).toEqual(['Bravo']);
			await fireEvent.click(screen.getByRole('button', { name: 'Issues | 1' }));
			expect(names()).toEqual(['Charlie']);
			await fireEvent.click(screen.getByRole('button', { name: 'All | 3' }));
			expect(names()).toEqual(['Alpha', 'Bravo', 'Charlie']);
		});

		it('with no channels shows the empty state whose button opens the add form', async () => {
			renderComponent(NotificationsTab);
			expect(await screen.findByText('No notification channels yet')).toBeInTheDocument();
			await openAddForm();
			expect(screen.getByText('Add notification channel')).toBeInTheDocument();
			expect(screen.queryByText('No notification channels yet')).not.toBeInTheDocument();
		});

		it('the add form cancel closes it', async () => {
			renderComponent(NotificationsTab);
			await openAddForm();
			await fireEvent.click(screen.getAllByRole('button', { name: /cancel/i })[0]);
			expect(screen.queryByText('Add notification channel')).not.toBeInTheDocument();
			expect(screen.getByText('No notification channels yet')).toBeInTheDocument();
		});
	});

	describe('handleAdd', () => {
		it('toasts "Add failed" with the Error message', async () => {
			vi.spyOn(api, 'createChannel').mockRejectedValue(new Error('dupe name'));
			renderComponent(NotificationsTab);
			await openAddForm();
			await fillWebhookAddForm();
			await fireEvent.click(screen.getByRole('button', { name: /save channel/i }));
			await expectToast('Add failed', 'dupe name');
		});

		it('toasts "Add failed" with "Unknown error" when the rejection is not an Error', async () => {
			vi.spyOn(api, 'createChannel').mockRejectedValue('nope');
			renderComponent(NotificationsTab);
			await openAddForm();
			await fillWebhookAddForm();
			await fireEvent.click(screen.getByRole('button', { name: /save channel/i }));
			await expectToast('Add failed', 'Unknown error');
		});
	});

	describe('handleToggle', () => {
		it('pausing an enabled channel toasts "Paused <name>"', async () => {
			vi.spyOn(api, 'updateChannel').mockResolvedValue(webhookChannel({ enabled: false }));
			await renderLoaded([webhookChannel()]);
			await fireEvent.click(screen.getByRole('switch', { name: /enabled/i }));
			await expectToast('Paused Hook');
		});

		it('enabling a paused channel toasts "Enabled <name>"', async () => {
			vi.spyOn(api, 'updateChannel').mockResolvedValue(webhookChannel());
			await renderLoaded([webhookChannel({ enabled: false })]);
			await fireEvent.click(screen.getByRole('switch', { name: /enabled/i }));
			await expectToast('Enabled Hook');
		});

		it('leaves the other channel as it was on toggle and on the revert after a failure', async () => {
			vi.spyOn(api, 'updateChannel').mockRejectedValue(new Error('nope'));
			await renderLoaded([
				webhookChannel({ id: 1, name: 'Alpha' }),
				webhookChannel({ id: 2, name: 'Bravo', enabled: false })
			]);
			const [first, second] = screen.getAllByRole('switch');
			await fireEvent.click(first);
			await expectToast('Update failed', 'Alpha');
			expect(first.getAttribute('aria-checked')).toBe('true');
			expect(second.getAttribute('aria-checked')).toBe('false');
		});
	});

	describe('handleEditorSave', () => {
		it('sends the edited webhook config as config', async () => {
			const update = vi.spyOn(api, 'updateChannel').mockResolvedValue(webhookChannel({ name: 'Hook2' }));
			await renderLoaded([webhookChannel()]);
			await expandRow('Hook');
			await fireEvent.input(screen.getByLabelText('Channel Label'), { target: { value: 'Hook2' } });
			await fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
			await waitFor(() => expect(update).toHaveBeenCalled());
			expect(update.mock.calls[0][1]).toMatchObject({ name: 'Hook2', config: { type: 'webhook', url: 'https://x' } });
			await expectToast('Saved.');
		});

		it('omits config for an apprise channel whose stored config has no fields', async () => {
			const noFields = appriseChannel({
				config: { type: 'apprise', url: 'discord://1/2', service_id: 'discord' } as Channel['config']
			});
			const update = vi.spyOn(api, 'updateChannel').mockResolvedValue(noFields);
			await renderLoaded([noFields]);
			await expandRow('D');
			await fireEvent.click(screen.getByLabelText('Rip completed'));
			await fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
			await waitFor(() => expect(update).toHaveBeenCalled());
			expect(update.mock.calls[0][1]).not.toHaveProperty('config');
		});

		it('leaves the other channel as it was after a save', async () => {
			const update = vi.spyOn(api, 'updateChannel').mockResolvedValue(webhookChannel({ id: 1, name: 'Alpha2' }));
			await renderLoaded([webhookChannel({ id: 1, name: 'Alpha' }), webhookChannel({ id: 2, name: 'Bravo' })]);
			await expandRow('Alpha');
			await fireEvent.input(screen.getByLabelText('Channel Label'), { target: { value: 'Alpha2' } });
			await fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
			await waitFor(() => expect(update).toHaveBeenCalled());
			expect(await screen.findByText('Alpha2')).toBeInTheDocument();
			expect(screen.getByText('Bravo')).toBeInTheDocument();
		});

		it('toasts "Save failed" with the Error message', async () => {
			vi.spyOn(api, 'updateChannel').mockRejectedValue(new Error('conflict'));
			await renderLoaded([webhookChannel()]);
			await expandRow('Hook');
			await fireEvent.input(screen.getByLabelText('Channel Label'), { target: { value: 'Hook2' } });
			await fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
			await expectToast('Save failed', 'conflict');
		});

		it('toasts "Save failed" with an empty body when the rejection is not an Error', async () => {
			vi.spyOn(api, 'updateChannel').mockRejectedValue('nope');
			await renderLoaded([webhookChannel()]);
			await expandRow('Hook');
			await fireEvent.input(screen.getByLabelText('Channel Label'), { target: { value: 'Hook2' } });
			await fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
			await expectToast('Save failed', '');
		});
	});

	describe('saved channel test send', () => {
		it('sends the first event type key when the channel has no subscribed events', async () => {
			const send = vi.spyOn(api, 'testSendChannel').mockResolvedValue({ ok: true, error: null });
			await renderLoaded([webhookChannel({ subscribed_events: [] })], sessionFirstEventTypes);
			await fireEvent.click(screen.getByRole('button', { name: 'Send test' }));
			await waitFor(() => expect(send).toHaveBeenCalledWith(1, 'session.started'));
		});

		it('sends rip.completed when no event types are loaded either', async () => {
			const send = vi.spyOn(api, 'testSendChannel').mockResolvedValue({ ok: true, error: null });
			await renderLoaded([webhookChannel({ subscribed_events: [] })], []);
			await fireEvent.click(screen.getByRole('button', { name: 'Send test' }));
			await waitFor(() => expect(send).toHaveBeenCalledWith(1, 'rip.completed'));
		});

		it('toasts "Test failed" with an empty body when the result has no error', async () => {
			vi.spyOn(api, 'testSendChannel').mockResolvedValue({ ok: false, error: null });
			await renderLoaded([webhookChannel()]);
			await fireEvent.click(screen.getByRole('button', { name: 'Send test' }));
			await expectToast('Test failed', '');
		});

		it('toasts "Test failed" with the Error message when the call rejects', async () => {
			vi.spyOn(api, 'testSendChannel').mockRejectedValue(new Error('timeout'));
			await renderLoaded([webhookChannel()]);
			await fireEvent.click(screen.getByRole('button', { name: 'Send test' }));
			await expectToast('Test failed', 'timeout');
		});

		it('toasts "Test failed" with an empty body when the rejection is not an Error', async () => {
			vi.spyOn(api, 'testSendChannel').mockRejectedValue('nope');
			await renderLoaded([webhookChannel()]);
			await fireEvent.click(screen.getByRole('button', { name: 'Send test' }));
			await expectToast('Test failed', '');
		});
	});

	describe('handleTestUnsaved (add form Send test)', () => {
		it('toasts "Test delivered" when delivered', async () => {
			vi.spyOn(api, 'testConfig').mockResolvedValue({ ok: true, error: null });
			renderComponent(NotificationsTab);
			await openAddForm();
			await clickAddFormSendTest();
			await expectToast('Test delivered');
		});

		it('toasts "Test failed" with the error text when delivery fails with an error', async () => {
			vi.spyOn(api, 'testConfig').mockResolvedValue({ ok: false, error: 'bad token' });
			renderComponent(NotificationsTab);
			await openAddForm();
			await clickAddFormSendTest();
			await expectToast('Test failed', 'bad token');
		});

		it('toasts "Test failed" with an empty body when delivery fails without an error', async () => {
			vi.spyOn(api, 'testConfig').mockResolvedValue({ ok: false, error: null });
			renderComponent(NotificationsTab);
			await openAddForm();
			await clickAddFormSendTest();
			await expectToast('Test failed', '');
		});

		it('toasts "Test failed" with the Error message when the call rejects', async () => {
			vi.spyOn(api, 'testConfig').mockRejectedValue(new Error('offline'));
			renderComponent(NotificationsTab);
			await openAddForm();
			await clickAddFormSendTest();
			await expectToast('Test failed', 'offline');
		});

		it('toasts "Test failed" with an empty body when the rejection is not an Error', async () => {
			vi.spyOn(api, 'testConfig').mockRejectedValue('nope');
			renderComponent(NotificationsTab);
			await openAddForm();
			await clickAddFormSendTest();
			await expectToast('Test failed', '');
		});

		it('sends the first event type key when the form has no events selected', async () => {
			const send = vi.spyOn(api, 'testConfig').mockResolvedValue({ ok: true, error: null });
			setChannels([], sessionFirstEventTypes);
			renderComponent(NotificationsTab);
			await openAddForm();
			await clickAddFormSendTest();
			await waitFor(() =>
				expect(send).toHaveBeenCalledWith(expect.objectContaining({ event_type: 'session.started' }))
			);
		});

		it('sends the selected event key when the form has an event selected', async () => {
			const send = vi.spyOn(api, 'testConfig').mockResolvedValue({ ok: true, error: null });
			renderComponent(NotificationsTab);
			await openAddForm();
			await fireEvent.click(screen.getByLabelText('Session started'));
			await clickAddFormSendTest();
			await waitFor(() =>
				expect(send).toHaveBeenCalledWith(expect.objectContaining({ event_type: 'session.started' }))
			);
		});
	});

	describe('handleEditorTest', () => {
		it('apprise with dirty fields toasts "Test failed" with the error text', async () => {
			vi.spyOn(api, 'testConfig').mockResolvedValue({ ok: false, error: 'bad hook' });
			await renderLoaded([fieldsApprise()]);
			await expandRow('D');
			await dirtyThreadField();
			await clickEditorSendTest();
			await expectToast('Test failed', 'bad hook');
		});

		it('apprise with dirty fields toasts "Test failed" with an empty body when there is no error', async () => {
			vi.spyOn(api, 'testConfig').mockResolvedValue({ ok: false, error: null });
			await renderLoaded([fieldsApprise()]);
			await expandRow('D');
			await dirtyThreadField();
			await clickEditorSendTest();
			await expectToast('Test failed', '');
		});

		it('apprise with dirty fields toasts "Test delivered" when delivered', async () => {
			vi.spyOn(api, 'testConfig').mockResolvedValue({ ok: true, error: null });
			await renderLoaded([fieldsApprise()]);
			await expandRow('D');
			await dirtyThreadField();
			await clickEditorSendTest();
			await expectToast('Test delivered');
		});

		it('apprise with no events selected sends the first event type key', async () => {
			const send = vi.spyOn(api, 'testConfig').mockResolvedValue({ ok: true, error: null });
			await renderLoaded([fieldsApprise({ subscribed_events: [] })], sessionFirstEventTypes);
			await expandRow('D');
			await dirtyThreadField();
			await clickEditorSendTest();
			await waitFor(() =>
				expect(send).toHaveBeenCalledWith(expect.objectContaining({ event_type: 'session.started' }))
			);
		});

		it('webhook toasts "Test failed" when the test fails', async () => {
			vi.spyOn(api, 'testConfig').mockResolvedValue({ ok: false, error: 'refused' });
			await renderLoaded([webhookChannel()]);
			await expandRow('Hook');
			await clickEditorSendTest();
			await expectToast('Test failed', 'refused');
		});

		it('webhook toasts "Test failed" with the Error message when the call rejects', async () => {
			vi.spyOn(api, 'testConfig').mockRejectedValue(new Error('offline'));
			await renderLoaded([webhookChannel()]);
			await expandRow('Hook');
			await clickEditorSendTest();
			await expectToast('Test failed', 'offline');
		});

		it('webhook toasts "Test failed" with an empty body when the rejection is not an Error', async () => {
			vi.spyOn(api, 'testConfig').mockRejectedValue('nope');
			await renderLoaded([webhookChannel()]);
			await expandRow('Hook');
			await clickEditorSendTest();
			await expectToast('Test failed', '');
		});

		it('webhook with no events selected sends the first event type key', async () => {
			const send = vi.spyOn(api, 'testConfig').mockResolvedValue({ ok: true, error: null });
			await renderLoaded([webhookChannel({ subscribed_events: [] })], sessionFirstEventTypes);
			await expandRow('Hook');
			await clickEditorSendTest();
			await waitFor(() =>
				expect(send).toHaveBeenCalledWith(expect.objectContaining({ event_type: 'session.started' }))
			);
		});
	});

	describe('confirmDelete and the dialog', () => {
		it('Delete opens the dialog naming the channel and Cancel closes it with no call', async () => {
			const del = vi.spyOn(api, 'deleteChannel');
			await renderLoaded([webhookChannel()]);
			const dialog = await openDeleteDialog('Hook');
			expect(dialog.getByText(/Hook will be removed/)).toBeInTheDocument();
			await fireEvent.click(dialog.getByRole('button', { name: 'Cancel' }));
			await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
			expect(del).not.toHaveBeenCalled();
		});

		it('Confirm deletes the channel, collapses its editor and toasts "Deleted <name>"', async () => {
			const del = vi.spyOn(api, 'deleteChannel').mockResolvedValue(undefined);
			await renderLoaded([webhookChannel({ id: 1, name: 'Alpha' }), webhookChannel({ id: 2, name: 'Bravo' })]);
			const dialog = await openDeleteDialog('Alpha');
			await fireEvent.click(dialog.getByRole('button', { name: 'Delete' }));
			await expectToast('Deleted Alpha');
			expect(del).toHaveBeenCalledWith(1);
			await waitFor(() => expect(screen.queryByText('Alpha')).not.toBeInTheDocument());
			expect(screen.getByText('Bravo')).toBeInTheDocument();
			expect(screen.queryByRole('button', { name: 'Close' })).not.toBeInTheDocument();
		});

		it('deleting a channel other than the expanded one leaves the expanded one open', async () => {
			vi.spyOn(api, 'deleteChannel').mockResolvedValue(undefined);
			await renderLoaded([webhookChannel({ id: 1, name: 'Alpha' }), webhookChannel({ id: 2, name: 'Bravo' })]);
			const dialog = await openDeleteDialog('Alpha');
			await expandRow('Bravo');
			await fireEvent.click(dialog.getByRole('button', { name: 'Delete' }));
			await expectToast('Deleted Alpha');
			await waitFor(() => expect(screen.queryByText('Alpha')).not.toBeInTheDocument());
			expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument();
		});

		it('toasts "Delete failed" with the Error message', async () => {
			vi.spyOn(api, 'deleteChannel').mockRejectedValue(new Error('in use'));
			await renderLoaded([webhookChannel()]);
			const dialog = await openDeleteDialog('Hook');
			await fireEvent.click(dialog.getByRole('button', { name: 'Delete' }));
			await expectToast('Delete failed', 'in use');
		});

		it('toasts "Delete failed" with an empty body when the rejection is not an Error', async () => {
			vi.spyOn(api, 'deleteChannel').mockRejectedValue('nope');
			await renderLoaded([webhookChannel()]);
			const dialog = await openDeleteDialog('Hook');
			await fireEvent.click(dialog.getByRole('button', { name: 'Delete' }));
			await expectToast('Delete failed', '');
		});

		it('a double click on Confirm deletes once', async () => {
			const del = vi.spyOn(api, 'deleteChannel').mockResolvedValue(undefined);
			await renderLoaded([webhookChannel()]);
			const dialog = await openDeleteDialog('Hook');
			const confirm = dialog.getByRole('button', { name: 'Delete' });
			confirm.click();
			confirm.click();
			await expectToast('Deleted Hook');
			expect(del).toHaveBeenCalledTimes(1);
		});
	});

	describe('toggleExpand', () => {
		it('clicking an expanded row name again collapses it', async () => {
			await renderLoaded([webhookChannel()]);
			await expandRow('Hook');
			expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument();
			await expandRow('Hook');
			expect(screen.queryByRole('button', { name: 'Close' })).not.toBeInTheDocument();
		});
	});
});
