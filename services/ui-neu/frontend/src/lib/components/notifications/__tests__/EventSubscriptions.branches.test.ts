import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/testing/render';
import { createSubscriber } from 'svelte/reactivity';
import type { ChannelTemplate } from '$lib/types/notifications';
import type { EventTypeInfo, ScriptInput } from '$lib/api/channels';
import EventSubscriptions from '../EventSubscriptions.svelte';

// Branch pins for EventSubscriptions, beside EventSubscriptions.svelte.test.ts.
// One branch cannot be reached from the rendered component, so nothing here
// forces it:
// - each option's `value={v}` in the values select: Svelte compiles in a check
//   for an unchanged value and a `?? ''` for a null one. The each block is
//   keyed by the value itself, so an option's value never changes, and the
//   values are strings, never null.

const ripCompleted: EventTypeInfo = {
	key: 'rip.completed',
	label: 'Rip completed',
	variables: [
		'job_title',
		'drive_id',
		'tracks_done',
		'tracks_total',
		'status',
		'job_id',
		'job_year',
		'job_disc_type',
		'event_type',
		'occurred_at',
		'tracks_failed'
	],
	default_title: 'ARM: rip completed - {job_title}',
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

const recipient: ScriptInput = {
	key: 'TO',
	label: 'Recipient',
	required: true,
	secret: false,
	default: '',
	values: null
};
const subject: ScriptInput = {
	key: 'SUBJ',
	label: 'Subject',
	required: false,
	secret: false,
	default: '',
	values: null
};
const level: ScriptInput = {
	key: 'LEVEL',
	label: 'Level',
	required: false,
	secret: false,
	default: '',
	values: ['info', 'error']
};

function makeProps(
	selected: string[],
	templates: Record<string, ChannelTemplate> = {},
	inputs: ScriptInput[] = []
): {
	selected: string[];
	templates: Record<string, ChannelTemplate>;
	eventTypes: EventTypeInfo[];
	inputs: ScriptInput[];
} {
	// Runes only compile in .svelte.test.ts files, so the bindable props are accessor pairs
	// that hold what the component writes back and tell it to re-read.
	const held = { selected, templates };
	let notify: () => void = () => {};
	const track = createSubscriber((update) => {
		notify = update;
		return () => {};
	});
	return {
		get selected() {
			track();
			return held.selected;
		},
		set selected(v: string[]) {
			held.selected = v;
			notify();
		},
		get templates() {
			track();
			return held.templates;
		},
		set templates(v: Record<string, ChannelTemplate>) {
			held.templates = v;
			notify();
		},
		eventTypes: catalogEventTypes,
		inputs
	};
}

describe('EventSubscriptions branches', () => {
	afterEach(() => cleanup());

	describe('toggle', () => {
		it('unchecking a selected event removes it from selected and hides its fields', async () => {
			const props = makeProps(['rip.completed', 'session.started']);
			renderComponent(EventSubscriptions, { props });
			await fireEvent.click(screen.getByLabelText('Rip completed'));
			expect(props.selected).toEqual(['session.started']);
			expect(screen.queryByLabelText('rip.completed title')).toBeNull();
			expect(screen.queryByLabelText('rip.completed body')).toBeNull();
		});

		it('a checked change on an already selected event leaves selected as it was', async () => {
			const props = makeProps(['rip.completed']);
			renderComponent(EventSubscriptions, { props });
			const box = screen.getByLabelText('Rip completed');
			await fireEvent.change(box, { target: { checked: true } });
			expect(props.selected).toEqual(['rip.completed']);
		});
	});

	describe('ensure and the field handlers', () => {
		it('typing into the title twice writes the same entry, and clearing it writes null', async () => {
			const props = makeProps(['rip.completed']);
			renderComponent(EventSubscriptions, { props });
			const title = screen.getByLabelText('rip.completed title');
			await fireEvent.input(title, { target: { value: 'A' } });
			const entry = props.templates['rip.completed'];
			expect(entry.title).toBe('A');
			await fireEvent.input(title, { target: { value: 'AB' } });
			expect(props.templates['rip.completed']).toBe(entry);
			expect(entry.title).toBe('AB');
			await fireEvent.input(title, { target: { value: '' } });
			expect(entry.title).toBeNull();
		});

		it('typing into the body twice writes the same entry, and clearing it writes null', async () => {
			const props = makeProps(['rip.completed']);
			renderComponent(EventSubscriptions, { props });
			const body = screen.getByLabelText('rip.completed body');
			await fireEvent.input(body, { target: { value: 'X' } });
			const entry = props.templates['rip.completed'];
			expect(entry.body).toBe('X');
			await fireEvent.input(body, { target: { value: 'XY' } });
			expect(props.templates['rip.completed']).toBe(entry);
			expect(entry.body).toBe('XY');
			await fireEvent.input(body, { target: { value: '' } });
			expect(entry.body).toBeNull();
		});

		it('a field with no reported caret takes an inserted variable at the end of its text', async () => {
			const props = makeProps(['rip.completed']);
			renderComponent(EventSubscriptions, { props });
			const title = screen.getByLabelText('rip.completed title') as HTMLInputElement;
			Object.defineProperty(title, 'selectionStart', { value: null, configurable: true });
			Object.defineProperty(title, 'selectionEnd', { value: null, configurable: true });
			await fireEvent.input(title, { target: { value: 'abc' } });
			await fireEvent.click(screen.getByRole('button', { name: 'Insert {job_title}' }));
			expect(props.templates['rip.completed'].title).toBe('abc{job_title}');
		});
	});

	describe('setInput', () => {
		it('setting an override then clearing it leaves inputs null', async () => {
			const props = makeProps(['rip.completed'], {}, [recipient]);
			renderComponent(EventSubscriptions, { props });
			const field = screen.getByLabelText('rip.completed Recipient');
			await fireEvent.input(field, { target: { value: 'a@x' } });
			expect(props.templates['rip.completed'].inputs).toEqual({ TO: 'a@x' });
			await fireEvent.input(field, { target: { value: '' } });
			expect(props.templates['rip.completed'].inputs).toBeNull();
		});

		it('clearing one of two overrides leaves the other', async () => {
			const props = makeProps(['rip.completed'], {}, [recipient, subject]);
			renderComponent(EventSubscriptions, { props });
			await fireEvent.input(screen.getByLabelText('rip.completed Recipient'), { target: { value: 'a@x' } });
			await fireEvent.input(screen.getByLabelText('rip.completed Subject'), { target: { value: 'Hi' } });
			expect(props.templates['rip.completed'].inputs).toEqual({ TO: 'a@x', SUBJ: 'Hi' });
			await fireEvent.input(screen.getByLabelText('rip.completed Recipient'), { target: { value: '' } });
			expect(props.templates['rip.completed'].inputs).toEqual({ SUBJ: 'Hi' });
		});

		it('an input with values renders a select with inherit and each value', async () => {
			const props = makeProps(['rip.completed'], {}, [level]);
			renderComponent(EventSubscriptions, { props });
			const select = screen.getByLabelText('rip.completed Level') as HTMLSelectElement;
			expect(select.tagName).toBe('SELECT');
			expect(Array.from(select.options).map((o) => o.textContent)).toEqual(['inherit', 'info', 'error']);
		});

		it('choosing a value writes the override and choosing inherit clears it', async () => {
			const props = makeProps(['rip.completed'], {}, [level]);
			renderComponent(EventSubscriptions, { props });
			const select = screen.getByLabelText('rip.completed Level');
			await fireEvent.change(select, { target: { value: 'error' } });
			expect(props.templates['rip.completed'].inputs).toEqual({ LEVEL: 'error' });
			await fireEvent.change(select, { target: { value: '' } });
			expect(props.templates['rip.completed'].inputs).toBeNull();
		});

		it('a required input label ends with " *" and an optional one does not', () => {
			renderComponent(EventSubscriptions, { props: makeProps(['rip.completed'], {}, [recipient, subject]) });
			expect(screen.getByText('Recipient *')).toBeTruthy();
			expect(screen.getByText('Subject')).toBeTruthy();
		});

		it('the help line mentions inheriting hook values only when there are inputs', () => {
			renderComponent(EventSubscriptions, { props: makeProps(['rip.completed'], {}, [recipient]) });
			expect(
				screen.getByText("Leave blank to use the default shown; blank inputs inherit the hook's values.")
			).toBeTruthy();
			cleanup();
			renderComponent(EventSubscriptions, { props: makeProps(['rip.completed']) });
			expect(screen.getByText('Leave blank to use the default shown.')).toBeTruthy();
		});
	});

	describe('insertVariable', () => {
		it('inserts at the caret in the focused body, keeps the focus and puts the caret after the token', async () => {
			const props = makeProps(['rip.completed']);
			renderComponent(EventSubscriptions, { props });
			const body = screen.getByLabelText('rip.completed body') as HTMLTextAreaElement;
			await fireEvent.input(body, { target: { value: 'hello world' } });
			body.setSelectionRange(5, 5);
			await fireEvent.click(body);
			await fireEvent.click(screen.getByRole('button', { name: 'Insert {job_title}' }));
			await waitFor(() => expect(props.templates['rip.completed'].body).toBe('hello{job_title} world'));
			expect(document.activeElement).toBe(body);
			expect(body.selectionStart).toBe(16);
			expect(body.selectionEnd).toBe(16);
		});

		it('an insert leaves a values select with no override showing inherit', async () => {
			const props = makeProps(['rip.completed'], {}, [level]);
			renderComponent(EventSubscriptions, { props });
			await fireEvent.click(screen.getByRole('button', { name: 'Insert {job_title}' }));
			expect((screen.getByLabelText('rip.completed Level') as HTMLSelectElement).value).toBe('');
		});

		it('a keyup in the title or body remembers the caret for the next insert', async () => {
			const props = makeProps(['rip.completed']);
			renderComponent(EventSubscriptions, { props });
			const title = screen.getByLabelText('rip.completed title') as HTMLInputElement;
			const body = screen.getByLabelText('rip.completed body') as HTMLTextAreaElement;
			await fireEvent.input(title, { target: { value: 'abcd' } });
			title.setSelectionRange(1, 1);
			await fireEvent.keyUp(title);
			await fireEvent.click(screen.getByRole('button', { name: 'Insert {drive_id}' }));
			expect(props.templates['rip.completed'].title).toBe('a{drive_id}bcd');
			await fireEvent.input(body, { target: { value: 'wxyz' } });
			body.setSelectionRange(2, 2);
			await fireEvent.keyUp(body);
			await fireEvent.click(screen.getByRole('button', { name: 'Insert {status}' }));
			expect(props.templates['rip.completed'].body).toBe('wx{status}yz');
		});

		it('a click in the title remembers the caret for the next insert', async () => {
			const props = makeProps(['rip.completed']);
			renderComponent(EventSubscriptions, { props });
			const title = screen.getByLabelText('rip.completed title') as HTMLInputElement;
			await fireEvent.input(title, { target: { value: 'abcd' } });
			title.setSelectionRange(2, 2);
			await fireEvent.click(title);
			await fireEvent.click(screen.getByRole('button', { name: 'Insert {drive_id}' }));
			expect(props.templates['rip.completed'].title).toBe('ab{drive_id}cd');
		});

		it('a chip for another event inserts at the end of that event title, not into the focused field', async () => {
			const props = makeProps(['rip.completed', 'session.started'], {
				'session.started': { title: 'ARM', body: null }
			});
			renderComponent(EventSubscriptions, { props });
			const focused = screen.getByLabelText('rip.completed title') as HTMLInputElement;
			await fireEvent.input(focused, { target: { value: 'mine' } });
			await fireEvent.click(screen.getByRole('button', { name: 'Insert {session_id}' }));
			expect(props.templates['session.started']).toEqual({ title: 'ARM{session_id}', body: null });
			expect(props.templates['rip.completed'].title).toBe('mine');
		});

		it('an event with no template yet gets the token as its title and a null body', async () => {
			const props = makeProps(['rip.completed']);
			renderComponent(EventSubscriptions, { props });
			await fireEvent.click(screen.getByRole('button', { name: 'Insert {job_title}' }));
			expect(props.templates['rip.completed']).toEqual({ title: '{job_title}', body: null });
		});

		it('inserting into the title keeps an empty body null', async () => {
			const props = makeProps(['rip.completed'], { 'rip.completed': { title: 'T', body: null } });
			renderComponent(EventSubscriptions, { props });
			await fireEvent.click(screen.getByRole('button', { name: 'Insert {job_title}' }));
			expect(props.templates['rip.completed']).toEqual({ title: 'T{job_title}', body: null });
		});

		it('inserting into the body keeps the title', async () => {
			const props = makeProps(['rip.completed'], { 'rip.completed': { title: 'T', body: null } });
			renderComponent(EventSubscriptions, { props });
			const body = screen.getByLabelText('rip.completed body');
			await fireEvent.focus(body);
			await fireEvent.click(screen.getByRole('button', { name: 'Insert {job_title}' }));
			expect(props.templates['rip.completed']).toEqual({ title: 'T', body: '{job_title}' });
		});

		it('inserting into the body keeps an existing body text around the token', async () => {
			const props = makeProps(['rip.completed'], { 'rip.completed': { title: null, body: 'B' } });
			renderComponent(EventSubscriptions, { props });
			await fireEvent.click(screen.getByRole('button', { name: 'Insert {job_title}' }));
			expect(props.templates['rip.completed']).toEqual({ title: '{job_title}', body: 'B' });
		});

		// #539 tracks this: the insert rebuilds the template from title and body only.
		it('an insert drops the input overrides of the event template', async () => {
			const props = makeProps(['rip.completed'], {}, [recipient]);
			renderComponent(EventSubscriptions, { props });
			await fireEvent.input(screen.getByLabelText('rip.completed Recipient'), { target: { value: 'a@x' } });
			expect(props.templates['rip.completed'].inputs).toEqual({ TO: 'a@x' });
			await fireEvent.click(screen.getByRole('button', { name: 'Insert {job_title}' }));
			expect(props.templates['rip.completed']).not.toHaveProperty('inputs');
			expect(props.templates['rip.completed'].title).toBe('{job_title}');
		});
	});

	describe('default props', () => {
		it('renders no checkboxes when no eventTypes prop is given', () => {
			renderComponent(EventSubscriptions, { props: { selected: [], templates: {} } as never });
			expect(screen.queryByRole('checkbox')).toBeNull();
		});
	});
});
