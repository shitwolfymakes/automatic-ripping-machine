import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import sonarjs from 'eslint-plugin-sonarjs';
import svelte from 'eslint-plugin-svelte';
import { defineConfig } from 'eslint/config';
import unicorn from 'eslint-plugin-unicorn';
import globals from 'globals';
import ts from 'typescript-eslint';

import svelteConfig from './svelte.config.js';

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
		// Development guidelines: cognitive complexity of 15 or less (SonarQube rule S3776). SonarQube
		// for IDE does not analyse .svelte, so the same rule runs here over .ts, .js and Svelte scripts.
		plugins: { sonarjs },
		rules: {
			'sonarjs/cognitive-complexity': ['error', 15]
		}
	},
	{
		// ui-neu file layout (see the development guidelines): kebab-case modules, PascalCase components. SvelteKit route files
		// (+page, +layout) and generated or ambient declarations are exempt. Warning until the renames land.
		plugins: { unicorn },
		ignores: ['src/routes/**', '**/*.d.ts', 'src/lib/types/api.gen.ts'],
		files: ['**/*.ts', '**/*.js'],
		rules: {
			'unicorn/filename-case': ['warn', { cases: { kebabCase: true }, ignore: [/^__tests__$/, /^__fixtures__$/] }]
		}
	},
	{
		// Folders are checked kebab-case by the block above; a folder holding only .svelte files is not checked.
		plugins: { unicorn },
		files: ['**/*.svelte'],
		ignores: ['src/routes/**'],
		rules: {
			'unicorn/filename-case': [
				'warn',
				{ cases: { pascalCase: true }, checkDirectories: false, ignore: [/^__tests__$/, /^__fixtures__$/] }
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
