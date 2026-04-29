# arm-ui

Vue 3 + Vite + Pinia + vue-router SPA, served by nginx as a reverse proxy in
front of `arm-backend`. Phase 5 walking skeleton: login, forced password
change, jobs list (REST polling, no WS yet), drives, sessions (read-only),
config form, diagnostics.

## Layout

```text
src/
├── main.ts                 # entrypoint
├── App.vue                 # root, picks AppShell vs bare layout from route meta
├── api/
│   ├── client.ts           # fetch wrapper, JWT in localStorage, 401 → reset
│   ├── types.ts            # hand-typed wire schemas the views read
│   └── generated.ts        # openapi-typescript output (gitignored)
├── stores/
│   ├── auth.ts             # token, user, password_must_change
│   └── jobs.ts             # jobs list with 5s polling
├── router/index.ts         # routes + nav guard
├── views/                  # one .vue per page
└── components/AppShell.vue # top nav
```

## Local development

```sh
cd v3/services/ui
npm install
npm run dev
# Vite serves http://localhost:5173 and proxies /api + /ws to https://localhost:8443
# (which requires the backend to be running on the host with port 8443 exposed).
```

For the simpler path, build the container:

```sh
cd v3
docker compose up -d arm-backend arm-ui
# https://localhost:8081/
```

## OpenAPI snapshot

`openapi.snapshot.json` is committed and is the input to `openapi-typescript`
during the Docker build (`npm run openapi-types`). Regenerate after every
`arm_common/schemas/` change:

```sh
cd v3
DATABASE_URL=postgresql://x:x@localhost/x ARM_SERVICE_TOKEN=tok \
  uv run python -c \
  "from arm_backend.main import app; import json; print(json.dumps(app.openapi(), indent=2))" \
  > services/ui/openapi.snapshot.json
```

The snapshot is consumed by the build step; mismatch ≠ runtime error today
(we hand-roll types in `src/api/types.ts`), but Phase 14 CI will diff the
checked-in snapshot against the live `app.openapi()` and fail the build on
drift, so keep them in sync.

## Tests

```sh
npm test
```

Vitest covers the auth store (login / logout / 401 reset) and router guards
(anonymous → /login, must-change → /change-password). No Playwright by
design — see `docs/arch/05-cross-cutting.md § Testing strategy`.

## Browser cert warning

Browsers don't trust the internal CA by default. Either click through once,
or import `~/arm/certs/arm-ca.crt` into your OS / browser trust store to
silence the warning across every device on your LAN. See
`docs/arch/05-cross-cutting.md § Transport (TLS)`.
