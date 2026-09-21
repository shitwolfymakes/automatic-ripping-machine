import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		proxy: {
			'/api': {
				target: 'https://localhost:8443',
				changeOrigin: true,
				secure: false
			},
			'/ws': {
				target: 'wss://localhost:8443',
				changeOrigin: true,
				ws: true,
				secure: false
			}
		}
	}
});
