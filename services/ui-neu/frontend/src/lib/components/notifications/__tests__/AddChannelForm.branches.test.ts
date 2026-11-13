import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, waitFor, within, cleanup } from '$lib/test-utils';
import AddChannelForm from '../AddChannelForm.svelte';
import type { AddChannelBody } from '../../../notifications/channel-actions';
import type { Catalog } from '$lib/types/notifications';
import type { EventTypeInfo } from '$lib/api/channels';

// Branch pins for AddChannelForm, beside AddChannelForm.svelte.test.ts. One
// branch cannot be reached from the rendered component, so nothing here
// forces it:
// - The `?? id` fallback in pickService's compact naming: the ServiceDropdown
//   lists only the services of the same `catalog` prop, so a picked id is
//   always found in it and the fallback to the raw id never runs.

vi.mock('$lib/api/channels', async (orig) => ({
	...(await orig<typeof import('$lib/api/channels')>()),
	fetchScripts: vi.fn().mockResolvedValue([]),
	fetchScript: vi.fn().mockRejectedValue(new Error('no script selected')),
	previewBash: vi
		.fn()
		.mockResolvedValue({ title: '', body: '', inputs: {}, env: {}, argv: [], error: null, result: null })
}));

const catalog: Catalog = {
	featured: ['discord'],
	services: [
		{
			id: 'discord',
			name: 'Discord',
			docs_url: '',
			url_scheme: 'discord',
			required_fields: [{ key: 'webhook_id', label: 'Webhook ID', type: 'string', private: false, required: true }],
			advanced_fields: []
		},
		{
			id: 'slack',
			name: 'Slack',
			docs_url: '',
			url_scheme: 'slack',
			required_fields: [],
			advanced_fields: []
		}
	]
};

const catalogWithoutDiscord: Catalog = { featured: [], services: [catalog.services[1]] };

const eventTypes: EventTypeInfo[] = [
	{
		key: 'rip.completed',
		label: 'Rip completed',
		variables: ['job_title', 'drive_id'],
		default_title: 'ARM: rip completed - {job_title}',
		default_body: '{job_title} finished ripping on drive {drive_id}.'
	}
];

type Handle = { getBody: () => AddChannelBody; isStarted: () => boolean };

function renderForm(props: Record<string, unknown> = {}) {
	const view = renderComponent(AddChannelForm, {
		props: { catalog, eventTypes, onsave: () => {}, oncancel: () => {}, ontest: () => {}, ...props }
	});
	return { ...view, form: view.component as unknown as Handle };
}

async function pickService(name: RegExp) {
	await fireEvent.click(screen.getByRole('button', { name: /select a service|discord|slack/i }));
	await fireEvent.click(screen.getByRole('button', { name }));
}

afterEach(() => cleanup());

describe('AddChannelForm default props', () => {
	it('renders with no eventTypes prop and an empty events list', () => {
		renderComponent(AddChannelForm, { props: { catalog, ontest: () => {} } });
		expect(screen.getByText(/^Needs:/)).toHaveTextContent('at least one event');
		expect(screen.queryByLabelText('Rip completed')).toBeNull();
	});
});

describe('AddChannelForm service lookup', () => {
	it('treats a picked service the catalog no longer lists as no service', async () => {
		const { form, rerender } = renderForm();
		await pickService(/^Discord/);
		expect(screen.getByLabelText('Webhook ID')).toBeInTheDocument();

		await rerender({ catalog: catalogWithoutDiscord });

		expect(form.isStarted()).toBe(true);
		expect(form.getBody().serviceId).toBe('discord');
		expect(screen.queryByLabelText('Webhook ID')).toBeNull();
		expect(screen.getByText('Select a service...')).toBeInTheDocument();
	});
});

describe('AddChannelForm setType', () => {
	it('keeps serviceId null when the service type is chosen again', async () => {
		const { form } = renderForm();
		await pickService(/^Discord/);
		await fireEvent.click(screen.getByRole('radio', { name: /webhook/i }));
		expect(form.getBody().serviceId).toBeNull();

		await fireEvent.click(screen.getByRole('radio', { name: /service \(apprise\)/i }));

		expect(form.getBody().type).toBe('apprise');
		expect(form.getBody().serviceId).toBeNull();
		expect(form.isStarted()).toBe(false);
	});
});

describe('AddChannelForm pickService in the compact variant', () => {
	it('names the channel after the picked service when the name is blank', async () => {
		const { form } = renderForm({ variant: 'compact' });
		expect(form.getBody().name).toBe('');
		await pickService(/^Discord/);
		expect(form.getBody().name).toBe('Discord');
		expect(form.getBody().serviceId).toBe('discord');
	});

	it('keeps the name when a second service is picked', async () => {
		const { form } = renderForm({ variant: 'compact' });
		await pickService(/^Discord/);
		await pickService(/^Slack/);
		expect(form.getBody().name).toBe('Discord');
		expect(form.getBody().serviceId).toBe('slack');
	});
});

describe('AddChannelForm delivery-type cards', () => {
	it('labels the three cards and badges only the service card', () => {
		const { container } = renderForm();
		const cards = Array.from(container.querySelectorAll<HTMLElement>('.channel-type-option'));
		expect(cards.map((c) => c.querySelector('.channel-type-option-label')?.textContent)).toEqual([
			'Service (Apprise)',
			'Webhook',
			'Bash script'
		]);
		const badged = cards.filter((c) => c.querySelector('.channel-type-option-badge'));
		expect(badged).toHaveLength(1);
		expect(within(badged[0]).getByText('RECOMMENDED')).toBeInTheDocument();
		expect(badged[0]).toHaveTextContent('Service (Apprise)');
	});

	it('marks only the chosen card as selected', async () => {
		const { container } = renderForm();
		const selected = () =>
			Array.from(container.querySelectorAll<HTMLElement>('.channel-type-option'))
				.filter((c) => c.dataset.selected === 'true')
				.map((c) => c.querySelector('.channel-type-option-label')?.textContent);
		expect(selected()).toEqual(['Service (Apprise)']);
		await fireEvent.click(screen.getByRole('radio', { name: /webhook/i }));
		expect(selected()).toEqual(['Webhook']);
		await fireEvent.click(screen.getByRole('radio', { name: /bash/i }));
		expect(selected()).toEqual(['Bash script']);
	});

	it('shows no delivery-type cards in the compact variant', () => {
		const { container } = renderForm({ variant: 'compact' });
		expect(container.querySelector('.channel-type-option')).toBeNull();
	});
});

describe('AddChannelForm footer', () => {
	async function makeWebhookReady() {
		await fireEvent.click(screen.getByRole('radio', { name: /webhook/i }));
		await fireEvent.input(screen.getByLabelText('Channel Label'), { target: { value: 'My Hook' } });
		await fireEvent.input(screen.getByLabelText(/webhook url/i), { target: { value: 'https://hooks.example/x' } });
		await fireEvent.click(screen.getByLabelText('Rip completed'));
	}

	it('lists what is missing before the form is ready', () => {
		const { container } = renderForm();
		const status = container.querySelector<HTMLElement>('.add-channel-form-ready')!;
		expect(status).toHaveTextContent('Needs: channel label, at least one event');
		expect(status.dataset.ready).toBe('false');
		expect(screen.queryByText('Ready to save')).toBeNull();
	});

	it('says Ready to save once the form is ready', async () => {
		const { container } = renderForm();
		await makeWebhookReady();
		await waitFor(() => expect(screen.getByText('Ready to save')).toBeInTheDocument());
		expect(container.querySelector<HTMLElement>('.add-channel-form-ready')!.dataset.ready).toBe('true');
		expect(screen.queryByText(/^Needs:/)).toBeNull();
	});

	it('shows Cancel and Save in the full variant and calls the callbacks', async () => {
		const onsave = vi.fn();
		const oncancel = vi.fn();
		renderForm({ onsave, oncancel });
		await makeWebhookReady();
		await waitFor(() => expect(screen.getByRole('button', { name: 'Save channel' })).toBeEnabled());
		await fireEvent.click(screen.getByRole('button', { name: 'Save channel' }));
		expect(onsave).toHaveBeenCalledWith(expect.objectContaining({ type: 'webhook', name: 'My Hook' }));
		// The header and the footer each carry a Cancel.
		const cancels = screen.getAllByRole('button', { name: /cancel/i });
		expect(cancels).toHaveLength(2);
		await fireEvent.click(cancels[1]);
		expect(oncancel).toHaveBeenCalledTimes(1);
	});

	it('hides Cancel and Save in the compact variant', () => {
		renderForm({ variant: 'compact' });
		expect(screen.queryByRole('button', { name: /cancel/i })).toBeNull();
		expect(screen.queryByRole('button', { name: 'Save channel' })).toBeNull();
	});

	it('hides Send test for a bash channel', async () => {
		renderForm();
		expect(screen.getByRole('button', { name: 'Send test' })).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('radio', { name: /bash/i }));
		expect(screen.queryByRole('button', { name: 'Send test' })).toBeNull();
	});

	it('enables Send test in the full variant even when not ready', async () => {
		const ontest = vi.fn();
		renderForm({ ontest });
		expect(screen.getByText(/^Needs:/)).toBeInTheDocument();
		const send = screen.getByRole('button', { name: 'Send test' });
		expect(send).toBeEnabled();
		await fireEvent.click(send);
		expect(ontest).toHaveBeenCalledWith(expect.objectContaining({ type: 'apprise', serviceId: null }));
	});

	it('disables Send test in the compact variant until the form is ready', async () => {
		const ontest = vi.fn();
		renderForm({ variant: 'compact', ontest });
		expect(screen.getByRole('button', { name: 'Send test' })).toBeDisabled();
		await pickService(/^Discord/);
		expect(screen.getByRole('button', { name: 'Send test' })).toBeDisabled();
		await fireEvent.input(screen.getByLabelText('Webhook ID'), { target: { value: '123' } });
		await waitFor(() => expect(screen.getByRole('button', { name: 'Send test' })).toBeEnabled());
		await fireEvent.click(screen.getByRole('button', { name: 'Send test' }));
		expect(ontest).toHaveBeenCalledWith(expect.objectContaining({ serviceId: 'discord', name: 'Discord' }));
	});
});
