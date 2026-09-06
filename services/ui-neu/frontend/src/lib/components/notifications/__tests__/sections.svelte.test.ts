import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import EventsSection from '../sections/EventsSection.svelte';
import ConfigureSection from '../sections/ConfigureSection.svelte';
import type { CatalogField, CatalogService, ChannelTemplate } from '$lib/types/notifications';
import type { EventTypeInfo } from '$lib/api/channels';

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
