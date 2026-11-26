// An inline <svg> that draws a path the shared Glyph component already has is
// a copy that drifts the moment the glyph set changes: use <Glyph name="..." />.
// The glyph paths are read from the GLYPH_PATHS table in glyph-names.ts, so a
// glyph added there is enforced here with no change to this rule. An svg
// matches when its static `d` attributes, joined in order, equal a glyph's
// path (an icon split over two <path>s is still a copy).

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const DEFAULT_GLYPH_FILE = fileURLToPath(new URL('../src/lib/ui/glyph-names.ts', import.meta.url));
const ENTRY = /^\s*'?([a-z0-9-]+)'?:\s*'([^']+)'/gm;

/** Map of glyph path -> glyph name, parsed from the GLYPH_PATHS table's source. */
export function parseGlyphPaths(source) {
	const table = source.slice(source.indexOf('GLYPH_PATHS'));
	const byPath = new Map();
	for (const [, name, path] of table.replace(/:\s*\n\s*'/g, ": '").matchAll(ENTRY)) byPath.set(path, name);
	return byPath;
}

const cache = new Map();
function glyphPaths(file) {
	if (!cache.has(file)) cache.set(file, parseGlyphPaths(readFileSync(file, 'utf8')));
	return cache.get(file);
}

function elementName(node) {
	return node.type === 'SvelteElement' ? node.name.name : undefined;
}

/** The static value of a `d` attribute, or null when it is missing or dynamic. */
function staticD(pathNode) {
	const attr = pathNode.startTag.attributes.find((a) => a.type === 'SvelteAttribute' && a.key.name === 'd');
	const parts = attr?.value ?? [];
	return parts.length === 1 && parts[0].type === 'SvelteLiteral' ? parts[0].value : null;
}

/** Every <path> element inside `node`, in document order. */
function pathsIn(node, out = []) {
	for (const child of node.children ?? []) {
		if (elementName(child) === 'path') out.push(child);
		pathsIn(child, out);
	}
	return out;
}

/** The glyph an svg element copies, or null. */
export function copiedGlyph(svgNode, byPath) {
	const ds = pathsIn(svgNode).map(staticD);
	if (ds.length === 0 || ds.includes(null)) return null;
	return byPath.get(ds.join('')) ?? null;
}

export default {
	meta: {
		type: 'suggestion',
		docs: { description: 'Disallow inline SVGs that copy a path from the shared Glyph component' },
		schema: [{ type: 'object', properties: { glyphFile: { type: 'string' } }, additionalProperties: false }],
		messages: {
			copy: 'This inline <svg> copies the "{{name}}" glyph: use <Glyph name="{{name}}" /> instead.'
		}
	},
	create(context) {
		const byPath = glyphPaths(context.options[0]?.glyphFile ?? DEFAULT_GLYPH_FILE);
		return {
			SvelteElement(node) {
				if (elementName(node) !== 'svg') return;
				const name = copiedGlyph(node, byPath);
				if (name !== null) context.report({ node, messageId: 'copy', data: { name } });
			}
		};
	}
};
