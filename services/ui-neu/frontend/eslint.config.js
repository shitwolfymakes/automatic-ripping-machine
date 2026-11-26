import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import sonarjs from 'eslint-plugin-sonarjs';
import svelte from 'eslint-plugin-svelte';
import { defineConfig } from 'eslint/config';
import unicorn from 'eslint-plugin-unicorn';
import globals from 'globals';
import ts from 'typescript-eslint';

import arm from './eslint-rules/index.js';

import svelteConfig from './svelte.config.js';

// lucide-svelte icons that the shared Glyph component already draws. Each has a Glyph name to use instead. Disc3 is
// left out: VideoTypeIcon draws it as one of a set of lucide media icons that Glyph has no match for.
const LUCIDE_WITH_GLYPH = {
	ArrowLeft: 'arrow-left',
	ArrowRight: 'arrow-right',
	Bell: 'bell',
	Check: 'check',
	CheckCircle: 'check-circle',
	CircleCheck: 'check-circle',
	ChevronDown: 'chevron-down',
	ChevronRight: 'chevron-right',
	ChevronUp: 'chevron-up',
	CircleHelp: 'question-circle',
	CircleMinus: 'minus-circle',
	CircleX: 'x-circle',
	Clock: 'clock',
	Copy: 'copy',
	Cpu: 'cpu',
	Download: 'download',
	ExternalLink: 'external-link',
	Eye: 'eye',
	EyeOff: 'eye-off',
	Folder: 'folder',
	HardDrive: 'hard-drive',
	Info: 'info',
	Key: 'key',
	Loader: 'loader',
	LoaderCircle: 'loader',
	Lock: 'lock',
	Moon: 'moon',
	RefreshCw: 'refresh',
	Settings: 'gear',
	ShieldCheck: 'shield-check',
	Sun: 'sun',
	TriangleAlert: 'warning',
	X: 'x',
	XCircle: 'x-circle'
};
const lucideGlyphImports = Object.entries(LUCIDE_WITH_GLYPH).map(([importName, glyph]) => ({
	name: 'lucide-svelte',
	importNames: [importName],
	message: `Glyph draws this icon: use <Glyph name="${glyph}" />.`
}));

export default defineConfig(
	{
		ignores: [
			'.svelte-kit/',
			'build/',
			'node_modules/',
			'static/',
			'coverage/',
			'src/lib/types/api.gen.ts',
			'test-results/',
			'playwright-report/',
			'blob-report/',
			'playwright/.cache/'
		]
	},
	js.configs.recommended,
	ts.configs.recommended,
	svelte.configs.recommended,
	svelte.configs.prettier,
	{
		languageOptions: {
			globals: { ...globals.browser, ...globals.node }
		}
	},
	{
		files: ['**/*.svelte', '**/*.svelte.ts', '**/*.svelte.js'],
		languageOptions: {
			parserOptions: {
				parser: ts.parser,
				extraFileExtensions: ['.svelte'],
				svelteConfig
			}
		}
	},
	{
		rules: {
			// The app is served at / with no kit.paths.base, so plain hrefs and goto() paths are already correct.
			'svelte/no-navigation-without-resolve': 'off',
			'@typescript-eslint/no-unused-vars': [
				'error',
				{ argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' }
			],
			'@typescript-eslint/no-explicit-any': 'error'
		}
	},
	{
		// Correctness and consistency guards. Each passed, or was brought to pass, when added; keep it that way.
		rules: {
			eqeqeq: ['error', 'always', { null: 'ignore' }],
			// warn and error stay: they report real failures to the browser console.
			'no-console': ['error', { allow: ['warn', 'error'] }],
			'object-shorthand': 'error',
			'no-param-reassign': 'error',
			// import() types stay allowed: vi.importActual<typeof import('...')>() needs them.
			'@typescript-eslint/consistent-type-imports': ['error', { disallowTypeAnnotations: false }],
			'svelte/block-lang': ['error', { script: 'ts' }],
			'svelte/no-target-blank': 'error',
			// A <button> with no type submits the form it sits in.
			'svelte/button-has-type': 'error'
		}
	},
	{
		// A non-null assertion turns a missing value into a crash further on: check for it instead. Tests assert freely.
		files: ['src/**/*.ts', 'src/**/*.svelte'],
		ignores: ['**/__tests__/**', '**/__fixtures__/**', '**/*.test.ts', '**/*.spec.ts'],
		rules: { '@typescript-eslint/no-non-null-assertion': 'error' }
	},
	{
		// Development guidelines: cognitive complexity of 15 or less (SonarQube rule S3776). SonarQube
		// for IDE does not analyse .svelte, so the same rule runs here over .ts, .js and Svelte scripts.
		plugins: { sonarjs },
		rules: {
			'sonarjs/cognitive-complexity': ['error', 15],
			'sonarjs/no-identical-functions': 'error',
			'sonarjs/no-all-duplicated-branches': 'error',
			'sonarjs/no-collapsible-if': 'error',
			'sonarjs/prefer-single-boolean-return': 'error'
		}
	},
	{
		// ui-neu file layout (see the development guidelines): kebab-case modules, PascalCase components. SvelteKit route files
		// (+page, +layout) and generated or ambient declarations are exempt.
		plugins: { unicorn },
		ignores: ['src/routes/**', '**/*.d.ts', 'src/lib/types/api.gen.ts'],
		files: ['**/*.ts', '**/*.js'],
		rules: {
			'unicorn/filename-case': ['error', { cases: { kebabCase: true }, ignore: [/^__tests__$/, /^__fixtures__$/] }]
		}
	},
	{
		// Folders are checked kebab-case by the block above; a folder holding only .svelte files is not checked.
		plugins: { unicorn },
		files: ['**/*.svelte'],
		ignores: ['src/routes/**'],
		rules: {
			'unicorn/filename-case': [
				'error',
				{ cases: { pascalCase: true }, checkDirectories: false, ignore: [/^__tests__$/, /^__fixtures__$/] }
			]
		}
	},
	{
		// UI copy and icons (see the ui-neu conventions): no em-dashes or unicode symbols in strings the UI renders, no
		// inline copies of a Glyph path, and no lucide icon that Glyph already draws. Tests may assert on any text, and fixtures copy backend data as is.
		plugins: { arm },
		files: ['src/**/*.ts', 'src/**/*.svelte'],
		ignores: ['**/__tests__/**', '**/__fixtures__/**', '**/*.test.ts', '**/*.spec.ts', 'src/lib/types/api.gen.ts'],
		rules: {
			'arm/no-banned-copy-chars': 'error',
			'arm/no-inline-glyph': 'error',
			'no-restricted-imports': ['error', { paths: lucideGlyphImports }]
		}
	},
	{
		// Layering: lib code outside components/ never imports from components/. Shared pieces live in lib/ui, lib/__fixtures__ etc.
		files: ['src/lib/**/*.ts', 'src/lib/**/*.js'],
		ignores: ['src/lib/components/**'],
		rules: {
			'no-restricted-imports': [
				'error',
				{
					// Repeats the lucide list from the block above: a later block's options replace an earlier one's.
					paths: lucideGlyphImports,
					patterns: [
						{
							regex: '(^\\$lib/components(/|$))|((^|/)components/)',
							message: 'lib code outside components/ must not import from components/.'
						}
					]
				}
			]
		}
	},
	{
		// Test mocks and fixtures use `any` freely.
		files: ['**/__tests__/**', '**/*.test.ts', '**/*.spec.ts', 'tests/**'],
		rules: {
			'@typescript-eslint/no-explicit-any': 'off'
		}
	},
	prettier
);
