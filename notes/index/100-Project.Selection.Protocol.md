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

## Combined Selection

When both selectors are present:

- resolve `--project` as a filesystem target
- require the resolved target to be an initialized `Agentos.Project`
- assert the resolved project root basename matches `--project-base`

Example:

```sh
agentos prefix next --project ../agentos-md --project-base agentos-md --target notes/live
```

This is useful when the caller is outside the project tree but still wants an identity check.

## Canonical Prefix Usage

For callers already inside the intended project tree:

```sh
agentos prefix next --project-base agentos-py --target notes/index
agentos prefix next --project-base agentos-py --target notes/live
agentos prefix next --project-base agentos-py --target dev/live
```

For callers outside the intended project tree:

```sh
agentos prefix next --project /path/to/agentos-py --project-base agentos-py --target notes/index
```

## Why Not `--project=<name>`

`--project=<value>` must remain a path selector because normal CLI expectations treat option values such as `agentos-md` and `../agentos-md` as paths.

Using `--project-base` avoids ambiguity:

- `--project agentos-md` means relative path `./agentos-md`
- `--project-base agentos-md` means discover from `pwd` and assert root basename `agentos-md`

## Superseded Surface

`--project-name` is not the right option for this safety check.

Reasons:

- it sounds like a marker-level logical name
- the intended assertion is the filesystem project root basename
- caller skills need a lightweight checkout safety check, not a marker identity contract

Marker-level project names may remain useful for initialization or metadata, but they are separate from project basename assertion.
