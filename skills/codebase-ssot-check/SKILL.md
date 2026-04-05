---
name: agentos-codebase-ssot-check
description: Scan a codebase for Single Source of Truth (SSOT) violations. USE WHEN the user wants duplicated knowledge, bypassed interfaces, repeated constants, or decentralized decisions identified in the current project.
user-invocable: true
disable-model-invocation: true
---

# SSOT Checker

Scan the current project's `src/` directory for **Single Source of Truth (SSOT) violations** — places where the same decision or knowledge is encoded in multiple locations instead of being centralized in one authoritative place.

**Philosophy**: Every piece of knowledge (paths, constants, logic, configuration) should have exactly one authoritative representation. If changing one value requires editing multiple files, that's an SSOT violation.

## Instructions

Execute the following phases sequentially. Use Glob, Grep, and Read tools — do NOT shell out to grep/find/rg.

### Phase 1: Discover source code

1. Use Glob to find all source files in `src/`:
   - Try `src/**/*.jl`, `src/**/*.py`, `src/**/*.js`, `src/**/*.ts`, `src/**/*.go`, `src/**/*.rs`, `src/**/*.rb`, `src/**/*.java`, `src/**/*.kt`, `src/**/*.cpp`, `src/**/*.c`, `src/**/*.h`
   - Use whichever patterns match files in the project
   - Skip binaries, generated files, lock files, and vendored dependencies
2. Note the primary language(s) based on file extensions found.

### Phase 2: Scan for violations

Search for these categories of SSOT violations. For each, use Grep across all source files.

#### A. Repeated path construction
- Search for path-building functions: `joinpath`, `path.join`, `os.path.join`, `Path(`, `filepath.Join`, etc.
- Group occurrences by the path fragments they construct (e.g., multiple files building `joinpath(root, "tapes")`)
- Flag when 2+ files construct the same path independently
- Check if a centralized path function already exists (e.g., `tapes_dir`, `get_config_path`)

#### B. Magic strings
- Search for repeated quoted string literals (minimum 3 characters, appearing in 2+ files)
- Ignore common/trivial strings: `"w"`, `"r"`, `"utf-8"`, `""`, `"/"`, `"\n"`, standard HTTP methods, common format specifiers
- Focus on domain-specific strings: file names, directory names, config keys, status values, error messages
- Flag when the same non-trivial string literal appears in 3+ locations

#### C. Magic numbers
- Search for numeric literals that appear in multiple files in non-trivial contexts
- Ignore 0, 1, 2 and common mathematical constants
- Focus on: ports, timeouts, buffer sizes, retry counts, thresholds, array indices with domain meaning

#### D. Duplicated logic
- Look for functions with very similar names or signatures across different files
- Look for repeated multi-line patterns (same sequence of operations in 2+ places)
- Look for repeated conditional logic (same if/switch conditions in multiple locations)

#### E. Missing interfaces / Bypassed interfaces
- If a centralized function exists (e.g., `tapes_dir()`), search for code that constructs the same value WITHOUT using that function
- This is the **highest priority** violation type — bypassing existing interfaces
- Also identify repeated patterns that suggest a missing abstraction (same 3+ line pattern in multiple files)

### Phase 3: Rank and select top 5

Score each violation using these heuristics (use judgment, not a formula):

1. **Bypasses existing interface** — highest priority. If a helper function exists and code bypasses it, this ranks first.
2. **Frequency** — more duplicate locations = higher priority
3. **Blast radius** — violations involving paths, config, or core domain concepts rank higher than cosmetic duplication
4. **Specificity** — concrete, fixable violations rank higher than vague patterns

Select the top 5 most impactful violations. If the codebase has fewer, report only what exists. If the codebase is very clean, say so.

### Phase 4: Generate report

Print the report directly to chat using this format:

```markdown
# SSOT Violations Report

## 1. [Short descriptive title]
- **Category**: [repeated path | magic string | magic number | duplicated logic | bypassed interface | missing interface]
- **Files**: `src/Foo.jl:12`, `src/Bar.jl:45`, `src/Baz.jl:78`
- **Issue**: [1-2 sentence description of what knowledge is duplicated and why it matters]
- **Fix**: [Specific, actionable suggestion — name the function to extract, the constant to define, etc.]
```

Rules for the report:
- Each violation gets at most ~5 lines (the 4 bullet points above)
- File paths MUST include line numbers and be verified against actual file content
- Fix suggestions must be concrete (name the function, constant, or module)
- If 0 violations found, print a short "Codebase is clean" message
- Do NOT include violations you are not confident about — precision over recall
