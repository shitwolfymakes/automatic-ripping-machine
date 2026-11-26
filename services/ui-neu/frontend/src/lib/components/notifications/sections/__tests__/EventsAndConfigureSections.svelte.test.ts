import { describe, it, expect, afterEach, vi } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/testing/render';
import EventsSection from '../EventsSection.svelte';
import ConfigureSection from '../ConfigureSection.svelte';
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

function appriseService(
	over: { required_fields?: CatalogField[]; advanced_fields?: CatalogField[] } = {}
): CatalogService {
	return {
		id: 'discord',
		name: 'Discord',
		docs_url: '',
		setup_url: '',
		url_scheme: 'discord',
		required_fields: over.required_fields ?? [],
		advanced_fields: over.advanced_fields ?? []
	};
}

describe('EventsSection', () => {
	afterEach(() => cleanup());

	it('select all checks every event from catalog; clear empties them', async () => {
		const props = $state({
			selected: [] as string[],
			templates: {} as Record<string, ChannelTemplate>,
			eventTypes: catalogEventTypes
		});
		renderComponent(EventsSection, { props });
		await fireEvent.click(screen.getByRole('button', { name: /select all/i }));
		expect(props.selected).toEqual(['rip.completed', 'session.started']);
		await fireEvent.click(screen.getByRole('button', { name: /clear/i }));
		expect(props.selected.length).toBe(0);
	});

	it('renders catalog event labels', () => {
		const props = $state({
			selected: [] as string[],
			templates: {} as Record<string, ChannelTemplate>,
			eventTypes: catalogEventTypes
		});
		renderComponent(EventsSection, { props });
		expect(screen.getByLabelText('Rip completed')).toBeInTheDocument();
		expect(screen.getByLabelText('Session started')).toBeInTheDocument();
	});
});

describe('ConfigureSection', () => {
	afterEach(() => cleanup());

	it('renders the channel label input and enabled toggle', () => {
		const props = $state({
			type: 'webhook' as const,
			name: '',
			enabled: true,
			config: {} as Record<string, unknown>,
			service: null
		});
		renderComponent(ConfigureSection, { props });
		expect(screen.getByLabelText(/channel label/i)).toBeInTheDocument();
		expect(screen.getByRole('switch', { name: /enabled/i })).toBeInTheDocument();
	});

	it('labels the channel label input through its field label, with no docs link', () => {
		renderComponent(ConfigureSection, {
			props: { type: 'webhook', name: '', enabled: true, config: {}, service: null }
		});
		const input = screen.getByLabelText('Channel Label');
		expect(document.querySelector(`label[for="${input.id}"]`)).toHaveTextContent(/^Channel Label$/);
		expect(document.querySelector('.field-label-required')).toHaveAttribute('aria-hidden', 'true');
		expect(screen.queryByRole('link', { name: /^Docs for Channel Label/ })).toBeNull();
	});

	it('the Enabled switch turns the channel off', async () => {
		const props = $state({
			type: 'webhook' as const,
			name: '',
			enabled: true,
			config: {} as Record<string, unknown>,
			service: null
		});
		renderComponent(ConfigureSection, { props });
		await fireEvent.click(screen.getByRole('switch', { name: 'Enabled' }));
		expect(props.enabled).toBe(false);
	});

	it('renders webhook fields (URL) for webhook type', () => {
		const props = $state({
			type: 'webhook' as const,
			name: '',
			enabled: true,
			config: {} as Record<string, unknown>,
			service: null
		});
		renderComponent(ConfigureSection, { props });
		expect(screen.getByLabelText(/webhook url/i)).toBeInTheDocument();
	});

	it('preserveExisting makes config fields optional and shows the keep-current hint', () => {
		const props = $state({
			type: 'webhook' as const,
			name: 'x',
			enabled: true,
			config: {} as Record<string, unknown>,
			service: null,
			preserveExisting: true
		});
		renderComponent(ConfigureSection, { props });
		const url = screen.getByLabelText(/webhook url/i) as HTMLInputElement;
		expect(url.required).toBe(false);
		expect(screen.getByText(/leave blank to keep/i)).toBeInTheDocument();
	});

	it('without preserveExisting, required fields stay required', () => {
		const props = $state({
			type: 'webhook' as const,
			name: 'x',
			enabled: true,
			config: {} as Record<string, unknown>,
			service: null
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
				type: 'webhook' as const,
				name: '',
				enabled: true,
				config: {} as Record<string, unknown>,
				service: null
			}
		});
		expect(screen.getByLabelText(/webhook url/i)).toBeInTheDocument();
		expect(screen.queryByText(/Advanced \(/)).toBeNull();
	});
});

describe('ConfigureSection bash', () => {
	afterEach(cleanup);
	const info = {
		name: 'send-email.sh',
		executable: true,
		description: 'Send an email',
		size_bytes: 120,
		modified_at: '2026-09-06T00:00:00Z',
		preview: '#!/usr/bin/env bash\n# arm-hook: Send an email',
		inputs: [
			{ key: 'TO', label: 'Recipient', required: true, secret: false, default: '', values: null },
			{
				key: 'PRIORITY',
				label: 'Priority',
				required: false,
				secret: false,
				default: 'normal',
				values: ['low', 'normal', 'high']
			},
			{ key: 'SMTP_PASS', label: 'SMTP password', required: false, secret: true, default: '', values: null }
		]
	};

	it('lists scripts, loads the selected script, renders its inputs and viewer', async () => {
		vi.mocked(fetchScripts).mockResolvedValue([
			{ name: 'send-email.sh', executable: true, description: 'Send an email' },
			{ name: 'draft.sh', executable: false, description: '' }
		]);
		vi.mocked(fetchScript).mockResolvedValue(info as never);
		const props = $state({
			type: 'bash' as const,
			name: 'x',
			enabled: true,
			config: {} as Record<string, unknown>,
			service: null
		});
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

	it('labels the script and timeout and links them to the bash hook scripts help', async () => {
		vi.mocked(fetchScripts).mockResolvedValue([]);
		renderComponent(ConfigureSection, { props: { type: 'bash', name: 'x', enabled: true, config: {}, service: null } });
		await screen.findByText('No scripts found');
		const script = screen.getByLabelText('Script');
		const timeout = screen.getByLabelText('Timeout (seconds)');
		expect(document.querySelector(`label[for="${script.id}"]`)).toHaveTextContent(/^Script$/);
		expect(document.querySelector(`label[for="${timeout.id}"]`)).toHaveTextContent(/^Timeout$/);
		expect(screen.getByText('(s)')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: 'Docs for Script (opens in a new tab)' })).toHaveAttribute(
			'href',
			'/help/guide/notification-scripts#where-scripts-live'
		);
		expect(screen.getByRole('link', { name: 'Docs for Timeout (opens in a new tab)' })).toHaveAttribute(
			'href',
			'/help/guide/notification-scripts#failures-and-timeouts'
		);
	});

	it('writes a typed timeout into the config', async () => {
		vi.mocked(fetchScripts).mockResolvedValue([]);
		const props = $state({
			type: 'bash' as const,
			name: 'x',
			enabled: true,
			config: {} as Record<string, unknown>,
			service: null
		});
		renderComponent(ConfigureSection, { props });
		await fireEvent.input(screen.getByLabelText('Timeout (seconds)'), { target: { value: '45' } });
		expect(props.config.timeout_seconds).toBe(45);
	});

	it('shows a failed script listing, and Refresh list lists again', async () => {
		vi.mocked(fetchScripts).mockRejectedValueOnce(new Error('listing failed')).mockResolvedValueOnce([]);
		renderComponent(ConfigureSection, { props: { type: 'bash', name: 'x', enabled: true, config: {}, service: null } });
		expect(await screen.findByText('listing failed')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: 'Refresh list' }));
		expect(await screen.findByText(/arm\/scripts/)).toBeTruthy();
		expect(screen.queryByText('listing failed')).toBeNull();
	});

	it('says so when the chosen script declares no inputs', async () => {
		vi.mocked(fetchScripts).mockResolvedValue([{ name: 'send-email.sh', executable: true, description: '' }]);
		vi.mocked(fetchScript).mockResolvedValue({ ...info, inputs: [] } as never);
		renderComponent(ConfigureSection, {
			props: { type: 'bash', name: 'x', enabled: true, config: { script: 'send-email.sh' }, service: null }
		});
		expect(await screen.findByText(/This script declares no inputs/)).toBeTruthy();
	});

	it('keeps a stale script name selectable as missing and masks stored secrets', async () => {
		vi.mocked(fetchScripts).mockResolvedValue([]);
		vi.mocked(fetchScript).mockRejectedValue(new Error('404'));
		renderComponent(ConfigureSection, {
			props: {
				type: 'bash',
				name: 'x',
				enabled: true,
				config: { script: 'gone.sh', inputs: { SMTP_PASS: '<hidden>' }, secret_keys: ['SMTP_PASS'] },
				service: null
			}
		});
		await screen.findByText('No scripts found');
		const select = screen.getByLabelText('Script') as HTMLSelectElement;
		expect(select.value).toBe('gone.sh');
		expect(select.options[1].textContent).toContain('missing');
	});
});

describe('ConfigureSection docs links', () => {
	afterEach(() => cleanup());

	const fields = {
		required_fields: [
			{ key: 'webhook_id', label: 'Webhook ID', type: 'string' as const, private: true, required: true }
		],
		advanced_fields: [
			{ key: 'thread', label: 'Thread ID', type: 'string' as const, private: false, required: false },
			{ key: 'tts', label: 'Text To Speech', type: 'bool' as const, private: false, required: false }
		]
	};

	it('links each field of a featured service to its own docs, with no service-wide link', () => {
		renderComponent(ConfigureSection, {
			props: { type: 'apprise' as const, name: '', enabled: true, config: {}, service: appriseService(fields) }
		});
		const ids = screen.getAllByRole('link', { name: /^Docs for/ }).map((a) => a.getAttribute('data-field-id'));
		expect(ids).toEqual(['notify.discord.webhook_id', 'notify.discord.thread', 'notify.discord.tts']);
		expect(screen.getByRole('link', { name: 'Docs for Webhook ID (opens in a new tab)' })).toHaveAttribute(
			'href',
			'https://appriseit.com/services/discord/#parameter-breakdown'
		);
		expect(screen.queryByRole('link', { name: 'Docs for Discord (opens in a new tab)' })).toBeNull();
	});

	it("gives any other service one link, to Apprise's setup page for it", () => {
		const service = {
			...appriseService(fields),
			id: 'zulip',
			name: 'Zulip',
			setup_url: 'https://appriseit.com/services/zulip/'
		};
		renderComponent(ConfigureSection, {
			props: { type: 'apprise' as const, name: '', enabled: true, config: {}, service }
		});
		const links = screen.getAllByRole('link', { name: /^Docs for/ });
		expect(links).toHaveLength(1);
		expect(links[0]).toHaveAccessibleName('Docs for Zulip (opens in a new tab)');
		expect(links[0]).toHaveAttribute('href', 'https://appriseit.com/services/zulip/');
		expect(links[0]).toHaveAttribute('target', '_blank');
	});

	it('shows no docs link on the webhook form', () => {
		renderComponent(ConfigureSection, {
			props: { type: 'webhook' as const, name: '', enabled: true, config: {}, service: null }
		});
		expect(screen.queryByRole('link')).toBeNull();
	});

	it('writes each Apprise field it renders, required, advanced text and advanced bool, into config', async () => {
		const props = $state({
			type: 'apprise' as const,
			name: '',
			enabled: true,
			config: {} as Record<string, unknown>,
			service: appriseService(fields)
		});
		renderComponent(ConfigureSection, { props });
		await fireEvent.input(screen.getByLabelText('Webhook ID'), { target: { value: 'w1' } });
		await fireEvent.input(screen.getByLabelText('Thread ID'), { target: { value: 't1' } });
		await fireEvent.click(screen.getByLabelText('Text To Speech'));
		expect(props.config).toEqual({ webhook_id: 'w1', thread: 't1', tts: true });
	});
});
