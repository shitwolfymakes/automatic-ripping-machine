import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import type { ChannelTemplate } from '$lib/types/notifications';
import EventSubscriptions from '../EventSubscriptions.svelte';

describe('EventSubscriptions', () => {
	afterEach(() => cleanup());

	it('renders a checkbox per event with labels', () => {
		renderComponent(EventSubscriptions, { props: { selected: [], templates: {} } });
		expect(screen.getByLabelText('Job started')).toBeTruthy();
		expect(screen.getByLabelText('Rip complete')).toBeTruthy();
		expect(screen.getByLabelText('Transcode complete')).toBeTruthy();
		expect(screen.getByLabelText('Job failed')).toBeTruthy();
		expect(screen.getByLabelText('Manual wait required')).toBeTruthy();
		expect(screen.getByLabelText('Duplicate detected')).toBeTruthy();
	});

	it('checks boxes for already-selected events', () => {
		renderComponent(EventSubscriptions, { props: { selected: ['job.started', 'job.failed'], templates: {} } });
		expect((screen.getByLabelText('Job started') as HTMLInputElement).checked).toBe(true);
		expect((screen.getByLabelText('Rip complete') as HTMLInputElement).checked).toBe(false);
	});

	it('checks a box when its event is clicked', async () => {
		renderComponent(EventSubscriptions, { props: { selected: [], templates: {} } });
		await fireEvent.click(screen.getByLabelText('Job failed'));
		expect((screen.getByLabelText('Job failed') as HTMLInputElement).checked).toBe(true);
	});

	it('shows the title/body template inputs only when an event is checked', async () => {
		const props = $state({ selected: [] as string[], templates: {} as Record<string, ChannelTemplate> });
		renderComponent(EventSubscriptions, { props });
		// Unchecked: no per-event template inputs.
		expect(screen.queryByLabelText('job.started title')).toBeNull();
		expect(screen.queryByLabelText('job.started body')).toBeNull();
		// Check the event -> its inputs appear.
		await fireEvent.click(screen.getByLabelText('Job started'));
		expect(screen.getByLabelText('job.started title')).toBeInTheDocument();
		expect(screen.getByLabelText('job.started body')).toBeInTheDocument();
	});

	it('a variable chip inserts {var} into the title field', async () => {
		const props = $state({ selected: ['job.started'] as string[], templates: {} as Record<string, ChannelTemplate> });
		renderComponent(EventSubscriptions, { props });
		// Insert a variable; with no prior caret it appends to the title.
		await fireEvent.click(screen.getByRole('button', { name: 'Insert {job_id}' }));
		expect((screen.getByLabelText('job.started title') as HTMLInputElement).value).toBe('{job_id}');
		expect(props.templates['job.started']?.title).toBe('{job_id}');
	});

	it('typing into the body input updates the template entry', async () => {
		const props = $state({ selected: ['job.failed'] as string[], templates: {} as Record<string, ChannelTemplate> });
		renderComponent(EventSubscriptions, { props });
		await fireEvent.input(screen.getByLabelText('job.failed body'), { target: { value: 'It broke' } });
		expect(props.templates['job.failed']?.body).toBe('It broke');
	});
});
