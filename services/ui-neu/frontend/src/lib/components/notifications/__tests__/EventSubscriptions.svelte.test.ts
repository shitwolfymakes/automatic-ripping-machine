import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import type { ChannelTemplate } from '$lib/types/notifications';
import type { EventTypeInfo } from '$lib/api/channels';
import EventSubscriptions from '../EventSubscriptions.svelte';

const ripCompleted: EventTypeInfo = {
	key: 'rip.completed',
	label: 'Rip completed',
	variables: ['job_title', 'drive_id', 'tracks_done', 'tracks_total', 'status', 'job_id', 'job_year', 'job_disc_type', 'event_type', 'occurred_at', 'tracks_failed'],
	default_title: 'ARM: rip completed — {job_title}',
	default_body: '{job_title} finished ripping on drive {drive_id} ({tracks_done}/{tracks_total} tracks).'
};

const sessionStarted: EventTypeInfo = {
	key: 'session.started',
	label: 'Session started',
	variables: ['session_id', 'drive_id', 'occurred_at'],
	default_title: 'ARM: session started',
	default_body: 'A new ripping session started on drive {drive_id}.'
};

const catalogEventTypes: EventTypeInfo[] = [ripCompleted, sessionStarted];

describe('EventSubscriptions', () => {
	afterEach(() => cleanup());

	it('renders a checkbox per event with labels from catalog', () => {
		renderComponent(EventSubscriptions, { props: { selected: [], templates: {}, eventTypes: catalogEventTypes } });
		expect(screen.getByLabelText('Rip completed')).toBeTruthy();
		expect(screen.getByLabelText('Session started')).toBeTruthy();
	});

	it('checks boxes for already-selected events', () => {
		renderComponent(EventSubscriptions, { props: { selected: ['rip.completed'], templates: {}, eventTypes: catalogEventTypes } });
		expect((screen.getByLabelText('Rip completed') as HTMLInputElement).checked).toBe(true);
		expect((screen.getByLabelText('Session started') as HTMLInputElement).checked).toBe(false);
	});

	it('checks a box when its event is clicked', async () => {
		renderComponent(EventSubscriptions, { props: { selected: [], templates: {}, eventTypes: catalogEventTypes } });
		await fireEvent.click(screen.getByLabelText('Rip completed'));
		expect((screen.getByLabelText('Rip completed') as HTMLInputElement).checked).toBe(true);
	});

	it('shows the title/body template inputs only when an event is checked', async () => {
		const props = $state({ selected: [] as string[], templates: {} as Record<string, ChannelTemplate>, eventTypes: catalogEventTypes });
		renderComponent(EventSubscriptions, { props });
		// Unchecked: no per-event template inputs.
		expect(screen.queryByLabelText('rip.completed title')).toBeNull();
		expect(screen.queryByLabelText('rip.completed body')).toBeNull();
		// Check the event -> its inputs appear.
		await fireEvent.click(screen.getByLabelText('Rip completed'));
		expect(screen.getByLabelText('rip.completed title')).toBeInTheDocument();
		expect(screen.getByLabelText('rip.completed body')).toBeInTheDocument();
	});

	it('a variable chip inserts {var} into the title field', async () => {
		const props = $state({ selected: ['rip.completed'] as string[], templates: {} as Record<string, ChannelTemplate>, eventTypes: catalogEventTypes });
		renderComponent(EventSubscriptions, { props });
		// Insert a variable; with no prior caret it appends to the title.
		await fireEvent.click(screen.getByRole('button', { name: 'Insert {job_title}' }));
		expect((screen.getByLabelText('rip.completed title') as HTMLInputElement).value).toBe('{job_title}');
		expect(props.templates['rip.completed']?.title).toBe('{job_title}');
	});

	it('typing into the body input updates the template entry', async () => {
		const props = $state({ selected: ['session.started'] as string[], templates: {} as Record<string, ChannelTemplate>, eventTypes: catalogEventTypes });
		renderComponent(EventSubscriptions, { props });
		await fireEvent.input(screen.getByLabelText('session.started body'), { target: { value: 'It started' } });
		expect(props.templates['session.started']?.body).toBe('It started');
	});

	it('renders no checkboxes when eventTypes is empty', () => {
		renderComponent(EventSubscriptions, { props: { selected: [], templates: {}, eventTypes: [] } });
		expect(screen.queryByRole('checkbox')).toBeNull();
	});

	it('renders non-secret inputs per subscribed event and writes overrides into templates', async () => {
		const inputs = [
			{ key: 'TO', label: 'Recipient', required: true, secret: false, default: '', values: null },
			{ key: 'SMTP_PASS', label: 'SMTP password', required: false, secret: true, default: '', values: null }
		];
		const props = $state({ selected: ['rip.completed'], templates: {} as Record<string, ChannelTemplate>, eventTypes: catalogEventTypes, inputs });
		renderComponent(EventSubscriptions, { props });
		const field = screen.getByLabelText('rip.completed Recipient') as HTMLInputElement;
		expect(field.placeholder).toBe('inherit');
		expect(screen.getByText('Recipient *')).toBeTruthy();
		expect(screen.queryByLabelText('rip.completed SMTP password')).toBeNull();
		await fireEvent.input(field, { target: { value: 'oncall@x' } });
		expect(props.templates['rip.completed'].inputs).toEqual({ TO: 'oncall@x' });
	});
});
