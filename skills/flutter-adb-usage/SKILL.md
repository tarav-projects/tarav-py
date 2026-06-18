---
name: agentos-flutter-adb-usage
description: Guide Flutter app development around real Android devices tested primarily through `adb`, `uiautomator dump`, and screenshots. USE WHEN the user wants Flutter code or UI flows to be testable through the Android accessibility tree and device tooling.
---

# Flutter ADB Usage

Guide development of Flutter apps so they are testable on real Android devices using `adb` as the primary automation surface.

This skill is for development guidance, review, and implementation planning. It does not replace test frameworks. Its purpose is to make the app itself reliably observable and operable through Android device tooling.

This is a `Batchy.Skill`. Load `agentos-batchy-skills` for the full convention.

- `-h` / `--help` prints this skill's help into the chat instead of running; it takes no arguments.

## Use This Skill When

- The user wants an app to be testable on a real Android device.
- The user wants an agent to inspect and drive the UI using `adb`.
- The user wants coding guidance for Flutter widgets so `uiautomator dump` can see meaningful nodes.
- The user wants a review of whether a Flutter screen is compatible with ADB-driven testing.

## Core Principle

Treat the Android accessibility tree as the primary machine-readable UI contract.

`adb` and `uiautomator` do not see Flutter widgets directly. They operate through what Android exposes from Flutter's semantics tree. Therefore:

- If a human using accessibility services cannot reliably identify and activate a control, ADB-driven automation should not rely on it either.
- `ValueKey` is useful for Flutter widget tests, but it is not the primary contract for ADB-driven real-device testing.
- Stable semantics beat coordinate tapping.
- Screenshots verify visuals; semantics verify structure and interactability.

## Primary Surfaces

Use these surfaces in this order:

1. Android accessibility tree from `uiautomator dump`
2. Screenshots from `adb exec-out screencap`
3. Direct shell interaction such as tap, swipe, text input, back, and app launch
4. Coordinate-based interaction only as a fallback

## Non-Goals

This skill is not primarily about:

- Flutter widget-test strategy
- Simulator-first testing
- Emulator-only assumptions
- MCP-specific integrations
- Appium/Maestro/Patrol setup, except as secondary context

## Mental Model

For ADB-driven testing, the effective UI surface is:

`Flutter widget tree -> Flutter semantics tree -> Android accessibility nodes -> uiautomator dump`

The development goal is to make important app behavior visible and operable at the Android accessibility layer.

## Development Rules

### 1. Expose important screens explicitly

Every important screen should have a stable semantic identity.

Examples:

- launcher screen
- notes screen
- drafts screen
- filter screen
- review sheet
- detail screen

Prefer a stable screen-level semantic identifier or label that does not depend on decorative copy.

### 2. Expose important actions explicitly

Every important action should be identifiable without coordinates.

Examples:

- send note
- open drafts
- capture photo
- apply filter
- save
- delete
- confirm
- cancel

For icon-only actions, add explicit semantics such as:

- label
- hint when useful
- role such as button

Do not assume the icon alone is enough.

### 3. Expose important entities explicitly

Rows, cards, bubbles, list items, and domain objects should expose stable per-entity semantics.

Examples:

- note card for note id `note_001`
- draft card for draft id `draft_017`
- export row for export folder `tara-mobile-202603141230`

Prefer identifiers derived from domain IDs, not list position.

Good:

- `note-card-note_001`
- `draft-card-draft_017`

Bad:

- `first-item`
- `row-3`

### 4. Reflect important state in semantics

If the user or test must know the current state, that state should be visible through semantics text or a clearly exposed node.

Examples:

- sending
- empty state
- selected filter
- draft saved
- capture in progress
- error banner shown

Do not make critical state observable only through color, animation, or layout position.

### 5. Use coordinate taps only as fallback

Coordinate-based taps are brittle and should not be the main testing contract.

They are acceptable only when:

- bootstrapping a legacy screen
- dealing with third-party/native UI that lacks better hooks
- temporarily bridging until semantics are added

If a flow depends on repeated coordinate taps, the app likely needs better semantics.

### 6. Preserve semantics stability across refactors

Labels and identifiers used as automation hooks should stay stable when visual styling changes.

Prefer domain-stable wording and identifiers over marketing or ornamental language.

## Flutter Coding Guidance

When reviewing or writing Flutter code, look for these patterns:

- Add `Semantics(...)` around custom tappable containers.
- Ensure icon-only buttons expose a clear accessible label.
- Ensure list items expose enough meaning to distinguish one item from another.
- Use semantics on custom cards built with `InkWell`, `GestureDetector`, or other wrappers.
- Avoid accidental loss of semantics through overly decorative composition.
- Keep interactive nodes separate enough that `uiautomator dump` can target them.

Use Flutter semantics intentionally for:

- screen roots
- buttons
- toggles
- tabs
- lists
- row/card items
- banners and error messages
- loading or progress states when they matter to flow control

## Verification Workflow

When applying this skill, prefer this sequence:

1. Identify the user flow to support.
2. Inspect the Flutter code for semantics coverage.
3. Predict what Android should expose.
4. Build and install the app on a real device.
5. Open the target screen.
6. Capture:
   - screenshot
   - `uiautomator dump`
7. Confirm:
   - the expected node exists
   - the label or identifier is stable
   - the action is distinguishable from siblings
   - the resulting state change is visible
8. Only then define or refine the ADB-driven test steps.

## Review Checklist

Use this checklist when auditing a screen:

- Can the screen be recognized from the dumped UI tree?
- Can the primary action be found without coordinates?
- Can repeated list items be distinguished from one another?
- Can a specific domain entity be targeted by stable identity?
- Can success, failure, loading, and empty states be observed?
- Are icon-only controls labeled clearly?
- Are custom tappable surfaces exposed through semantics?
- Would the test still work after layout or spacing changes?
- Is any critical interaction currently coordinate-only?
- Are semantics names stable enough to survive normal copy/design iteration?

## Anti-Patterns

Flag these as ADB-testability problems:

- `ValueKey` used as if it were an ADB locator
- icon buttons without accessible labels
- generic repeated labels like `Open`, `More`, or `Edit` on many siblings
- relying on visual order or row index to identify domain entities
- core flows that require hard-coded coordinates
- critical state visible only by color or animation
- custom cards that are tappable but not semantically meaningful
- unstable labels that change for stylistic reasons instead of product meaning

## Output Style

When using this skill, produce:

- a short statement of the target flow or screen
- the current ADB-testability assessment
- the top missing semantics contracts
- exact recommendations for what to expose
- any fallback coordinate interactions still required
- residual risk if the current UI is still partially opaque to `uiautomator`

Prefer concrete guidance over abstract accessibility lectures.

## Good Outcome

A good outcome from this skill is:

- the app can be opened and navigated on a real Android device
- important controls can be located from `uiautomator dump`
- important state can be verified from semantics and screenshots
- ADB-driven testing does not depend on fragile coordinates for core flows
- Flutter code has an intentional, stable semantics contract for automation

## References

Primary references should favor official docs:

- Flutter accessibility and semantics docs
- Flutter API docs for semantics
- Android accessibility and `AccessibilityNodeInfo` docs
- Android UI Automator docs when needed
