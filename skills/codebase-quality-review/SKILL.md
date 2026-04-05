---
name: codebase-quality-review
description: Analyze a codebase to find organization, readability, and maintainability issues, then propose incremental improvements. USE WHEN the user wants a quality review focused on unorganized structure, suboptimal patterns, or maintainability problems.
---

# Codebase Quality Review

## Purpose

This Skill helps improve project quality incrementally by:
- scanning the codebase for structural, readability, organization or repeated pattern issues,
- reporting and explaining why these are issues,
- proposing small, medium, and more elaborate fixes for each.

This Skill is intended to be used when the user asks to review a codebase for quality, refactor opportunities, or organizational improvements.

---

## When to Use

Use this Skill when the user requests any of the following:
- “Find unorganized or suboptimal sections in the codebase”
- “Audit the project for quality issues and suggest fixes”
- “Generate a quality improvement report for this repo”
- “Code review for maintainability and structure issues”

---

## Inputs

- A path or reference to the codebase directory
- Optional: a list of languages in the project
- Optional: priorities (e.g., readability, test coverage, architecture)

---

## Core Workflow

When this Skill is triggered:

1. **Scan the codebase files**  
   - Traverse the repo by language, key directories and common patterns (e.g., tests, src folders).
   - Identify areas that appear unorganized (e.g., files without clear structure, repeated logic blocks, outdated documentation).

2. **For each finding**, produce a structured report entry including:
   - **Issue summary**  
     What the issue is and where it appears.
   - **Why this is an issue**  
     Practical downsides: maintainability, readability, risk of bugs, onboarding friction.
   - **Evidence**  
     Code excerpts, file paths, function names or patterns that illustrate the problem.
   - **Improvement proposals**  
     At least 2–4 options:
       a) small incremental fix  
       b) slightly larger refactor  
       c) (optional) more ambitious solution if justified
   - **Expected impact**  
     What gets better if the fix is applied.

3. **Rank and prioritize findings**  
   - Low-hanging fruit first
   - Tests and safety improvements next
   - Larger structural changes later

---

## Output Format

Each issue output must follow this structure:

```

### Issue: <short description>

**Location:** <file path or module>

**Why this is an issue:**
<clear, concise explanation with practical consequences>

**Evidence:**
<code snippet, file list, pattern description>

**Improvement proposals:**

1. <smallest, safest improvement>
2. <medium refactor keeping current patterns>  
3. <more involved improvement if justified>

**Expected impact:**
<what improves — clarity, correctness, reduced bugs, onboarding>

```

At the end of the overall report:
- Include a **top 5 prioritized list** of improvements
- Provide a **summary of codebase health** and main risk areas

---

## Guidelines & Constraints

- Focus on **incremental improvements** rather than wholesale rewrites.
- Respect existing style and conventions unless they are part of the issue.
- Distinguish between *acceptable* code and *problematic* code — only flag real issues.
- For ambiguous cases, state assumptions clearly.
- When proposing fixes, avoid overly abstract patterns unless they are clearly beneficial.
- Provide actionable steps; prefer concrete examples over vague advice.
