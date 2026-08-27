# Manual Setup Checklist

These settings change external accounts, credentials, GitHub Apps, or repository administration. They are deliberately not automated by this pull request. The repository owner performs each applicable item and records completion in the canonical GitHub Issue or pull request without copying secret values.

## Codex Cloud and GitHub

- [ ] Sign in to [Codex](https://chatgpt.com/codex) with the intended ChatGPT account and workspace.
- [ ] Connect GitHub through the Codex setup flow and grant access only to `OKJ1105/evidence-first-rag` unless broader access is explicitly intended.
- [ ] Create a Codex cloud environment for this repository using the [Codex cloud environment guide](https://learn.chatgpt.com/docs/environments/cloud-environment).
- [ ] Confirm the environment checks out the default branch and can create a test branch without bypassing protection on `main`.
- [ ] Keep automatic review disabled. Enable repository **Code review** in [Codex settings](https://chatgpt.com/codex/settings/code-review), then use a top-level `@codex review` pull request comment only when L1 or L2 requires it. See [Use Codex in GitHub](https://learn.chatgpt.com/docs/third-party/github).
- [ ] Confirm Codex reads the root `AGENTS.md` review rules on a representative pull request.

## Claude Code Web and GitHub

- [ ] Sign in to Claude with the intended account and open Claude Code on the web.
- [ ] Connect GitHub through the product flow and grant the Claude GitHub App access only to this repository unless broader access is explicitly intended.
- [ ] Select this repository and run a documentation-only test task in an isolated branch. Confirm that the proposed change is reviewable before opening or merging a pull request.
- [ ] Do not install Claude Code GitHub Actions and do not enable automatic Claude review. This workflow uses Claude Code Web as the writer, not an AI Action.
- [ ] Review the current [Claude Code on the web guide](https://support.claude.com/en/articles/12618689-claude-code-on-the-web) and [GitHub integration guide](https://support.claude.com/en/articles/10167454-use-the-github-integration) when reconnecting or changing repository access.

## Cloud environments, dependencies, variables, and Secrets

- [ ] Record required runtime and tool versions in repository contracts or dependency files before adding setup commands. The repository currently has no product dependencies to install.
- [ ] Add only reproducible dependency installation commands to each cloud environment's setup configuration.
- [ ] Store non-secret configuration as environment variables in the provider UI. Do not commit machine-specific values or `.env` files.
- [ ] Store credentials only in the provider's encrypted Secrets UI. Never paste secret values into Issues, pull requests, prompts, logs, fixtures, or repository files.
- [ ] Grant each environment only the minimum repository and network access needed. Keep agent-phase internet access disabled or allowlisted unless a reviewed task requires more.
- [ ] Verify setup with synthetic data and least-privilege accounts. Do not connect production or customer data.
- [ ] Record only Secret names, owners, purpose, rotation expectations, and successful verification in GitHub; never record values.

## GitHub Ruleset for `main`

Perform this only after the `repository-checks` job has run successfully on a pull request. GitHub requires a check to exist before it can be selected reliably as required.

- [ ] Open repository **Settings > Rules > Rulesets** and create a branch ruleset targeting the default branch, following [GitHub's repository ruleset guide](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository).
- [ ] Set enforcement to **Active** only after reviewing the target and bypass list.
- [ ] Enable **Require a pull request before merging**.
- [ ] Enable **Require status checks to pass before merging** and require the `repository-checks` job. Do not require an AI review check.
- [ ] Enable **Require conversation resolution before merging**.
- [ ] Leave AI users and GitHub Apps out of the bypass list and do not grant them merge authority.
- [ ] Keep automatic merge disabled for this repository workflow; the repository owner manually confirms scope, review level, CI, conversations, and required human decisions before merge.
- [ ] Test the Ruleset with a small L0 pull request before relying on it for product work. GitHub documents the available protections in [Available rules for rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets).

## Optional smartphone Remote connection

- [ ] Install current ChatGPT desktop and mobile apps and sign in to the same account and workspace.
- [ ] On the desktop host, open **Settings > Connections > Control this Mac or PC** and start setup.
- [ ] Scan the displayed QR code from the mobile device and complete any MFA, SSO, or passkey checks.
- [ ] Keep the host awake, online, and running the desktop app while using Remote. Existing sandbox and approval settings still apply.
- [ ] Review connected devices periodically and remove devices that are no longer used. Availability can vary by account or workspace rollout; see the current [Remote connections guide](https://learn.chatgpt.com/docs/remote).
