# ui-neu src/lib restructure codemod

Moves or renames files under `services/ui-neu/frontend` with `git mv` and rewrites every reference to them.

```bash
node devtools/ui-neu-restructure/move.mjs <mapping.json> [--dry-run] [--root <frontend dir>]
node --test devtools/ui-neu-restructure/*.test.mjs
```

`mapping.json` holds `{ "moves": [{ "from": "src/lib/utils/session-routes.ts", "to": "src/lib/sessions/routes.ts" }] }`,
paths relative to `services/ui-neu/frontend`. A `from` that names a folder moves everything under it; an explicit
file entry wins over an enclosing folder entry. Chained moves (a target that is also a source) and duplicate
targets are rejected: split them into separate runs.

## What it rewrites

- Module specifiers in `.ts`, `.js`, `.mjs` and `.svelte` files under `src/`, `tests/`, `site/` and the frontend root
  config files: every string literal that starts with `$lib/`, `./` or `../`, so `import`, `export ... from`,
  `import()`, `vi.mock()` and `vi.importActual()` are all covered. A specifier is resolved to the real file
  (alias or relative, with or without extension, `.svelte.ts` modules, `index` directory imports, `.js` for `.ts`,
  `?query` suffixes) and written back in the same style. A moved importer gets its relative specifiers recomputed.
- Path references in `*.md`, `*.mjs`, `*.js` and `*.sh` under `docs/`, `devtools/` (this folder excluded), `site/`,
  `.claude/memory/`, plus the root `CLAUDE.md`, and in code comments: repo-relative paths, frontend-relative paths
  and `$lib/` forms of each moved file or folder.
- Case-only renames go through a temporary name (`git mv a tmp; git mv tmp b`) so case-insensitive filesystems cope.

## Survivor check

After the run it re-reads the tree and fails (exit 1) listing any specifier that still resolves to a moved file's
old path, and any old path form still present in a scanned file. `--dry-run` prints the plan, evaluates the same
check against the planned content, and changes nothing. Exit 2 is a usage or mapping error.

Not followed: computed specifiers, `import.meta.glob` patterns and path strings built from parts. Files outside the
scanned roots (for example `services/ui-neu/frontend/e2e/`) are not scanned.
