# Source Registry

Curated default sources for `skills-miner-ingenier`.

Use this registry as a starting point, not an exhaustive crawl. For each task:

- inspect the target first
- derive search themes
- select only the most relevant sources
- add prompt-provided sources when needed
- prefer a local mirror under `/Users/pereiro/.agents/skills-mine` when one exists

## Entry Format

Each source entry should capture:

- `id`s
- `kind`
- `location`
- `priority` (optional; use when a source should be preferred within its tier)
- `why-it-matters`
- `best-for`
- `caveats`
- `search-hints`

## custom-recommendations

- `id`: `custom-recommendations`
- `kind`: local user-maintained recommendation set
- `location`: `/Users/pereiro/.agents/skills/skills-miner-ingenier/references/custom-recommendations`
- `priority`: `high`
- `why-it-matters`: captures repeated local preferences and design rules that should influence mining and authoring even when external sources suggest something more generic
- `best-for`: trigger wording, local style conventions, packaging preferences, source-specific overrides, and repeated design guidance the user wants preserved across skill work
- `caveats`: these files are intentionally opinionated and environment-specific; prefer them only when they clearly apply to the current target
- `search-hints`: `README.md`, `*.md`, `USE WHEN`, `frontmatter`, `description`, `trigger`, `local preference`

## spec-kit

- `id`: `spec-kit`
- `kind`: external official repo and workflow toolkit
- `location`: `https://github.com/github/spec-kit`
- `priority`: `high`
- `why-it-matters`: official GitHub toolkit for Spec-Driven Development with a concrete multi-step workflow, reusable templates, presets/extensions, and explicit support for agent-specific command or skill installation
- `best-for`: spec-first workflow design, command/skill decomposition, template layering, project constitution or memory patterns, agent-install integration patterns, and mining how a reusable toolkit maps one process across multiple agent surfaces
- `caveats`: strongly opinionated around spec-driven development and product-specific command surfaces; translate slash-command or installer details into agent-agnostic concepts before reuse
- `search-hints`: `README.md`, `spec-driven.md`, `docs/`, `templates/`, `presets/`, `extensions/`, `AGENTS.md`, `specify init`, `/speckit.constitution`, `/speckit.specify`, `/speckit.plan`, `/speckit.tasks`, `/speckit.implement`

## fabric

- `id`: `fabric`
- `kind`: local mined repo mirror and pattern library
- `location`: `/Users/pereiro/.agents/skills-mine/fabric`
- `why-it-matters`: large named prompt corpus with reusable pattern structure and task scoping
- `best-for`: pattern naming, prompt structure, output schema ideas, diff-oriented prompts, prompt examples to mine and adapt
- `caveats`: quality is uneven; many prompts contain roleplay fluff or arbitrary constraints; stronger as a pattern mine than as a full skill system
- `search-hints`: `data/patterns/review_code`, `review_design`, `create_pattern`, `create_coding_feature`, `summarize_git_diff`, `create_git_diff_commit`

## skills-mine-root

- `id`: `skills-mine-root`
- `kind`: local mined source depot
- `location`: `/Users/pereiro/.agents/skills-mine`
- `why-it-matters`: curated local home for cloned and inspected external sources used during skill mining
- `best-for`: initial source inventory, checking which external sources are available locally, and choosing a small relevant subset before deeper reads
- `caveats`: this is a container, not a single source; do not crawl it exhaustively by default
- `search-hints`: top-level directories, repo remotes, `SKILL.md`, `AGENTS.md`, `agents/`, `skills/`, `references/`

## anthropics-skills

- `id`: `anthropics-skills`
- `kind`: local mined repo mirror
- `location`: `/Users/pereiro/.agents/skills-mine/anthropics-skills`
- `why-it-matters`: official public Agent Skills repository with real skills, a template, and a specification
- `best-for`: full skill-stack design, progressive disclosure, bundled scripts and references, spec-aligned structure, and higher-quality production-oriented examples
- `caveats`: some skills are complex and product-specific; do not cargo-cult Claude-specific harness behavior into agent-agnostic skills
- `search-hints`: `skills/*/SKILL.md`, `template/SKILL.md`, `spec/agent-skills-spec.md`, `skills/skill-creator`, `skills/mcp-builder`, `skills/docx`, `skills/webapp-testing`

## mattpocock-skills

- `id`: `mattpocock-skills`
- `kind`: local mined repo mirror
- `location`: `/Users/pereiro/.agents/skills-mine/mattpocock-skills`
- `why-it-matters`: high-signal public skill corpus centered on practical software engineering workflows, small composable skills, and explicit setup patterns for project-specific conventions
- `best-for`: engineering workflow design, concise skill scoping, setup/bootstrap skills, interview or grilling flows, TDD and diagnosis loops, architecture-improvement prompts, and mining a real skill-authoring example from `write-a-skill`
- `caveats`: the repo is organized around slash-command style invocation and some agent-specific setup assumptions; reuse the workflow shape and packaging ideas without importing product-specific command syntax or repo conventions verbatim
- `search-hints`: `README.md`, `skills/engineering/*/SKILL.md`, `skills/productivity/write-a-skill/SKILL.md`, `skills/productivity/grill-me/SKILL.md`, `skills/engineering/grill-with-docs/SKILL.md`, `skills/engineering/tdd/SKILL.md`, `skills/engineering/diagnose/SKILL.md`, `skills/engineering/setup-matt-pocock-skills/SKILL.md`

## agent-skills-standard

- `id`: `agent-skills-standard`
- `kind`: external documentation set
- `location`: `https://agentskills.io/`
- `why-it-matters`: strongest source for the format itself, cross-client conventions, and implementation guidance for portable skill systems
- `best-for`: skill structure, discovery conventions, description design, script usage, and client-side integration rules
- `caveats`: this is a standard and guidance source, not a large corpus of example skills; pair it with concrete repos
- `search-hints`: `https://agentskills.io/what-are-skills`, `https://agentskills.io/specification`, `https://agentskills.io/skill-creation/optimizing-descriptions`, `https://agentskills.io/skill-creation/using-scripts`, `https://agentskills.io/integrate-skills`

## cline-docs

- `id`: `cline-docs`
- `kind`: external documentation set
- `location`: `https://docs.cline.bot/`
- `why-it-matters`: strong source for workflow design, reusable process files, context hygiene, and the distinction between rules, workflows, skills, and memory
- `best-for`: workflow composition, rules-bank ideas, memory patterns, and process-oriented agent customization
- `caveats`: product-specific features and naming should be adapted before reuse in agent-agnostic skills
- `search-hints`: `https://docs.cline.bot/customization/skills`, `https://docs.cline.bot/customization/workflows`, `https://docs.cline.bot/features/cline-rules/overview`, `https://docs.cline.bot/customization/memory-bank`

## github-copilot-docs

- `id`: `github-copilot-docs`
- `kind`: external documentation set
- `location`: `https://docs.github.com/en/copilot/`
- `why-it-matters`: strong official source for how skills, custom instructions, prompt files, custom agents, and MCP-related customization fit together in one product
- `best-for`: choosing the right artifact type, skill locations, customization layering, prompt-file patterns, and official crosswalks between always-on and on-demand guidance
- `caveats`: mixes GitHub.com, CLI, IDE, and coding-agent surfaces; extract the underlying design idea instead of copying product-surface details verbatim
- `search-hints`: `https://docs.github.com/copilot/concepts/agents/about-agent-skills`, `https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-skills`, `https://docs.github.com/en/copilot/reference/customization-cheat-sheet`, `https://docs.github.com/en/copilot/concepts/about-customizing-github-copilot-chat-responses`, `https://docs.github.com/en/copilot/tutorials/customization-library/custom-instructions`, `https://docs.github.com/en/copilot/tutorials/customization-library/prompt-files`, `https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-custom-agents-for-cli`, `https://docs.github.com/en/copilot/reference/custom-agents-configuration`

## claude-code-docs

- `id`: `claude-code-docs`
- `kind`: external documentation set
- `location`: `https://docs.claude.com/en/docs/claude-code/`
- `why-it-matters`: strongest official source for the relationship between skills, slash commands, subagents, and MCP-backed prompts in Claude Code
- `best-for`: deciding when a capability should be a skill versus a slash command, designing subagent decomposition, and understanding how structured reusable capabilities compose
- `caveats`: some concepts are Claude-specific and should be translated into agent-agnostic terms before reuse
- `search-hints`: `https://docs.claude.com/en/docs/claude-code/skills`, `https://docs.claude.com/en/docs/claude-code/slash-commands`, `https://docs.claude.com/en/docs/claude-code/subagents`, `https://docs.claude.com/en/docs/claude-code/mcp`

## continue-docs

- `id`: `continue-docs`
- `kind`: external documentation set
- `location`: `https://docs.continue.dev/`
- `why-it-matters`: strong source for how prompts, rules, agents, and YAML configuration fit together across local files and shared hub artifacts
- `best-for`: rule layering, prompt-file structure, agent composition, configuration-driven reuse, and thinking about local versus shared artifacts
- `caveats`: Continue uses its own product vocabulary and hub concepts; reuse the structural patterns without assuming the same runtime model elsewhere
- `search-hints`: `https://docs.continue.dev/customize/overview/`, `https://docs.continue.dev/customization/rules`, `https://docs.continue.dev/customize/deep-dives/rules`, `https://docs.continue.dev/actions/how-it-works`, `https://docs.continue.dev/hub/agents/create-and-edit`, `https://docs.continue.dev/agent/how-to-customize`, `https://docs.continue.dev/yaml-reference`, `https://docs.continue.dev/checks/reference`

## cursor-docs

- `id`: `cursor-docs`
- `kind`: external documentation set
- `location`: `https://docs.cursor.com/`
- `why-it-matters`: strong source for concise rules, commands, custom modes, and practical agent operating guidance from a coding-agent product with a heavy workflow focus
- `best-for`: rule scoping, `AGENTS.md` positioning, command-style reusable workflows, custom modes, and concise product-tested advice for context hygiene
- `caveats`: some useful guidance lives in Cursor blog posts rather than the formal docs; product-specific file locations should be adapted before reuse
- `search-hints`: `https://docs.cursor.com/en/context`, `https://docs.cursor.com/agent/custom-modes`, `https://docs.cursor.com/en/agent/chat/commands`, `https://docs.cursor.com/en/cli/using`, `https://cursor.com/blog/agent-best-practices/`

## awesome-copilot

- `id`: `awesome-copilot`
- `kind`: local mined repo mirror
- `location`: `/Users/pereiro/.agents/skills-mine/awesome-copilot`
- `why-it-matters`: broad community collection of agents, skills, instructions, and related artifacts for GitHub Copilot
- `best-for`: breadth, artifact-type comparison, trigger phrasing, agent packaging patterns, and discovering cross-cutting workflow ideas
- `caveats`: quality varies widely; many entries are specialized, noisy, or style-heavy rather than structurally strong
- `search-hints`: `skills/*/SKILL.md`, `agents/*.agent.md`, `.github/copilot-instructions.md`, `AGENTS.md`

## home-skills

- `id`: `home-skills`
- `kind`: local skill directory
- `location`: `/Users/pereiro/.agents/skills`
- `why-it-matters`: main working skill collection with real trigger descriptions, workflow structure, and packaging choices
- `best-for`: `SKILL.md` structure, `agents/openai.yaml` patterns, progressive disclosure, validation conventions, full skill-stack design
- `caveats`: contains a mix of mature, experimental, and copied skills; compare before imitating
- `search-hints`: `skill-creator`, `design-discussion`, `codebase-general-cleanup`, `codebase-quality-review`, `index-*`

## agentos-project-skills

- `id`: `agentos-project-skills`
- `kind`: local project skill directory
- `location`: `/Users/pereiro/projects/agentos/skills`
- `why-it-matters`: project-local and more experimental skill patterns that may not yet be reflected in the home skill set
- `best-for`: discussion-driven designs, task miners, in-progress conventions, and side-by-side comparison against home skills
- `caveats`: may diverge from home copies; some entries are partial or project-specific
- `search-hints`: `design-discussion`, `design-interview`, `todo-miner`, `tasks001-*`, `index-*`
