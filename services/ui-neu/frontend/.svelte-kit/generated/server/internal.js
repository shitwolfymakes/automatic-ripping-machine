
import root from '../root.js';
import { set_building, set_prerendering } from '$app/env/internal';
import { set_assets } from '$app/paths/internal/server';
import { set_manifest, set_read_implementation } from '__sveltekit/server';
import { set_env } from '__sveltekit/env';
import { set_private_env, set_public_env } from '../../../node_modules/@sveltejs/kit/src/runtime/shared-server.js';

export const options = {
	app_template_contains_nonce: false,
	async: false,
	csp: {"mode":"auto","directives":{"upgrade-insecure-requests":false,"block-all-mixed-content":false},"reportOnly":{"upgrade-insecure-requests":false,"block-all-mixed-content":false}},
	csrf_check_origin: true,
	csrf_trusted_origins: [],
	embedded: false,
	env_public_prefix: 'PUBLIC_',
	env_private_prefix: '',
	hash_routing: false,
	hooks: null, // added lazily, via `get_hooks`
	preload_strategy: "modulepreload",
	root,
	service_worker: false,
	service_worker_options: undefined,
	server_error_boundaries: false,
	templates: {
		app: ({ head, body, assets, nonce, env }) => "<!doctype html>\n<html lang=\"en\">\n\t<head>\n\t\t<meta charset=\"utf-8\" />\n\t\t<link rel=\"icon\" href=\"" + assets + "/favicon.ico\" sizes=\"any\" />\n\t\t<link rel=\"icon\" type=\"image/png\" href=\"" + assets + "/favicon.png\" sizes=\"32x32\" />\n\t\t<link rel=\"apple-touch-icon\" href=\"" + assets + "/apple-touch-icon.png\" />\n\t\t<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n\t\t<title>ARM</title>\n\t\t<style>body { visibility: hidden; }</style>\n\t\t" + head + "\n\t</head>\n\t<body data-sveltekit-preload-data=\"hover\">\n\t\t<script>\n\t\t\t(function() {\n\t\t\t\tvar darkSchemes = ['glass','cinema','gaming','royale','lcars','tactical','craft','terminal','blockbuster','hollywood-video-v2'];\n\t\t\t\tvar cs = localStorage.getItem('colorScheme');\n\t\t\t\tif (darkSchemes.indexOf(cs) !== -1) {\n\t\t\t\t\tdocument.documentElement.classList.add('dark');\n\t\t\t\t} else {\n\t\t\t\t\tvar t = localStorage.getItem('theme');\n\t\t\t\t\tif (t === 'dark' || (!t && window.matchMedia('(prefers-color-scheme: dark)').matches)) {\n\t\t\t\t\t\tdocument.documentElement.classList.add('dark');\n\t\t\t\t\t}\n\t\t\t\t}\n\n\t\t\t\t// Theme CSS cache: inject cached theme style before the CSS bundle loads\n\t\t\t\ttry {\n\t\t\t\t\tvar themeKey = cs || 'default';\n\t\t\t\t\tvar cached = localStorage.getItem('theme-cache-v1-' + themeKey);\n\t\t\t\t\tif (cached) {\n\t\t\t\t\t\tvar style = document.createElement('style');\n\t\t\t\t\t\tstyle.id = 'theme-cache';\n\t\t\t\t\t\tstyle.textContent = cached;\n\t\t\t\t\t\tdocument.head.appendChild(style);\n\t\t\t\t\t}\n\t\t\t\t} catch {\n\t\t\t\t\t// localStorage unavailable - fall through to network-loaded theme\n\t\t\t\t}\n\t\t\t})();\n\t\t</script>\n\t\t<div style=\"display: contents\">" + body + "</div>\n\t</body>\n</html>\n",
		error: ({ status, message }) => "<!doctype html>\n<html lang=\"en\">\n\t<head>\n\t\t<meta charset=\"utf-8\" />\n\t\t<title>" + message + "</title>\n\n\t\t<style>\n\t\t\tbody {\n\t\t\t\t--bg: white;\n\t\t\t\t--fg: #222;\n\t\t\t\t--divider: #ccc;\n\t\t\t\tbackground: var(--bg);\n\t\t\t\tcolor: var(--fg);\n\t\t\t\tfont-family:\n\t\t\t\t\tsystem-ui,\n\t\t\t\t\t-apple-system,\n\t\t\t\t\tBlinkMacSystemFont,\n\t\t\t\t\t'Segoe UI',\n\t\t\t\t\tRoboto,\n\t\t\t\t\tOxygen,\n\t\t\t\t\tUbuntu,\n\t\t\t\t\tCantarell,\n\t\t\t\t\t'Open Sans',\n\t\t\t\t\t'Helvetica Neue',\n\t\t\t\t\tsans-serif;\n\t\t\t\tdisplay: flex;\n\t\t\t\talign-items: center;\n\t\t\t\tjustify-content: center;\n\t\t\t\theight: 100vh;\n\t\t\t\tmargin: 0;\n\t\t\t}\n\n\t\t\t.error {\n\t\t\t\tdisplay: flex;\n\t\t\t\talign-items: center;\n\t\t\t\tmax-width: 32rem;\n\t\t\t\tmargin: 0 1rem;\n\t\t\t}\n\n\t\t\t.status {\n\t\t\t\tfont-weight: 200;\n\t\t\t\tfont-size: 3rem;\n\t\t\t\tline-height: 1;\n\t\t\t\tposition: relative;\n\t\t\t\ttop: -0.05rem;\n\t\t\t}\n\n\t\t\t.message {\n\t\t\t\tborder-left: 1px solid var(--divider);\n\t\t\t\tpadding: 0 0 0 1rem;\n\t\t\t\tmargin: 0 0 0 1rem;\n\t\t\t\tmin-height: 2.5rem;\n\t\t\t\tdisplay: flex;\n\t\t\t\talign-items: center;\n\t\t\t}\n\n\t\t\t.message h1 {\n\t\t\t\tfont-weight: 400;\n\t\t\t\tfont-size: 1em;\n\t\t\t\tmargin: 0;\n\t\t\t}\n\n\t\t\t@media (prefers-color-scheme: dark) {\n\t\t\t\tbody {\n\t\t\t\t\t--bg: #222;\n\t\t\t\t\t--fg: #ddd;\n\t\t\t\t\t--divider: #666;\n\t\t\t\t}\n\t\t\t}\n\t\t</style>\n\t</head>\n\t<body>\n\t\t<div class=\"error\">\n\t\t\t<span class=\"status\">" + status + "</span>\n\t\t\t<div class=\"message\">\n\t\t\t\t<h1>" + message + "</h1>\n\t\t\t</div>\n\t\t</div>\n\t</body>\n</html>\n"
	},
	version_hash: "7a822j"
};

export async function get_hooks() {
	let handle;
	let handleFetch;
	let handleError;
	let handleValidationError;
	let init;
	

	let reroute;
	let transport;
	

	return {
		handle,
		handleFetch,
		handleError,
		handleValidationError,
		init,
		reroute,
		transport
	};
}

export { set_assets, set_building, set_env, set_manifest, set_prerendering, set_private_env, set_public_env, set_read_implementation };
