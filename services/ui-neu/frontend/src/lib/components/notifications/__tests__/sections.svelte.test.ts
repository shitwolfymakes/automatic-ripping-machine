import { describe, it, expect, afterEach, vi } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import EventsSection from '../sections/EventsSection.svelte';
import ConfigureSection from '../sections/ConfigureSection.svelte';
import type { CatalogField, CatalogService, ChannelTemplate } from '$lib/types/notifications';
import type { EventTypeInfo } from '$lib/api/channels';
import { fetchScripts, fetchScript } from '$lib/api/channels';

vi.mock('$lib/api/channels', async (orig) => ({
	...(await orig<typeof import('$lib/api/channels')>()),
	fetchScripts: vi.fn(),
	fetchScript: vi.fn()
}));

const catalogEventTypes: EventTypeInfo[] = [
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

function appriseService(over: { required_fields?: CatalogField[]; advanced_fields?: CatalogField[] } = {}): CatalogService {
	return {
		id: 'discord', name: 'Discord', docs_url: '', url_scheme: 'discord',
		required_fields: over.required_fields ?? [],
		advanced_fields: over.advanced_fields ?? []
	};
}

describe('EventsSection', () => {
	afterEach(() => cleanup());

	it('select all checks every event from catalog; clear empties them', async () => {
		const props = $state({ selected: [] as string[], templates: {} as Record<string, ChannelTemplate>, eventTypes: catalogEventTypes });
		renderComponent(EventsSection, { props });
		await fireEvent.click(screen.getByRole('button', { name: /select all/i }));
		expect(props.selected).toEqual(['rip.completed', 'session.started']);
		await fireEvent.click(screen.getByRole('button', { name: /clear/i }));
		expect(props.selected.length).toBe(0);
	});

	it('renders catalog event labels', () => {
		const props = $state({ selected: [] as string[], templates: {} as Record<string, ChannelTemplate>, eventTypes: catalogEventTypes });
		renderComponent(EventsSection, { props });
		expect(screen.getByLabelText('Rip completed')).toBeInTheDocument();
		expect(screen.getByLabelText('Session started')).toBeInTheDocument();
	});
});

describe('ConfigureSection', () => {
	afterEach(() => cleanup());

	it('renders the channel label input and enabled toggle', () => {
		const props = $state({
			type: 'webhook' as const, name: '', enabled: true,
			config: {} as Record<string, unknown>, service: null
		});
		renderComponent(ConfigureSection, { props });
		expect(screen.getByLabelText(/channel label/i)).toBeInTheDocument();
		expect(screen.getByRole('switch', { name: /enabled/i })).toBeInTheDocument();
	});

	it('renders webhook fields (URL) for webhook type', () => {
		const props = $state({
			type: 'webhook' as const, name: '', enabled: true,
			config: {} as Record<string, unknown>, service: null
		});
		renderComponent(ConfigureSection, { props });
		expect(screen.getByLabelText(/webhook url/i)).toBeInTheDocument();
	});

	it('preserveExisting makes config fields optional and shows the keep-current hint', () => {
		const props = $state({
			type: 'webhook' as const, name: 'x', enabled: true,
			config: {} as Record<string, unknown>, service: null, preserveExisting: true
		});
		renderComponent(ConfigureSection, { props });
		const url = screen.getByLabelText(/webhook url/i) as HTMLInputElement;
		expect(url.required).toBe(false);
		expect(screen.getByText(/leave blank to keep/i)).toBeInTheDocument();
	});

	it('without preserveExisting, required fields stay required', () => {
		const props = $state({
			type: 'webhook' as const, name: 'x', enabled: true,
			config: {} as Record<string, unknown>, service: null
		});
		renderComponent(ConfigureSection, { props });
		const url = screen.getByLabelText(/webhook url/i) as HTMLInputElement;
		expect(url.required).toBe(true);
	});

	it('apprise layout: required fields visible at top; advanced inside a closed <details>', () => {
		const service = appriseService({
			required_fields: [
				{ key: 'webhook_id', label: 'Webhook ID', type: 'string', private: true, required: true },
				{ key: 'webhook_token', label: 'Webhook Token', type: 'string', private: true, required: true }
			],
			advanced_fields: [
				{ key: 'thread', label: 'Thread ID', type: 'string', private: false, required: false },
				{ key: 'tts', label: 'Text To Speech', type: 'bool', private: false, required: false }
			]
		});
		renderComponent(ConfigureSection, {
			props: { type: 'apprise' as const, name: '', enabled: true, config: {}, service }
		});
		expect(screen.getByLabelText('Webhook ID')).toBeInTheDocument();
		expect(screen.getByLabelText('Webhook Token')).toBeInTheDocument();
		const details = screen.getByText(/Advanced \(2\)/i).closest('details') as HTMLDetailsElement;
		expect(details).toBeInTheDocument();
		expect(details.open).toBe(false);
	});

	it('apprise advanced expanded: bool fields render separately from text inputs', async () => {
		const service = appriseService({
			advanced_fields: [
				{ key: 'thread', label: 'Thread ID', type: 'string', private: false, required: false },
				{ key: 'tts', label: 'Text To Speech', type: 'bool', private: false, required: false }
			]
		});
		renderComponent(ConfigureSection, {
			props: { type: 'apprise' as const, name: '', enabled: true, config: {}, service }
		});
		const details = screen.getByText(/Advanced \(2\)/i).closest('details') as HTMLDetailsElement;
		details.open = true;
		expect(screen.getByLabelText('Thread ID')).toBeInTheDocument();
		expect(screen.getByLabelText('Text To Speech')).toBeInTheDocument();
	});

	it('webhook layout unchanged: single grid, no <details>', () => {
		renderComponent(ConfigureSection, {
			props: {
				type: 'webhook' as const, name: '', enabled: true,
				config: {} as Record<string, unknown>, service: null
			}
		});
		expect(screen.getByLabelText(/webhook url/i)).toBeInTheDocument();
		expect(screen.queryByText(/Advanced \(/)).toBeNull();
	});
});

describe('ConfigureSection bash', () => {
	afterEach(cleanup);
	const info = {
		name: 'send-email.sh', executable: true, description: 'Send an email', size_bytes: 120, modified_at: '2026-09-06T00:00:00Z',
		preview: '#!/usr/bin/env bash\n# arm-hook: Send an email',
		inputs: [
			{ key: 'TO', label: 'Recipient', required: true, secret: false, default: '', values: null },
			{ key: 'PRIORITY', label: 'Priority', required: false, secret: false, default: 'normal', values: ['low', 'normal', 'high'] },
			{ key: 'SMTP_PASS', label: 'SMTP password', required: false, secret: true, default: '', values: null }
		]
	};

	it('lists scripts, loads the selected script, renders its inputs and viewer', async () => {
		vi.mocked(fetchScripts).mockResolvedValue([{ name: 'send-email.sh', executable: true, description: 'Send an email' }, { name: 'draft.sh', executable: false, description: '' }]);
		vi.mocked(fetchScript).mockResolvedValue(info as never);
		const props = $state({ type: 'bash' as const, name: 'x', enabled: true, config: {} as Record<string, unknown>, service: null });
		renderComponent(ConfigureSection, { props });
		await screen.findByText('Choose a script');
		const select = screen.getByLabelText('Script') as HTMLSelectElement;
		expect(select.options[2].disabled).toBe(true);
		expect(select.options[2].textContent).toContain('not executable');
		await fireEvent.change(select, { target: { value: 'send-email.sh' } });
		expect(props.config.script).toBe('send-email.sh');
		expect(await screen.findByText('Send an email')).toBeTruthy();
		expect(await screen.findByLabelText('Recipient')).toBeTruthy();
		const priority = (await screen.findByLabelText('Priority')) as HTMLSelectElement;
		expect(priority.value).toBe('normal');
		expect((screen.getByLabelText('SMTP password') as HTMLInputElement).type).toBe('password');
		await fireEvent.input(screen.getByLabelText('Recipient'), { target: { value: 'me@x' } });
		expect((props.config.inputs as Record<string, string>).TO).toBe('me@x');
		await fireEvent.click(screen.getByText(/view script/i));
		expect(screen.getByText(/arm-hook: Send an email/)).toBeTruthy();
		expect((screen.getByLabelText('Timeout (seconds)') as HTMLInputElement).value).toBe('30');
	});

	it('shows the drop-in hint when no scripts exist', async () => {
		vi.mocked(fetchScripts).mockResolvedValue([]);
		renderComponent(ConfigureSection, { props: { type: 'bash', name: 'x', enabled: true, config: {}, service: null } });
		expect(await screen.findByText(/arm\/scripts/)).toBeTruthy();
	});

	it('keeps a stale script name selectable as missing and masks stored secrets', async () => {
		vi.mocked(fetchScripts).mockResolvedValue([]);
		vi.mocked(fetchScript).mockRejectedValue(new Error('404'));
		renderComponent(ConfigureSection, { props: { type: 'bash', name: 'x', enabled: true, config: { script: 'gone.sh', inputs: { SMTP_PASS: '<hidden>' }, secret_keys: ['SMTP_PASS'] }, service: null } });
		await screen.findByText('No scripts found');
		const select = screen.getByLabelText('Script') as HTMLSelectElement;
		expect(select.value).toBe('gone.sh');
		expect(select.options[1].textContent).toContain('missing');
	});
});
