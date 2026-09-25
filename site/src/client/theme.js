// Runs synchronously in <head> so the first paint has the right mode.
// Uses the same localStorage key as ui-neu ('theme': 'dark' | 'light').
(function () {
	var saved = null;
	try {
		saved = localStorage.getItem('theme');
	} catch (e) {
		// storage blocked: fall through to the OS preference
	}
	var dark = saved ? saved === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
	document.documentElement.classList.toggle('dark', dark);
})();
