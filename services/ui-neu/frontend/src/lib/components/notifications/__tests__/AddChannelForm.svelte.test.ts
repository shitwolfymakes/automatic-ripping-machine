import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, waitFor, cleanup } from '$lib/test-utils';
import AddChannelForm from '../AddChannelForm.svelte';
import type { Catalog } from '$lib/types/notifications';
import type { EventTypeInfo } from '$lib/api/channels';

vi.mock('$lib/api/channels', async (orig) => ({
	...(await orig<typeof import('$lib/api/channels')>()),
	fetchScripts: vi.fn().mockResolvedValue([]),
	fetchScript: vi.fn().mockRejectedValue(new Error('no script selected')),
	previewBash: vi.fn().mockResolvedValue({ title: '', body: '', inputs: {}, env: {}, argv: [], error: null, result: null })
}));

const catalog: Catalog = {
	featured: ['discord'],
	services: [{ id: 'discord', name: 'Discord', docs_url: '', url_scheme: 'discord',
		required_fields: [{ key: 'webhook_id', label: 'Webhook ID', type: 'string', private: false, required: true }],
		advanced_fields: [] }]
};

const eventTypes: EventTypeInfo[] = [
	{
		key: 'rip.completed',
		label: 'Rip completed',
		variables: ['job_title', 'drive_id'],
		default_title: 'ARM: rip completed - {job_title}',
		default_body: '{job_title} finished ripping on drive {drive_id}.'
	},
	{
		key: 'session.started',
		label: 'Session started',
		variables: ['session_id', 'drive_id'],
		default_title: 'ARM: session started',
		default_body: 'A new ripping session started on drive {drive_id}.'
	}
];

describe('AddChannelForm', () => {
	afterEach(() => cleanup());

	it('disables Save until required fields are met, then emits body on save', async () => {
		const onsave = vi.fn();
		renderComponent(AddChannelForm, { props: { catalog, eventTypes, onsave, oncancel: () => {}, ontest: () => {} } });

		const save = screen.getByRole('button', { name: /save channel/i });
		expect(save).toBeDisabled();

		await fireEvent.click(screen.getByRole('radio', { name: /webhook/i }));
		await fireEvent.input(screen.getByLabelText('Channel Label'), { target: { value: 'My Hook' } });
		await fireEvent.input(screen.getByLabelText(/webhook url/i), { target: { value: 'https://hooks.example/x' } });
		await fireEvent.click(screen.getByLabelText('Rip completed'));
		// Now that the event is enabled, its inline template inputs appear.
		await fireEvent.input(screen.getByLabelText('rip.completed title'), { target: { value: 'Hi {job_title}' } });

		await waitFor(() => expect(screen.getByRole('button', { name: /save channel/i })).toBeEnabled());
		await fireEvent.click(screen.getByRole('button', { name: /save channel/i }));

		expect(onsave).toHaveBeenCalledWith(
			expect.objectContaining({
				type: 'webhook',
				name: 'My Hook',
				config: expect.objectContaining({ url: 'https://hooks.example/x' }),
				subscribed_events: ['rip.completed'],
				templates: expect.objectContaining({ 'rip.completed': { title: 'Hi {job_title}', body: null } })
			})
		);
	});

	it('switching type resets config', async () => {
		renderComponent(AddChannelForm, { props: { catalog, eventTypes, onsave: () => {}, oncancel: () => {}, ontest: () => {} } });
		await fireEvent.click(screen.getByRole('radio', { name: /webhook/i }));
		await fireEvent.input(screen.getByLabelText(/webhook url/i), { target: { value: 'https://x' } });
		await fireEvent.click(screen.getByRole('radio', { name: /bash/i }));
		expect(screen.queryByLabelText(/webhook url/i)).toBeNull();
		expect((screen.getByLabelText('Script') as HTMLSelectElement).value).toBe('');
	});

	it('bash shows the test panel instead of the Send test button', async () => {
		renderComponent(AddChannelForm, { props: { catalog, eventTypes, onsave: () => {}, oncancel: () => {}, ontest: () => {} } });
		await fireEvent.click(screen.getByRole('radio', { name: /bash/i }));
		expect(screen.queryByRole('button', { name: 'Send test' })).toBeNull();
		expect(screen.getByText('Test')).toBeInTheDocument();
	});
});
