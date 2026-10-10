import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { BLOCKS } from './blocks-registry';

const dir = resolve(__dirname, '../components');
describe('block files', () => {
	for (const [file, classes] of Object.entries(BLOCKS)) {
		it(`${file}.css declares its block and parts with a header comment`, () => {
			const p = resolve(dir, `${file}.css`);
			expect(existsSync(p), p).toBe(true);
			const css = readFileSync(p, 'utf8');
			expect(css.trimStart().startsWith('/*'), 'header comment').toBe(true);
			for (const c of classes) expect(css, c).toMatch(new RegExp(`${c.replace('.', '\\.')}[\\s,:{\\[]`));
			expect(css, 'no raw colours').not.toMatch(/#[0-9a-f]{3,8}\b|rgb\(/i);
		});
	}
	it('layout.css declares the helpers', () => {
		const css = readFileSync(resolve(__dirname, '../layout.css'), 'utf8');
		for (const c of ['.stack', '.stack-sm', '.stack-lg', '.cluster', '.grid-2', '.grid-3', '.page', '.page-header', '.page-title', '.split']) expect(css, c).toContain(c);
	});
	it('app.css imports every block file', () => {
		const app = readFileSync(resolve(__dirname, '../../../app.css'), 'utf8');
		for (const file of Object.keys(BLOCKS)) expect(app, file).toContain(`components/${file}.css`);
	});
});
