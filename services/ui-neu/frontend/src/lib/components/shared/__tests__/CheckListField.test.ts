import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/testing/render';
import CheckListFieldHarness from './CheckListFieldHarness.svelte';

const OPTIONS = [
	{ value: 'artist', label: 'Artist' },
	{ value: 'title', label: 'Track title' },
	{ value: 'cover', label: 'Cover art' }
];

const box = (name: string) => screen.getByRole('checkbox', { name }) as HTMLInputElement;
const render = (props: { initial: string[]; disabled?: boolean; helpId?: string }) =>
	renderComponent(CheckListFieldHarness, { props: { options: OPTIONS, ...props } });

afterEach(() => cleanup());

describe('CheckListField', () => {
	it('shows one labelled checkbox per option, ticked as the value says', () => {
		render({ initial: ['cover', 'artist'] });
		expect(screen.getAllByRole('checkbox')).toHaveLength(3);
		expect(box('Artist').checked).toBe(true);
		expect(box('Track title').checked).toBe(false);
		expect(box('Cover art').checked).toBe(true);
	});

	it('names the group by its legend and points it at the help text', () => {
		render({ initial: [], helpId: 'help-x' });
		expect(screen.getByRole('group', { name: 'Music file tags' })).toHaveAttribute('aria-describedby', 'help-x');
	});

	it('writes the ticked values back in the options order', async () => {
		const { component } = render({ initial: ['cover'] });
		await fireEvent.click(box('Artist'));
		expect(component.getValue()).toEqual(['artist', 'cover']);
		await fireEvent.click(box('Cover art'));
		expect(component.getValue()).toEqual(['artist']);
		expect(box('Cover art').checked).toBe(false);
	});

	it('gives each checkbox an id from the prefix, so its label is clickable', () => {
		render({ initial: [] });
		expect(box('Track title').id).toBe('tags-title');
	});

	it('disables every checkbox for a read-only view', () => {
		render({ initial: ['artist'], disabled: true });
		for (const el of screen.getAllByRole('checkbox')) expect(el).toBeDisabled();
	});
});
