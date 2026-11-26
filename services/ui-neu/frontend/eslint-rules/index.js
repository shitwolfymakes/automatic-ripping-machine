// ui-neu's own ESLint rules (the `arm` plugin in eslint.config.js).
import noBannedCopyChars from './no-banned-copy-chars.js';
import noInlineGlyph from './no-inline-glyph.js';

export default {
	meta: { name: 'eslint-plugin-arm' },
	rules: {
		'no-banned-copy-chars': noBannedCopyChars,
		'no-inline-glyph': noInlineGlyph
	}
};
