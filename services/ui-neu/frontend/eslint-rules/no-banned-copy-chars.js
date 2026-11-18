// UI copy uses plain ASCII punctuation: no em-dashes, middle dots, ellipsis
// characters, curly quotes or unicode symbols standing in for icons. Letters
// with accents (language names, titles) are fine, as are the no-break space
// and the degree sign. Checks the decoded value of every string the UI can
// render: JS/TS string and template literals, and Svelte text and attribute
// values, so `&mdash;` is caught as well as a literal `—`. Comments are not
// strings, so they are never checked.

const ALLOWED_NON_ASCII = new Set([' ', '°']);
const LETTER_OR_MARK = /[\p{L}\p{M}]/u;

const ADVICE = new Map([
	['—', 'use ":", "," or "-"'],
	['–', 'use "-"'],
	['·', 'use "|" between fields, or "," in prose'],
	['•', 'use "|" between fields, or "," in prose'],
	['…', 'use "..."'],
	['×', 'use <CloseButton> for a close button, or "x"'],
	['≥', 'use ">="'],
	['≤', 'use "<="'],
	['‘', "use a straight quote (')"],
	['’', "use a straight quote (')"],
	['“', 'use a straight quote (")'],
	['”', 'use a straight quote (")']
]);
const ICON_ADVICE = 'use a <Glyph> icon';

/** The first character in `text` that UI copy may not contain, or null. */
export function findBannedChar(text) {
	for (const ch of text) {
		if (ch.charCodeAt(0) < 0x80 || ALLOWED_NON_ASCII.has(ch) || LETTER_OR_MARK.test(ch)) continue;
		return ch;
	}
	return null;
}

/** How to replace a banned character. */
export function adviceFor(ch) {
	return ADVICE.get(ch) ?? ICON_ADVICE;
}

function codePoint(ch) {
	return 'U+' + ch.codePointAt(0).toString(16).toUpperCase().padStart(4, '0');
}

/** The decoded text of a string-bearing node, or null for any other node.
 *  A <style> block's raw CSS reaches the rule as a text node; it is not copy. */
function stringValue(node) {
	if (node.parent?.type === 'SvelteStyleElement') return null;
	if (node.type === 'TemplateElement') return node.value.cooked ?? null;
	return typeof node.value === 'string' ? node.value : null;
}

export default {
	meta: {
		type: 'problem',
		docs: { description: 'Disallow em-dashes, unicode symbols and other non-ASCII punctuation in UI strings' },
		schema: [],
		messages: {
			banned: 'UI copy must not contain "{{ch}}" ({{code}}): {{advice}}.'
		}
	},
	create(context) {
		function check(node) {
			const text = stringValue(node);
			const ch = text === null ? null : findBannedChar(text);
			if (ch === null) return;
			context.report({ node, messageId: 'banned', data: { ch, code: codePoint(ch), advice: adviceFor(ch) } });
		}
		return { Literal: check, TemplateElement: check, SvelteText: check, SvelteLiteral: check };
	}
};
