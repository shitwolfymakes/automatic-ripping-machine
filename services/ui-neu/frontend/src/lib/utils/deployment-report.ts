// Builds the Markdown deployment report that Settings > System copies for
// bug reports: version, environment by group, containers, health, log levels.
import type {
	ContainerView,
	DiagnosticsServiceView,
	EnvVarView,
	SystemDiagnosticsResponse,
	SystemEnvironmentResponse
} from '$lib/types/api.gen';
import { checkDetail, checkLabel, pathDetail, pathState } from './system-health';

// Collapse line breaks so one value stays on one line.
function oneLine(v: string): string {
	return v.replace(/\r?\n|\r/g, '\\n');
}

function escapeHtml(v: string): string {
	return oneLine(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Inline code span for text outside a fence: the delimiter is a backtick run
// longer than any run inside, so the text cannot close it early.
function inlineCode(v: string): string {
	const text = oneLine(v);
	const longest = Math.max(0, ...(text.match(/`+/g) ?? []).map((r) => r.length));
	const fence = '`'.repeat(longest + 1);
	return `${fence} ${text} ${fence}`;
}

function yesNo(v: boolean | null): string {
	if (v === null) return 'unknown';
	return v ? 'yes' : 'no';
}

function varLine(v: EnvVarView): string {
	if (v.secret) return `${v.key}=${v.is_set ? '<set>' : '<not set>'}`;
	let line = `${v.key}=${oneLine(v.value ?? '')}`;
	if (v.source === 'default') line += '  (default)';
	if (v.effective) line += `  | in use: ${v.effective.value} (Settings > ${v.effective.tab})`;
	return line;
}

// A fence longer than any backtick run in the content, so a value cannot close it.
function fence(lines: string[]): string[] {
	const longest = Math.max(0, ...lines.flatMap((l) => (l.match(/`+/g) ?? []).map((m) => m.length)));
	const ticks = '`'.repeat(Math.max(3, longest + 1));
	return [ticks, ...lines, ticks];
}

function containerBlock(c: ContainerView): string[] {
	const state = c.state === null ? '' : ` (${escapeHtml(c.state)})`;
	const lines = [`image: ${oneLine(c.image)}`];
	if (c.network) lines.push(`network: ${oneLine(c.network)}`);
	if (c.docker_host) lines.push(`docker host: ${oneLine(c.docker_host)}`);
	if (c.mounts.length) {
		lines.push(
			'mounts:',
			...c.mounts.map((m) => `  ${oneLine(m.host)} -> ${oneLine(m.container)} (${oneLine(m.mode)})`)
		);
	}
	if (c.devices.length) lines.push('devices:', ...c.devices.map((d) => `  ${oneLine(d)}`));
	if (c.env.length) {
		lines.push('env:', ...c.env.map((e) => `  ${oneLine(e.key)}=${e.secret ? '<secret>' : oneLine(e.value ?? '')}`));
	}
	return [
		`<details><summary>${escapeHtml(c.kind)}: ${escapeHtml(c.label)}${state}</summary>`,
		'',
		...fence(lines),
		'',
		'</details>'
	];
}

function healthSection(health: SystemDiagnosticsResponse): string[] {
	const lines = health.checks.map((c) =>
		c.status === 'ok' ? `- PASS ${checkLabel(c.name)}` : `- FAIL ${checkLabel(c.name)}: ${inlineCode(checkDetail(c))}`
	);
	for (const p of health.paths) {
		lines.push(
			pathState(p) === 'ok'
				? `- PASS ${oneLine(p.name)}: ${oneLine(p.path)}`
				: `- FAIL ${oneLine(p.name)}: ${oneLine(p.path)}, ${inlineCode(pathDetail(p))}`
		);
	}
	return ['### Health', ...lines, ''];
}

export function buildDeploymentReport(
	env: SystemEnvironmentResponse,
	health: SystemDiagnosticsResponse | null,
	logLevels: DiagnosticsServiceView[],
	now: Date
): string {
	const out: string[] = [
		`## ARM deployment report | ${env.version} | ${now.toISOString()}`,
		'',
		'**Summary**',
		`- Host paths set: ${yesNo(env.summary.host_paths_set)}`,
		`- Transcode capable: ${yesNo(env.summary.transcode_capable)}`,
		`- GPUs: ${env.summary.gpus.length ? env.summary.gpus.join(', ') : 'none'}`,
		''
	];
	if (health) out.push(...healthSection(health));

	const levelLines = logLevels.map((s) => `- ${s.name}: ${s.log_level}`);
	let loggingDone = levelLines.length === 0;
	for (const g of env.groups) {
		out.push(`### ${g.name}`, ...fence(g.vars.map(varLine)));
		if (g.name === 'Logging' && !loggingDone) {
			out.push('', ...levelLines);
			loggingDone = true;
		}
		out.push('');
	}
	if (!loggingDone) out.push('### Logging', '', ...levelLines, '');

	if (env.containers.length) {
		out.push('### Containers', '');
		for (const c of env.containers) out.push(...containerBlock(c), '');
	}
	return out.join('\n').trimEnd() + '\n';
}
