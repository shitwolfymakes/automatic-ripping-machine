
// this file is generated — do not edit it


declare module "svelte/elements" {
	export interface HTMLAttributes<T> {
		'data-sveltekit-keepfocus'?: true | '' | 'off' | undefined | null;
		'data-sveltekit-noscroll'?: true | '' | 'off' | undefined | null;
		'data-sveltekit-preload-code'?:
			| true
			| ''
			| 'eager'
			| 'viewport'
			| 'hover'
			| 'tap'
			| 'off'
			| undefined
			| null;
		'data-sveltekit-preload-data'?: true | '' | 'hover' | 'tap' | 'off' | undefined | null;
		'data-sveltekit-reload'?: true | '' | 'off' | undefined | null;
		'data-sveltekit-replacestate'?: true | '' | 'off' | undefined | null;
	}
}

export {};


declare module "$app/types" {
	type MatcherParam<M> = M extends (param : string) => param is (infer U extends string) ? U : string;

	export interface AppTypes {
		RouteId(): "/" | "/__tests__" | "/change-password" | "/files" | "/files/__tests__" | "/jobs" | "/jobs/__tests__" | "/jobs/[id]" | "/login" | "/logs" | "/logs/__tests__" | "/logs/[job_id]" | "/notifications" | "/notifications/__tests__" | "/settings" | "/settings/__tests__" | "/setup" | "/setup/__tests__" | "/transcoder" | "/transcoder/__tests__";
		RouteParams(): {
			"/jobs/[id]": { id: string };
			"/logs/[job_id]": { job_id: string }
		};
		LayoutParams(): {
			"/": { id?: string | undefined; job_id?: string | undefined };
			"/__tests__": Record<string, never>;
			"/change-password": Record<string, never>;
			"/files": Record<string, never>;
			"/files/__tests__": Record<string, never>;
			"/jobs": { id?: string | undefined };
			"/jobs/__tests__": Record<string, never>;
			"/jobs/[id]": { id: string };
			"/login": Record<string, never>;
			"/logs": { job_id?: string | undefined };
			"/logs/__tests__": Record<string, never>;
			"/logs/[job_id]": { job_id: string };
			"/notifications": Record<string, never>;
			"/notifications/__tests__": Record<string, never>;
			"/settings": Record<string, never>;
			"/settings/__tests__": Record<string, never>;
			"/setup": Record<string, never>;
			"/setup/__tests__": Record<string, never>;
			"/transcoder": Record<string, never>;
			"/transcoder/__tests__": Record<string, never>
		};
		Pathname(): "/" | "/change-password" | "/files" | `/jobs/${string}` & {} | "/login" | "/logs" | `/logs/${string}` & {} | "/notifications" | "/settings" | "/setup" | "/transcoder";
		ResolvedPathname(): `${"" | `/${string}`}${ReturnType<AppTypes['Pathname']>}`;
		Asset(): "/apple-touch-icon.png" | "/favicon.ico" | "/favicon.png" | "/fonts/rajdhani-500-latin-ext.woff2" | "/fonts/rajdhani-500-latin.woff2" | "/fonts/rajdhani-700-latin-ext.woff2" | "/fonts/rajdhani-700-latin.woff2" | "/img/arm-logo-black.png" | "/img/arm-logo-white.png" | "/img/disc-bluray.svg" | "/img/disc-bluray4k.svg" | "/img/disc-data.svg" | "/img/disc-dvd.svg" | "/img/disc-music.svg" | "/img/disc-unknown.svg" | "/img/poster-placeholder.svg" | "/themes/blockbuster.css" | "/themes/cinema.css" | "/themes/coffee.css" | "/themes/craft.css" | "/themes/deep-sea-abyss.css" | "/themes/dracula-pro.css" | "/themes/gaming.css" | "/themes/glass.css" | "/themes/hollywood-video-v2.css" | "/themes/lcars.css" | "/themes/library-archive.css" | "/themes/nordic-frost.css" | "/themes/research-outpost.css" | "/themes/retro-console.css" | "/themes/royal-archive.css" | "/themes/royale.css" | "/themes/solarized-dark.css" | "/themes/stealth-ops.css" | "/themes/synth-retro-v2.css" | "/themes/synth-retro.css" | "/themes/tactical.css" | "/themes/terminal.css" | "/themes/tokyo-night.css" | "/themes/vcr-osd.css" | string & {};
	}
}