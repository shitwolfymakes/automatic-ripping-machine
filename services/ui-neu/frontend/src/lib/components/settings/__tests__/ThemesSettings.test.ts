import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import type { Writable } from 'svelte/store';
import { renderComponent, screen, cleanup, fireEvent, within } from '$lib/testing/render';
import ThemesSettings from '../ThemesSettings.svelte';
import { UserThemes } from '$lib/stores/user-themes.svelte';
import { theme, toggleTheme } from '$lib/stores/theme';
import { colorScheme, allSchemes, schemeLocksMode } from '$lib/stores/color-scheme';

vi.mock('$lib/api/themes', () => ({
	uploadTheme: vi.fn(() => Promise.resolve()),
	deleteTheme: vi.fn(() => Promise.resolve())
}));

vi.mock('$lib/stores/theme', async () => {
	const { writable } = await import('svelte/store');
	return { theme: writable('dark'), toggleTheme: vi.fn() };
});

vi.mock('$lib/stores/color-scheme', async () => {
	const { writable } = await import('svelte/store');
	return {
		colorScheme: writable('default'),
		COLOR_SCHEMES: [],
		schemeLocksMode: writable(false),
		allSchemes: writable([]),
		loadThemesFromApi: vi.fn()
	};
});

const builtin = (id: string, label: string, over: Record<string, unknown> = {}) => ({
	id,
	label,
	swatch: '#123456',
	tokens: {},
	builtin: true,
	...over
});

const userTheme = (id: string, label: string, over: Record<string, unknown> = {}) => ({
	id,
	label,
	swatch: '#abcdef',
	tokens: {},
	builtin: false,
	...over
});

function setSchemes(list: unknown[]) {
	allSchemes.set(list as never);
}

// The mocked schemeLocksMode is a writable, though the real one is derived.
function setLocked(locked: boolean) {
	(schemeLocksMode as unknown as Writable<boolean>).set(locked);
}

function renderThemes(themes = new UserThemes()) {
	renderComponent(ThemesSettings, { themes });
	return themes;
}

beforeEach(() => {
	vi.mocked(toggleTheme).mockClear();
	theme.set('dark');
	colorScheme.set('default');
	setLocked(false);
	setSchemes([]);
});
afterEach(() => cleanup());

describe('ThemesSettings built-in swatches', () => {
	it('shows a tooltip only for a swatch with a description', () => {
		setSchemes([builtin('default', 'Default', { description: 'The classic look' }), builtin('plain', 'Plain')]);
		renderThemes();
		expect(screen.getByText('The classic look')).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /Plain/ }).querySelector('.scheme-swatch-tooltip')).toBeNull();
	});

	it('marks the active scheme selected and selects another on click', async () => {
		setSchemes([builtin('default', 'Default'), builtin('plain', 'Plain')]);
		renderThemes();
		const def = screen.getByRole('button', { name: /Default/ });
		const plain = screen.getByRole('button', { name: /Plain/ });
		expect(def).toHaveAttribute('data-selected', 'true');
		expect(plain).toHaveAttribute('data-selected', 'false');
		await fireEvent.click(plain);
		expect(get(colorScheme)).toBe('plain');
		expect(plain).toHaveAttribute('data-selected', 'true');
		expect(def).toHaveAttribute('data-selected', 'false');
	});
});

describe('ThemesSettings user themes', () => {
	it('hides the User Themes card when there are none', () => {
		setSchemes([builtin('default', 'Default')]);
		renderThemes();
		expect(screen.queryByText('User Themes')).not.toBeInTheDocument();
	});

	it('lists user themes with an author line only when the theme has an author', () => {
		setSchemes([
			builtin('default', 'Default'),
			userTheme('mine', 'Mine', { author: 'Ann' }),
			userTheme('anon', 'Anon')
		]);
		renderThemes();
		expect(screen.getByText('User Themes')).toBeInTheDocument();
		expect(screen.getByText('by Ann')).toBeInTheDocument();
		expect(screen.getAllByText(/^by /)).toHaveLength(1);
	});

	it('selects a user theme on click', async () => {
		setSchemes([userTheme('mine', 'Mine')]);
		renderThemes();
		await fireEvent.click(screen.getByRole('button', { name: /Mine/ }));
		expect(get(colorScheme)).toBe('mine');
	});

	it('deletes a user theme by its id and label', async () => {
		setSchemes([userTheme('mine', 'Mine')]);
		const themes = new UserThemes();
		const spy = vi.spyOn(themes, 'deleteTheme').mockResolvedValue();
		renderThemes(themes);
		await fireEvent.click(screen.getByTitle('Delete'));
		expect(spy).toHaveBeenCalledWith('mine', 'Mine');
	});
});

describe('ThemesSettings feedback', () => {
	it('shows no feedback by default', () => {
		setSchemes([userTheme('mine', 'Mine')]);
		renderThemes();
		expect(document.querySelector('.alert')).toBeNull();
		expect(document.querySelector('.settings-page-feedback')).toBeNull();
	});

	it('shows a success feedback at the top and under the user themes', () => {
		setSchemes([userTheme('mine', 'Mine')]);
		const themes = new UserThemes();
		themes.feedback = { type: 'success', message: 'Theme "Mine" deleted' };
		renderThemes(themes);
		const alert = document.querySelector('.alert') as HTMLElement;
		expect(alert).toHaveClass('alert-success');
		expect(alert).toHaveTextContent('Theme "Mine" deleted');
		const line = document.querySelector('.settings-page-feedback') as HTMLElement;
		expect(line).toHaveAttribute('data-error', 'false');
		expect(line).toHaveTextContent('Theme "Mine" deleted');
	});

	it('shows an error feedback as a danger alert and an error line', () => {
		setSchemes([userTheme('mine', 'Mine')]);
		const themes = new UserThemes();
		themes.feedback = { type: 'error', message: 'Delete failed' };
		renderThemes(themes);
		expect(document.querySelector('.alert')).toHaveClass('alert-danger');
		expect(document.querySelector('.settings-page-feedback')).toHaveAttribute('data-error', 'true');
	});

	it('shows only the top alert when there are no user themes', () => {
		setSchemes([builtin('default', 'Default')]);
		const themes = new UserThemes();
		themes.feedback = { type: 'error', message: 'Delete failed' };
		renderThemes(themes);
		expect(screen.getByText('Delete failed')).toBeInTheDocument();
		expect(document.querySelector('.settings-page-feedback')).toBeNull();
	});
});

describe('ThemesSettings dark mode', () => {
	it('shows a lock note and no switch when the scheme locks the mode', () => {
		setLocked(true);
		renderThemes();
		expect(screen.getByText('Locked by theme')).toBeInTheDocument();
		expect(screen.queryByRole('switch')).not.toBeInTheDocument();
	});

	it('shows the switch on for dark mode', () => {
		renderThemes();
		const sw = screen.getByRole('switch', { name: 'Dark mode' });
		expect(sw).toHaveAttribute('aria-checked', 'true');
		const label = within(sw.parentElement as HTMLElement).getByText('On');
		expect(label).toHaveAttribute('data-on', 'true');
	});

	it('shows the switch off for light mode', () => {
		theme.set('light');
		renderThemes();
		const sw = screen.getByRole('switch', { name: 'Dark mode' });
		expect(sw).toHaveAttribute('aria-checked', 'false');
		const label = within(sw.parentElement as HTMLElement).getByText('Off');
		expect(label).toHaveAttribute('data-on', 'false');
	});

	it('toggles the theme from the switch', async () => {
		renderThemes();
		await fireEvent.click(screen.getByRole('switch', { name: 'Dark mode' }));
		expect(toggleTheme).toHaveBeenCalledTimes(1);
	});
});
