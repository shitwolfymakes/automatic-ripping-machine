# Contributing to the Wiki

The wiki you're reading is generated from Markdown files in the **`arm_wiki/`**
folder of the main repository, so wiki edits go through the same fork → branch →
PR flow as code. (Don't edit pages directly in the GitHub wiki UI — those edits
live in a separate wiki repo and get overwritten.)

## Make a change

1. **Fork** the
   [repository](https://github.com/automatic-ripping-machine/automatic-ripping-machine)
   and **clone** your fork:

   ```bash
   git clone https://github.com/<your-username>/automatic-ripping-machine.git
   cd automatic-ripping-machine
   ```

2. **Branch** from `main` (trunk-based — don't commit to `main` directly):

   ```bash
   git switch -c wiki/fix-getting-started
   ```

3. **Edit the Markdown** under `arm_wiki/`. Each `.md` file is one wiki page; the
   filename (with spaces as hyphens) is its URL slug. If you add or remove a
   page, update **`arm_wiki/_Sidebar.md`** so the navigation stays in sync.

4. **Commit and push** to your fork:

   ```bash
   git commit -am "docs(wiki): clarify GPU overlay setup"
   git push -u origin wiki/fix-getting-started
   ```

5. **Open a pull request** against `main`. A maintainer reviews it, and once
   merged the published wiki updates automatically.

## Style notes

- Keep it **v3-accurate.** v3 is Docker-only with a one-line installer and UI
  config — no native installs, no `arm.yaml`. If you find a page still describing
  v2, fix or flag it.
- **Link between pages** with the page slug, e.g. `[Configuration](Configuring-ARM)`;
  link into the repo with full GitHub URLs.
- Prefer concise, task-focused prose. Match the tone of the existing pages.

If you're also touching code, fold the wiki update into the same PR — see
[Contributing](Contribute).
