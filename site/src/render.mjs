// Markdown -> HTML fragment. Runs once per page; the output is shared by the
// Pages site and the in-app /help route, so it carries only ui-neu block
// classes and docs-* element classes, never Tailwind utilities, and raw HTML
// in markdown is escaped (the app injects this with {@html}).
import MarkdownIt from 'markdown-it';
import GithubSlugger from 'github-slugger';
import { createHighlighter } from 'shiki';

const LANGS = ['shellscript', 'css', 'json', 'yaml', 'svelte', 'typescript', 'javascript', 'python', 'dockerfile', 'nginx', 'ini', 'toml', 'diff', 'sql', 'html'];
const ALERTS = { note: 'info', tip: 'success', important: 'info', warning: 'warning', caution: 'danger' };
const GH_MARKER = /^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\][ \t]*\n?/i;
const BOLD_LEAD = /^\*\*(Note|Tip|Important|Warning|Caution)\*\*/i;

const inlineText = (inline) =>
	(inline.children ?? [])
		.filter((c) => c.type === 'text' || c.type === 'code_inline')
		.map((c) => c.content)
		.join('');

export async function createRenderer() {
	const hl = await createHighlighter({ themes: ['github-light', 'github-dark'], langs: LANGS });
	const shikiOptions = {
		themes: { light: 'github-light', dark: 'github-dark' },
		defaultColor: false,
		transformers: [{ pre(node) { this.addClassToHast(node, 'code-block'); } }]
	};
	const highlight = (code, lang) => {
		try {
			return hl.codeToHtml(code, { ...shikiOptions, lang: lang || 'text' });
		} catch {
			return hl.codeToHtml(code, { ...shikiOptions, lang: 'text' });
		}
	};

	const md = new MarkdownIt({ html: false, linkify: true });
	const r = md.renderer.rules;
	r.fence = (tokens, idx) => highlight(tokens[idx].content, tokens[idx].info.trim().split(/\s+/)[0].toLowerCase());
	r.code_block = (tokens, idx) => highlight(tokens[idx].content, 'text');
	r.table_open = () => '<div class="docs-table-scroll"><table class="table">\n';
	r.table_close = () => '</table></div>\n';
	r.blockquote_open = (tokens, idx, opts, env, self) => {
		const alert = tokens[idx].meta?.alert;
		if (!alert) return self.renderToken(tokens, idx, opts);
		const title = alert.title ? `<p class="alert-title">${alert.title}</p>` : '';
		return `<div class="alert alert-${alert.kind} docs-alert" role="note">${title}\n`;
	};
	r.blockquote_close = (tokens, idx, opts, env, self) =>
		tokens[idx].meta?.alert ? '</div>\n' : self.renderToken(tokens, idx, opts);

	// Before inline parsing: detect callouts on the raw paragraph text and
	// strip GitHub's [!KIND] marker so it never reaches the output.
	md.core.ruler.before('inline', 'arm_alerts', (state) => {
		const { tokens } = state;
		tokens.forEach((t, i) => {
			if (t.type !== 'blockquote_open' || tokens[i + 1]?.type !== 'paragraph_open') return;
			const inline = tokens[i + 2];
			let alert = null;
			const gh = inline.content.match(GH_MARKER);
			if (gh) {
				const word = gh[1].toLowerCase();
				alert = { kind: ALERTS[word], title: word[0].toUpperCase() + word.slice(1) };
				inline.content = inline.content.slice(gh[0].length);
			} else {
				const bold = inline.content.match(BOLD_LEAD);
				if (bold) alert = { kind: ALERTS[bold[1].toLowerCase()], title: null };
			}
			if (!alert) return;
			t.meta = { alert };
			const close = tokens.findIndex((c, j) => j > i && c.type === 'blockquote_close' && c.level === t.level);
			tokens[close].meta = { alert };
		});
	});

	// After inline parsing: heading ids, table classes, link and image
	// resolution, search text.
	md.core.ruler.push('arm_docs', (state) => {
		const { env, tokens } = state;
		let line = 1;
		let inBody = false;
		tokens.forEach((t, i) => {
			if (t.map) line = t.map[0] + 1;
			switch (t.type) {
				case 'heading_open': {
					const text = inlineText(tokens[i + 1]);
					const id = env.slugger.slug(text);
					t.attrSet('id', id);
					env.headingIds.add(id);
					const depth = Number(t.tag.slice(1));
					if (depth === 2 || depth === 3) env.toc.push({ depth, id, text });
					break;
				}
				case 'tbody_open': inBody = true; break;
				case 'tbody_close': inBody = false; break;
				case 'th_open': t.attrJoin('class', 'table-header'); break;
				case 'td_open': t.attrJoin('class', 'table-cell'); break;
				case 'tr_open': if (inBody) t.attrJoin('class', 'table-row'); break;
				case 'inline':
					rewriteInline(t, env, line);
					env.text.push(inlineText(t));
					break;
			}
		});
	});

	function rewriteInline(inline, env, line) {
		const where = `${env.page.srcPath}:${line}`;
		for (const child of inline.children ?? []) {
			if (child.type === 'link_open') {
				const raw = child.attrGet('href');
				const resolved = env.resolver.resolve(raw, env.page.srcPath);
				if (resolved.kind === 'error') {
					env.errors.push(`${where}: ${resolved.message}`);
					continue;
				}
				const n = env.links.push({ line, raw, resolved }) - 1;
				child.attrSet('href', `@@doclink:${n}@@`);
				if (resolved.kind === 'external') {
					child.attrSet('target', '_blank');
					child.attrSet('rel', 'noopener');
				}
			} else if (child.type === 'image') {
				const resolved = env.resolver.resolveAsset(child.attrGet('src'), env.page.srcPath);
				if (resolved.kind === 'error') env.errors.push(`${where}: ${resolved.message}`);
				else if (resolved.kind === 'asset') child.attrSet('src', `@@docasset:${env.assets.push(resolved.path) - 1}@@`);
			}
		}
	}

	return {
		render(page, resolver) {
			const env = { page, resolver, slugger: new GithubSlugger(), headingIds: new Set(), toc: [], links: [], assets: [], errors: [], text: [] };
			const html = md.render(page.source, env);
			return { page, html, toc: env.toc, headingIds: env.headingIds, links: env.links, assets: env.assets, errors: env.errors, text: env.text.join(' ') };
		}
	};
}
