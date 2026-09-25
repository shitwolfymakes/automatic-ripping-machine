import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const styles = resolve(__dirname, '..');
const css = readFileSync(resolve(styles, 'components/docs-prose.css'), 'utf8');

describe('docs-prose block', () => {
	it('is imported by app.css', () => {
		expect(readFileSync(resolve(styles, '../../app.css'), 'utf8')).toContain('@import "./lib/styles/components/docs-prose.css";');
	});
	it('lives in the components layer with no raw colours and no !important', () => {
		expect(css).toMatch(/@layer components \{/);
		expect(css).not.toMatch(/#[0-9a-f]{3,8}\b|rgb\(|hsl\(/i);
		expect(css).not.toContain('!important');
	});
	it('switches Shiki colours with the dark class', () => {
		expect(css).toContain('.docs-prose .shiki span { color: var(--shiki-light); }');
		expect(css).toContain('.dark .docs-prose .shiki span { color: var(--shiki-dark); }');
	});
});
