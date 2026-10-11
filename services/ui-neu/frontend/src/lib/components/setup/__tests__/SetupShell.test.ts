import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createRawSnippet } from 'svelte';
import { renderComponent, screen, cleanup, fireEvent, waitFor } from '$lib/test-utils';

const gotoMock = vi.fn();
vi.mock('$app/navigation', () => ({ goto: (to: string) => gotoMock(to) }));
const finishLaterMock = vi.fn();
vi.mock('$lib/stores/setup.svelte', () => ({ finishLater: () => finishLaterMock() }));

import SetupShell from '../SetupShell.svelte';

const snippet = (html: string) => createRawSnippet(() => ({ render: () => html }));
const props = () => ({
	stepper: snippet('<nav></nav>'),
	footer: snippet('<div></div>'),
	children: snippet('<p>step</p>')
});

beforeEach(() => {
	gotoMock.mockReset();
	finishLaterMock.mockReset();
});
afterEach(() => cleanup());

describe('SetupShell Finish later', () => {
	it('defers setup on the server, then goes to the dashboard', async () => {
		finishLaterMock.mockResolvedValue(undefined);
		renderComponent(SetupShell, { props: props() });
		await fireEvent.click(screen.getByRole('button', { name: 'Finish later' }));
		await waitFor(() => expect(gotoMock).toHaveBeenCalledWith('/'));
		expect(finishLaterMock).toHaveBeenCalledOnce();
	});

	it('stays on setup and says why when the server could not record it', async () => {
		finishLaterMock.mockRejectedValue(new Error('backend down'));
		renderComponent(SetupShell, { props: props() });
		await fireEvent.click(screen.getByRole('button', { name: 'Finish later' }));
		expect(await screen.findByRole('alert')).toHaveTextContent('backend down');
		expect(gotoMock).not.toHaveBeenCalled();
	});
});
