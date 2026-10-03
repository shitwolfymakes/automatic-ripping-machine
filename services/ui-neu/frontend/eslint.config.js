import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import svelte from 'eslint-plugin-svelte';
import { defineConfig } from 'eslint/config';
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
		// Test mocks and fixtures use `any` freely.
		files: ['**/__tests__/**', '**/*.test.ts', '**/*.spec.ts', 'tests/**'],
		rules: {
			'@typescript-eslint/no-explicit-any': 'off'
		}
	},
	prettier
);
