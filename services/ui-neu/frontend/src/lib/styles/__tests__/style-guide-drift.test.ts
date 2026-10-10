import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { BLOCKS } from './blocks-registry';

// The style guide is manually written but may not silently rot: this suite
// fails, naming exactly what is missing, whenever the system grows a token,
// a block, or a block class that neither guide document mentions. It is the
// documentation twin of the openapi-drift job.
//
// Sources of truth:            what must stay current:
//   tokens.css                   docs/ui-neu-style-guide.md (names)
//   blocks-registry.ts           static/style-guide.html   (names + swatch values)
//   components/*.css file set    both

const styles = resolve(__dirname, '..');
const repoRoot = resolve(__dirname, '../../../../../../..');
const tokensCss = readFileSync(resolve(styles, 'tokens.css'), 'utf8');
const mdRaw = readFileSync(resolve(repoRoot, 'docs/ui-neu-style-guide.md'), 'utf8');
const htmlRaw = readFileSync(resolve(__dirname, '../../../../static/style-guide.html'), 'utf8');

// The md tables use three compact family conventions; expand them so a
// literal token-name search still matches:
//   --color-status-{ripping,transcoding}  ->  each member
//   --color-accent-1..4                   ->  each number
//   --color-primary-tint-1/2/3            ->  each number
function expandFamilies(text: string): string {
	let out = text;
	out = out.replace(/([-\w]+)\{([^}]+)\}/g, (_, stem: string, body: string) =>
		body.split(',').map((part) => stem + part.trim()).join(' ')
	);
	out = out.replace(/([-\w]+-)(\d+)\.\.(\d+)/g, (_, stem: string, a: string, b: string) => {
		const names: string[] = [];
		for (let i = Number(a); i <= Number(b); i++) names.push(stem + i);
		return names.join(' ');
	});
	out = out.replace(/([-\w]+-)(\d+)((?:\/\d+)+)/g, (_, stem: string, first: string, rest: string) =>
		[first, ...rest.split('/').filter(Boolean)].map((n) => stem + n).join(' ')
	);
	return out;
}
const docs = expandFamilies(mdRaw) + '\n' + expandFamilies(htmlRaw);

describe('style guide drift', () => {
	it('every semantic token name appears in the guide', () => {
		const names = [...tokensCss.matchAll(/^\s*(--[a-z][\w-]*)\s*:/gim)]
			.map((m) => m[1])
			// primitives are private; --radius is documented through its scale
			.filter((n) => !n.startsWith('--color-p-'));
		const missing = [...new Set(names)].filter((n) => !docs.includes(n));
		expect(missing, `tokens undocumented in docs/ui-neu-style-guide.md or static/style-guide.html: ${missing.join(', ')}`).toEqual([]);
	});

	it('every rgb-valued colour token value appears in the rendered guide swatches', () => {
		// Only plain rgb()/space-syntax literals; mixes and var() chains render
		// through the page's own tokens. Normalise whitespace and `0.x` alpha.
		const norm = (s: string) => s.replace(/\s+/g, '').replace(/\/0\./g, '/.');
		const html = norm(htmlRaw);
		const values = [...tokensCss.matchAll(/^\s*--color-[\w-]+\s*:\s*(rgb\([^)]*\))\s*;/gim)].map((m) => norm(m[1]));
		const missing = [...new Set(values)].filter((v) => !html.includes(v));
		expect(missing, `token values missing from static/style-guide.html swatches: ${missing.join(', ')}`).toEqual([]);
	});

	it('every block and block class appears in the guide', () => {
		const missing: string[] = [];
		for (const [block, classes] of Object.entries(BLOCKS)) {
			if (!docs.includes(block)) missing.push(block);
			// the class stem can differ from the file name (button -> .btn)
			const stem = classes[0].slice(1);
			for (const cls of classes) {
				const full = cls.slice(1); // panel-title
				const short = full === stem ? full : full.replace(stem, ''); // -title
				if (!docs.includes(full) && !(short !== full && docs.includes(short))) missing.push(cls);
			}
		}
		expect(missing, `block classes undocumented: ${missing.join(', ')}`).toEqual([]);
	});

	it('every block file is in the registry (a new block cannot dodge the contract)', () => {
		const files = readdirSync(resolve(styles, 'components'))
			.filter((f) => f.endsWith('.css'))
			.map((f) => f.replace(/\.css$/, ''));
		const unregistered = files.filter((f) => !(f in BLOCKS));
		expect(unregistered, `components/*.css without a blocks-registry entry: ${unregistered.join(', ')}`).toEqual([]);
	});
});
