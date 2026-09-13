import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig, loadEnv } from 'vite';

// `npm run dev` proxies /api and /ws to a running backend. Default is the
// local compose stack; set ARM_DEV_BACKEND (env or .env.local) to develop the
// UI against live data, e.g. ARM_DEV_BACKEND=https://192.168.0.71:8080.
export default defineConfig(({ mode }) => {
	const backend = loadEnv(mode, '.', 'ARM_').ARM_DEV_BACKEND ?? 'https://localhost:8443';
	const backendWs = backend.replace(/^http/, 'ws');
	return {
		plugins: [tailwindcss(), sveltekit()],
		server: {
			proxy: {
				'/api': {
					target: backend,
					changeOrigin: true,
					secure: false
				},
				'/ws': {
					target: backendWs,
					changeOrigin: true,
					ws: true,
					secure: false
				}
			}
		}
	};
});
