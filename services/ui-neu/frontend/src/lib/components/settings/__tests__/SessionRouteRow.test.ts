import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import type { SessionRouteView, SessionView } from '$lib/types/api.gen';

// The coverage tool reports one branch on a session's `<option value={s.id}>`,
// which is Svelte's, not the component's: it compiles the attribute to
// `(option.__value = s.id) ?? ''`, and a session's id is never null.

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		isGuest: derived(_role, (r) => r === 'guest'),
		// Test-only helper, not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});

import SessionRouteRow from '../SessionRouteRow.svelte';

async function setRole(r: string | null) {
	const auth = (await import('$lib/stores/auth')) as unknown as { __setRole: (r: string | null) => void };
	auth.__setRole(r);
}

const builtin = { id: 'ses_music', name: 'Music -> FLAC', is_builtin: true } as unknown as SessionView;
const custom = { id: 'ses_custom', name: 'My rip', is_builtin: false } as unknown as SessionView;

const route: SessionRouteView = {
	id: 'srt_a',
	media_type: 'music',
	disc_type: 'cd',
	session_id: 'ses_music',
	created_at: null,
	updated_at: null
};

function renderRow(overrides: Record<string, unknown> = {}) {
	const onchange = vi.fn();
	const onclear = vi.fn();
	const { rerender } = renderComponent(SessionRouteRow, {
		props: {
			rowId: 'music/cd',
			mediaLabel: 'Music',
			scopeLabel: 'CD',
			route,
			options: [builtin, custom],
			busy: false,
			onchange,
			onclear,
			...overrides
		}
	});
	return { onchange, onclear, rerender };
}

afterEach(async () => {
	cleanup();
	await setRole('admin');
});

describe('SessionRouteRow', () => {
	it('names the select by media and scope and lists none plus each session', () => {
		renderRow();
		const select = screen.getByRole('combobox', { name: 'Music / CD session' }) as HTMLSelectElement;
		expect(select.id).toBe('route-music/cd');
		expect(screen.getByText('CD')).toBeTruthy();
		expect(Array.from(select.options).map((o) => o.textContent)).toEqual([
			'- none -',
			'Music -> FLAC (built-in)',
			'My rip'
		]);
	});

	it('selects the routed session', () => {
		renderRow();
		expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe('ses_music');
	});

	it('keeps the routed session selected when only busy changes', async () => {
		const { rerender } = renderRow();
		await rerender({ busy: true });
		const select = screen.getByRole('combobox') as HTMLSelectElement;
		expect(select.value).toBe('ses_music');
		expect(select.disabled).toBe(true);
	});

	it('selects none with no route', () => {
		renderRow({ route: undefined });
		expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe('');
	});

	it('enables the select for an admin that is not busy', () => {
		renderRow();
		expect((screen.getByRole('combobox') as HTMLSelectElement).disabled).toBe(false);
	});

	it('disables the select for a non-admin', async () => {
		await setRole('user');
		renderRow();
		expect((screen.getByRole('combobox') as HTMLSelectElement).disabled).toBe(true);
	});

	it('disables the select while busy', () => {
		renderRow({ busy: true });
		expect((screen.getByRole('combobox') as HTMLSelectElement).disabled).toBe(true);
	});

	it('disables the select with no options', () => {
		renderRow({ options: [] });
		expect((screen.getByRole('combobox') as HTMLSelectElement).disabled).toBe(true);
	});

	it('calls onchange with the chosen session id', async () => {
		const { onchange } = renderRow();
		await fireEvent.change(screen.getByRole('combobox'), { target: { value: 'ses_custom' } });
		expect(onchange).toHaveBeenCalledWith('ses_custom');
	});

	it('shows Clear for an admin with a route and calls onclear with the route', async () => {
		const { onclear } = renderRow();
		const button = screen.getByRole('button', { name: 'Clear Music / CD route' }) as HTMLButtonElement;
		expect(button.disabled).toBe(false);
		await fireEvent.click(button);
		expect(onclear).toHaveBeenCalledWith(route);
	});

	it('hides Clear with no route', () => {
		renderRow({ route: undefined });
		expect(screen.queryByRole('button')).toBeNull();
	});

	it('hides Clear for a non-admin', async () => {
		await setRole('user');
		renderRow();
		expect(screen.queryByRole('button')).toBeNull();
	});

	it('disables Clear while busy', () => {
		renderRow({ busy: true });
		expect((screen.getByRole('button') as HTMLButtonElement).disabled).toBe(true);
	});
});
