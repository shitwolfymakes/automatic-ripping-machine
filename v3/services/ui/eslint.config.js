// ESLint flat config (ESLint 9). Mirrors create-vue's scaffolded setup:
// vue + typescript-eslint stacks layered, then `skipFormatting` from
// `@vue/eslint-config-prettier` disables stylistic rules so Prettier
// owns formatting alone.

import pluginVue from 'eslint-plugin-vue'
import vueTsEslintConfig from '@vue/eslint-config-typescript'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'

export default [
  {
    name: 'arm-ui/files-to-lint',
    files: ['**/*.{ts,mts,tsx,vue}'],
  },
  {
    name: 'arm-ui/files-to-ignore',
    ignores: [
      '**/dist/**',
      '**/dist-ssr/**',
      '**/coverage/**',
      '**/node_modules/**',
      'src/api/generated.ts',
      'openapi.snapshot.json',
    ],
  },
  ...pluginVue.configs['flat/essential'],
  ...vueTsEslintConfig(),
  skipFormatting,
  {
    name: 'arm-ui/project-rules',
    rules: {
      // Allow `_unused` as an explicit-discard convention.
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      // Top-level route components are named after their page (Login, Drives,
      // Sessions). Renaming them to two-word forms would just be churn.
      'vue/multi-word-component-names': 'off',
    },
  },
]
