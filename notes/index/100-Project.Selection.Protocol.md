# Project.Selection.Protocol

Explicit project selection contract for project-aware `agentos` commands.

---

## What It Is

- A CLI protocol for making project-aware commands explicit without forcing callers to pass machine-specific absolute paths.
- A safety layer over `Agentos.Project` discovery.
- The distinction between selecting a project target path and asserting the discovered project root basename.

## Core Rule

A project-aware command must receive at least one explicit project selector:

- `--project`
- `--project-base`
- both `--project` and `--project-base`

Commands must not silently operate on an implicitly discovered project when neither selector is present.

Commands may impose a stricter selector contract when their risk profile requires it.

## Project Path Selector

`--project` is path-shaped.

Rules:

- bare `--project` means use the current working directory as the explicit project target
- `--project <path>` means resolve `<path>` as a filesystem path
- relative values such as `--project agentos-md` and `--project ../agentos-md` are relative paths, not project names
- absolute values are explicit path targets

The resolved target must be an initialized `Agentos.Project` when the command requires an existing project.

## Project Basename Assertion

`--project-base <basename>` is discovery-shaped.

Rules:

- start project discovery from `pwd`
- walk upward until `.agentos/project.json` is found
- require that project to be initialized
- assert `resolved_project.root.name == <basename>`
- fail if no project is found
- fail if the discovered project root basename differs

`--project-base` checks the project root basename, not the marker `project_name`.

## Project Name Assertion

`--project-name <name>` is marker-shaped.

Rules:

- it asserts the declared project name in `.agentos/project.json`
- it is not a filesystem path
- it must fail if the marker name differs from `<name>`
- it must fail if the selected project has no declared marker name

Use `--project-name` when command safety depends on the declared project identity rather than the checkout folder basename.

## Combined Selection

When both selectors are present:

- resolve `--project` as a filesystem target
- require the resolved target to be an initialized `Agentos.Project`
- assert the resolved project root basename matches `--project-base`

Example:

```sh
agentos <command> --project ../agentos-md --project-base agentos-md
```

This is useful when the caller is outside the project tree but still wants an identity check.

## Canonical Prefix Usage

`agentos stdlib prefix next` has a stricter contract than the general project selector rule.

It requires both:

- `--project`
- `--project-name`

For callers already inside the intended project tree:

```sh
agentos stdlib prefix next --project --project-name agentos-py --target notes/index
agentos stdlib prefix next --project --project-name agentos-py --target notes/live
agentos stdlib prefix next --project --project-name agentos-py --target dev/live
```

For callers outside the intended project tree:

```sh
agentos stdlib prefix next --project /path/to/agentos-py --project-name agentos-py --target notes/index
```

## Why Not `--project=<name>`

`--project=<value>` must remain a path selector because normal CLI expectations treat option values such as `agentos-md` and `../agentos-md` as paths.

Using `--project-base` avoids ambiguity:

- `--project agentos-md` means relative path `./agentos-md`
- `--project-base agentos-md` means discover from `pwd` and assert root basename `agentos-md`

## Basename Versus Marker Name

`--project-base` and `--project-name` are different assertions.

- `--project-base` checks the filesystem checkout basename
- `--project-name` checks marker-level logical identity

General project-aware commands may use `--project-base` for lightweight checkout safety. Commands that require marker identity, such as `agentos stdlib prefix next`, should use `--project-name`.
