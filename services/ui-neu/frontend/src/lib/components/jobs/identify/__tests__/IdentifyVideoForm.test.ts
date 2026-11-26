import { describe, it, expect, afterEach, vi } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/testing/render';
import IdentifyVideoFormHarness from './IdentifyVideoFormHarness.svelte';

afterEach(() => cleanup());

type Values = { title: string; year: number | null };

const render = (props: { submitting?: boolean } = {}) => {
	const ontitleinput = vi.fn();
	const { component } = renderComponent(IdentifyVideoFormHarness, { props: { ...props, ontitleinput } });
	return { ontitleinput, getValues: (component as unknown as { getValues: () => Values }).getValues };
};

describe('IdentifyVideoForm', () => {
	it('writes typed Title and Year back to the bound values', async () => {
		const { getValues } = render();
		await fireEvent.input(screen.getByTestId('identify-title'), { target: { value: 'Alien' } });
		await fireEvent.input(screen.getByTestId('identify-year'), { target: { value: '1979' } });
		expect(getValues()).toEqual({ title: 'Alien', year: 1979 });
	});

	it('calls ontitleinput on each Title edit but not on a Year edit', async () => {
		const { ontitleinput } = render();
		await fireEvent.input(screen.getByTestId('identify-year'), { target: { value: '1979' } });
		expect(ontitleinput).not.toHaveBeenCalled();
		await fireEvent.input(screen.getByTestId('identify-title'), { target: { value: 'A' } });
		await fireEvent.input(screen.getByTestId('identify-title'), { target: { value: 'Al' } });
		expect(ontitleinput).toHaveBeenCalledTimes(2);
	});

	it('disables both inputs while submitting', () => {
		render({ submitting: true });
		expect(screen.getByTestId('identify-title')).toBeDisabled();
		expect(screen.getByTestId('identify-year')).toBeDisabled();
	});
});
