import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const css = readFileSync(resolve(__dirname, '../tokens.css'), 'utf8');

const COLOR_ROLES = [
	'page', 'surface', 'surface-raised', 'border', 'border-strong',
	'text', 'text-secondary', 'text-muted', 'text-faint',
	'primary', 'primary-hover', 'on-primary', 'primary-text',
	'primary-tint-1', 'primary-tint-2', 'primary-tint-3', 'backdrop',
	'danger', 'danger-soft', 'on-danger-soft',
	'warning', 'warning-soft', 'on-warning-soft',
	'success', 'success-soft', 'on-success-soft',
	'info', 'info-soft', 'on-info-soft',
	'status-scanning', 'status-ripping', 'status-transcoding', 'status-finishing', 'status-waiting', 'status-success', 'status-error',
	'accent-1', 'accent-2', 'accent-3', 'accent-4'
];
const OTHER = ['--radius', '--shadow-1', '--shadow-2', '--font-display', '--font-mono', '--motion-fast', '--motion-base', '--ease', '--control-h', '--control-h-sm'];

describe('tokens.css', () => {
	it('declares every colour role in @theme', () => {
		const theme = css.slice(css.indexOf('@theme'), css.indexOf('}', css.indexOf('@theme')));
		for (const role of COLOR_ROLES) expect(theme, role).toMatch(new RegExp(`--color-${role}:`));
	});
	it('declares the non-colour tokens', () => {
		for (const t of OTHER) expect(css).toContain(`${t}:`);
	});
	it('flips every semantic role under .dark', () => {
		const dark = css.slice(css.indexOf('.dark {'));
		for (const role of ['page', 'surface', 'surface-raised', 'border', 'border-strong', 'text', 'text-secondary', 'text-muted', 'text-faint', 'primary-text', 'backdrop', 'danger', 'danger-soft', 'on-danger-soft', 'warning', 'warning-soft', 'on-warning-soft', 'success', 'success-soft', 'on-success-soft']) {
			expect(dark, role).toMatch(new RegExp(`--color-${role}:`));
		}
	});
	it('defines the class-driven dark variant', () => {
		expect(css).toContain('@variant dark (&:where(.dark, .dark *));');
	});
	it('carries none of the migration-window legacy aliases (removed in Task 13)', () => {
		for (const alias of [
			'--color-primary-dark:',
			'--color-primary-light-bg:',
			'--color-primary-light-bg-dark:',
			'--color-primary-text-dark:',
			'--color-primary-border:',
			'--color-page-dark:',
			'--color-surface-dark:'
		]) {
			expect(css, alias).not.toContain(alias);
		}
	});
});
