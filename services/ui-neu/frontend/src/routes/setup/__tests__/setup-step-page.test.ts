// Behaviour tests for the setup walkthrough's step page. The nine step
// components are replaced by one stand-in; the setup API and goto are faked;
// the real setup store and footer/stepper/shell render on top.
//
// Branches the page cannot reach, so they are not forced here:
// - Continue's guard for a missing step component: the footer disables
//   Continue until the setup view has loaded, and the step component is bound
//   as soon as the view is there.
// - go() given null: Back is hidden on the first step, Skip only shows on
//   optional steps (none is last), and the stepper only selects real steps;
//   the finish step never calls go() after completing.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { tick } from 'svelte';
import { renderComponent, screen, fireEvent, waitFor, within, cleanup } from '$lib/testing/render';
import type { SetupStep, SetupView } from '$lib/types/api.gen';
import { setupState } from '$lib/stores/setup.svelte';
import { stubState } from './fixtures/setup-step-stub';

const fetchSetup = vi.fn();
const putSetupStep = vi.fn();
const deferSetup = vi.fn();
const completeSetup = vi.fn();
vi.mock('$lib/api/setup', () => ({
	fetchSetup: (...a: unknown[]) => fetchSetup(...a),
	putSetupStep: (...a: unknown[]) => putSetupStep(...a),
	deferSetup: (...a: unknown[]) => deferSetup(...a),
	completeSetup: (...a: unknown[]) => completeSetup(...a)
}));

const goto = vi.fn();
vi.mock('$app/navigation', () => ({ goto: (...a: unknown[]) => goto(...a) }));

vi.mock('$lib/components/setup/steps/AccountStep.svelte', async () => ({
	default: (await import('./fixtures/SetupStepStub.svelte')).default
}));
vi.mock('$lib/components/setup/steps/SystemStep.svelte', async () => ({
	default: (await import('./fixtures/SetupStepStub.svelte')).default
}));
vi.mock('$lib/components/setup/steps/DrivesStep.svelte', async () => ({
	default: (await import('./fixtures/SetupStepStub.svelte')).default
}));
vi.mock('$lib/components/setup/steps/MakemkvStep.svelte', async () => ({
	default: (await import('./fixtures/SetupStepStub.svelte')).default
}));
vi.mock('$lib/components/setup/steps/MetadataStep.svelte', async () => ({
	default: (await import('./fixtures/SetupStepStub.svelte')).default
}));
vi.mock('$lib/components/setup/steps/DiscsStep.svelte', async () => ({
	default: (await import('./fixtures/SetupStepStub.svelte')).default
}));
vi.mock('$lib/components/setup/steps/TranscodingStep.svelte', async () => ({
	default: (await import('./fixtures/SetupStepStub.svelte')).default
}));
vi.mock('$lib/components/setup/steps/NotificationsStep.svelte', async () => ({
	default: (await import('./fixtures/SetupStepStub.svelte')).default
}));
vi.mock('$lib/components/setup/steps/FinishStep.svelte', async () => ({
	default: (await import('./fixtures/SetupStepStub.svelte')).default
}));

import Page from '../[step]/+page.svelte';

const makeView = (over: Partial<SetupView> = {}) =>
	({
		completed_at: null,
		progress: {},
		current_step: 'account',
		admin_default_password: false,
		checklist_dismissed: false,
		...over
	}) as SetupView;

const LOAD_ERROR = 'Could not load setup. Check that ARM is running, then reload.';

async function open(step: SetupStep, view: SetupView = makeView()) {
	fetchSetup.mockResolvedValue(view);
	const utils = renderComponent(Page, { props: { data: { step } } });
	await screen.findByTestId('step-stub');
	return utils;
}

const continueBtn = () => screen.getByRole('button', { name: /Continue|Go to dashboard|Saving/ });
const skipBtn = () => screen.getByRole('button', { name: 'Skip for now' });
const backBtn = () => screen.getByRole('button', { name: /Back/ });
// The stepper's mobile header also says "Step N of 9", so scope to the page's.
const eyebrow = () => document.querySelector('.setup-step-eyebrow') as HTMLElement;

/** A promise the test settles by hand. */
function deferred<T>() {
	let resolve!: (v: T) => void;
	let reject!: (e: unknown) => void;
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

beforeEach(() => {
	fetchSetup.mockReset();
	putSetupStep.mockReset();
	deferSetup.mockReset();
	completeSetup.mockReset();
	goto.mockReset();
	putSetupStep.mockResolvedValue(makeView());
	completeSetup.mockResolvedValue(undefined);
	setupState.view = null;
	setupState.loading = false;
	setupState.error = null;
	stubState.commit = async () => 'done';
	stubState.setBlocked = undefined;
});

afterEach(() => cleanup());

describe('setup step page: loading', () => {
	it('shows Loading... while the setup view is pending, then the step', async () => {
		const pending = deferred<SetupView>();
		fetchSetup.mockReturnValue(pending.promise);
		renderComponent(Page, { props: { data: { step: 'system' } } });
		expect(screen.getByText('Loading...')).toBeTruthy();
		expect(screen.queryByTestId('step-stub')).toBeNull();
		pending.resolve(makeView());
		expect(await screen.findByTestId('step-stub')).toBeTruthy();
		expect(screen.queryByText('Loading...')).toBeNull();
	});

	it('shows the load error alert and no Loading... when the load fails', async () => {
		fetchSetup.mockRejectedValue(new Error('down'));
		renderComponent(Page, { props: { data: { step: 'system' } } });
		expect((await screen.findByRole('alert')).textContent).toBe(LOAD_ERROR);
		expect(screen.queryByText('Loading...')).toBeNull();
		expect(screen.queryByTestId('step-stub')).toBeNull();
	});

	it('keeps Continue disabled until the view has loaded', async () => {
		fetchSetup.mockReturnValue(new Promise(() => {}));
		renderComponent(Page, { props: { data: { step: 'system' } } });
		expect((continueBtn() as HTMLButtonElement).disabled).toBe(true);
	});
});

describe('setup step page: default-password redirect', () => {
	it('redirects to the account step when the default password is still set', async () => {
		await open('system', makeView({ admin_default_password: true }));
		await waitFor(() => expect(goto).toHaveBeenCalledWith('/setup/account', { replaceState: true }));
	});

	it('does not redirect on the account step', async () => {
		await open('account', makeView({ admin_default_password: true }));
		expect(goto).not.toHaveBeenCalled();
	});

	it('does not redirect when the default password is not set', async () => {
		await open('system');
		expect(goto).not.toHaveBeenCalled();
	});
});

describe('setup step page: header', () => {
	it('shows the step count, title, intro and document title on a required step', async () => {
		await open('system');
		expect(eyebrow().textContent).toContain('Step 2 of 9');
		expect(screen.queryByText('Optional')).toBeNull();
		expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('System check');
		expect(screen.getByText(/ARM checked the folders and services/)).toBeTruthy();
		expect(document.title).toBe('ARM - Set up: System check');
	});

	it('shows the Optional badge on an optional step', async () => {
		await open('metadata');
		expect(eyebrow().textContent).toContain('Step 5 of 9');
		expect(screen.getByText('Optional')).toBeTruthy();
		expect(document.title).toBe('ARM - Set up: Identification');
	});

	it('shows Finish later on every step but account', async () => {
		const { rerender } = await open('system');
		expect(screen.getByRole('button', { name: 'Finish later' })).toBeTruthy();
		await rerender({ data: { step: 'account' } });
		await tick();
		expect(screen.queryByRole('button', { name: 'Finish later' })).toBeNull();
	});
});

describe('setup step page: changing step', () => {
	it('clears the error and the blocked reason', async () => {
		stubState.commit = async () => {
			throw new Error('boom');
		};
		const { rerender } = await open('system');
		stubState.setBlocked?.('Fix this first');
		await fireEvent.click(continueBtn());
		await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('boom'));
		expect(screen.getByText('Fix this first')).toBeTruthy();
		await rerender({ data: { step: 'drives' } });
		await tick();
		expect(screen.queryByRole('alert')).toBeNull();
		expect(screen.queryByText('Fix this first')).toBeNull();
	});

	it('moves focus to the heading after the next tick', async () => {
		const { rerender } = await open('system');
		await tick();
		(document.activeElement as HTMLElement | null)?.blur();
		await rerender({ data: { step: 'drives' } });
		await tick();
		await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('heading', { level: 1 })));
	});

	it('does not fail when the page is torn down before the focus tick', async () => {
		fetchSetup.mockReturnValue(new Promise(() => {}));
		const { unmount } = renderComponent(Page, { props: { data: { step: 'system' } } });
		unmount();
		await tick();
		await tick();
		expect(document.activeElement).toBe(document.body);
	});
});

describe('setup step page: blocked reason', () => {
	it('shows the reason in the footer and disables Continue, until cleared', async () => {
		await open('system');
		stubState.setBlocked?.('Pick a drive first');
		await waitFor(() => expect(screen.getByText('Pick a drive first')).toBeTruthy());
		expect((continueBtn() as HTMLButtonElement).disabled).toBe(true);
		stubState.setBlocked?.(null);
		await waitFor(() => expect((continueBtn() as HTMLButtonElement).disabled).toBe(false));
		expect(screen.queryByText('Pick a drive first')).toBeNull();
	});
});

describe('setup step page: Continue', () => {
	it.each([
		['done', 'done'],
		['attention', 'attention'],
		['skip', 'skipped']
	] as const)('records a %s commit as %s and moves to the next step', async (result, recorded) => {
		stubState.commit = async () => result;
		await open('system');
		await fireEvent.click(continueBtn());
		await waitFor(() => expect(goto).toHaveBeenCalledWith('/setup/drives'));
		expect(putSetupStep).toHaveBeenCalledWith('system', recorded);
	});

	it('records nothing and stays put when the commit returns false', async () => {
		stubState.commit = async () => false;
		await open('system');
		await fireEvent.click(continueBtn());
		await waitFor(() => expect((continueBtn() as HTMLButtonElement).disabled).toBe(false));
		expect(putSetupStep).not.toHaveBeenCalled();
		expect(completeSetup).not.toHaveBeenCalled();
		expect(goto).not.toHaveBeenCalled();
	});

	it('completes setup and goes to the dashboard on the finish step', async () => {
		await open('finish');
		await fireEvent.click(screen.getByRole('button', { name: /Go to dashboard/ }));
		await waitFor(() => expect(goto).toHaveBeenCalledWith('/'));
		expect(completeSetup).toHaveBeenCalledTimes(1);
		expect(putSetupStep).not.toHaveBeenCalled();
	});

	it("shows an Error's message when the commit rejects", async () => {
		stubState.commit = async () => {
			throw new Error('Key rejected');
		};
		await open('system');
		await fireEvent.click(continueBtn());
		expect((await screen.findByRole('alert')).textContent).toBe('Key rejected');
		expect(goto).not.toHaveBeenCalled();
	});

	it('shows a generic message when the commit rejects with a non-Error', async () => {
		stubState.commit = () => Promise.reject('nope');
		await open('system');
		await fireEvent.click(continueBtn());
		expect((await screen.findByRole('alert')).textContent).toBe('Saving this step failed');
	});

	it('commits once when Continue is clicked twice while the first is in flight', async () => {
		const pending = deferred<'done'>();
		const commit = vi.fn(() => pending.promise);
		stubState.commit = commit;
		await open('system');
		const btn = continueBtn();
		void fireEvent.click(btn);
		void fireEvent.click(btn);
		await tick();
		pending.resolve('done');
		await waitFor(() => expect(goto).toHaveBeenCalledWith('/setup/drives'));
		expect(commit).toHaveBeenCalledTimes(1);
		expect(putSetupStep).toHaveBeenCalledTimes(1);
	});

	it('clears the last error when Continue is pressed again', async () => {
		const retry = deferred<'done'>();
		stubState.commit = async () => {
			throw new Error('first failure');
		};
		await open('system');
		await fireEvent.click(continueBtn());
		await screen.findByRole('alert');
		stubState.commit = () => retry.promise;
		await fireEvent.click(continueBtn());
		await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
		retry.resolve('done');
		await waitFor(() => expect(goto).toHaveBeenCalledWith('/setup/drives'));
	});
});

describe('setup step page: Skip for now', () => {
	it('records the step as skipped and moves to the next step', async () => {
		await open('metadata');
		await fireEvent.click(skipBtn());
		await waitFor(() => expect(goto).toHaveBeenCalledWith('/setup/discs'));
		expect(putSetupStep).toHaveBeenCalledWith('metadata', 'skipped');
	});

	it("shows an Error's message when recording the skip fails", async () => {
		putSetupStep.mockRejectedValue(new Error('server said no'));
		await open('metadata');
		await fireEvent.click(skipBtn());
		expect((await screen.findByRole('alert')).textContent).toBe('server said no');
		expect(goto).not.toHaveBeenCalled();
	});

	it('shows a generic message when recording the skip fails with a non-Error', async () => {
		putSetupStep.mockRejectedValue('nope');
		await open('metadata');
		await fireEvent.click(skipBtn());
		expect((await screen.findByRole('alert')).textContent).toBe('Skipping this step failed');
	});

	it('records the skip once when clicked twice while the first is in flight', async () => {
		const pending = deferred<SetupView>();
		putSetupStep.mockReturnValue(pending.promise);
		await open('metadata');
		const btn = skipBtn();
		void fireEvent.click(btn);
		void fireEvent.click(btn);
		await tick();
		pending.resolve(makeView());
		await waitFor(() => expect(goto).toHaveBeenCalledWith('/setup/discs'));
		expect(putSetupStep).toHaveBeenCalledTimes(1);
	});

	it('does not clear an earlier error before skipping', async () => {
		stubState.commit = async () => {
			throw new Error('earlier failure');
		};
		const pending = deferred<SetupView>();
		await open('metadata');
		await fireEvent.click(continueBtn());
		await screen.findByRole('alert');
		putSetupStep.mockReturnValue(pending.promise);
		await fireEvent.click(skipBtn());
		await waitFor(() => expect(putSetupStep).toHaveBeenCalledTimes(1));
		expect(screen.getByRole('alert').textContent).toBe('earlier failure');
		pending.resolve(makeView());
		await waitFor(() => expect(goto).toHaveBeenCalledWith('/setup/discs'));
		expect(screen.getByRole('alert').textContent).toBe('earlier failure');
	});
});

describe('setup step page: navigation', () => {
	it('Back goes to the previous step', async () => {
		await open('drives');
		await fireEvent.click(backBtn());
		expect(goto).toHaveBeenCalledWith('/setup/system');
	});

	it('selecting a step in the stepper goes to that step', async () => {
		await open('drives', makeView({ progress: { system: { state: 'done' } } as SetupView['progress'] }));
		const nav = screen.getByRole('navigation', { name: 'Setup steps' });
		await fireEvent.click(within(nav).getAllByRole('button', { name: /System check/ })[0]);
		expect(goto).toHaveBeenCalledWith('/setup/system');
	});
});

describe('setup step page: busy state', () => {
	it('disables the footer buttons and shows Saving... while a commit is pending', async () => {
		const pending = deferred<'done'>();
		stubState.commit = () => pending.promise;
		await open('metadata');
		await fireEvent.click(continueBtn());
		await waitFor(() => expect(screen.getByText('Saving...')).toBeTruthy());
		expect((continueBtn() as HTMLButtonElement).disabled).toBe(true);
		expect((skipBtn() as HTMLButtonElement).disabled).toBe(true);
		expect((backBtn() as HTMLButtonElement).disabled).toBe(true);
		pending.resolve('done');
		await waitFor(() => expect(screen.queryByText('Saving...')).toBeNull());
	});
});
