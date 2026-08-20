# $kw: --from POI.System --from Index.Linter
"""Historical Index POI roots retained while the redesigned checker replaces producers.

These are addressable documentation entrypoints, not a runtime catalog. The former
Markdown classes had no executable producer after the concurrent Index redesign; keeping
their exact lines here preserves resolution for existing POI instances without making
Markdown a second canonical copy.
"""

from __future__ import annotations


# $kw: Index.Linter/Config.NoSurfaces --from POI.Linter
# --note emitted when no lint target is configured
# --note normal use is `--depot`; explicit surface paths exist only for advanced or partial linting
# --note fix by passing a depot root, or an explicit surface path when doing partial linting
def _historical_01() -> str:
    return "Index.Linter/Config.NoSurfaces"


# $kw: Index.Linter/Surface.IndexMissing --from POI.Linter
# --note emitted when a configured `--index` path does not exist
# --note the path is resolved from the current working directory unless absolute
# --note fix by correcting the path or creating the intended index scope
def _historical_02() -> str:
    return "Index.Linter/Surface.IndexMissing"


# $kw: Index.Linter/Surface.AppendixMissing --from POI.Linter
# --note emitted when a configured `--appendix` path does not exist
# --note the path is resolved from the current working directory unless absolute
# --note fix by correcting the path or creating the intended appendix surface
def _historical_03() -> str:
    return "Index.Linter/Surface.AppendixMissing"


# $kw: Index.Linter/Surface.IndexNotMarkdown --from POI.Linter
# --note emitted when a configured `--index` file is not a markdown file
# --note files passed explicitly must end in `.md`; directories may contain markdown files
# --note fix by passing a markdown file or an index directory
def _historical_04() -> str:
    return "Index.Linter/Surface.IndexNotMarkdown"


# $kw: Index.Linter/Surface.AppendixNotMarkdown --from POI.Linter
# --note emitted when a configured `--appendix` file is not a markdown file
# --note files passed explicitly must end in `.md`; directories may contain markdown files
# --note fix by passing a markdown file or an appendix directory
def _historical_05() -> str:
    return "Index.Linter/Surface.AppendixNotMarkdown"


# $kw: Index.Linter/Surface.IndexInvalid --from POI.Linter
# --note emitted when a configured `--index` path is neither a markdown file nor a directory
# --note fix by passing a valid markdown file or directory path
def _historical_06() -> str:
    return "Index.Linter/Surface.IndexInvalid"


# $kw: Index.Linter/Surface.AppendixInvalid --from POI.Linter
# --note emitted when a configured `--appendix` path is neither a markdown file nor a directory
# --note fix by passing a valid markdown file or directory path
def _historical_07() -> str:
    return "Index.Linter/Surface.AppendixInvalid"


# $kw: Index.Linter/Surface.Invalid --from POI.Linter
# --note used as a blocked-check dependency when no configured surface is valid
# --note this code is not usually emitted as a direct finding
# --note fix the preceding surface path errors before interpreting downstream blocked checks
def _historical_08() -> str:
    return "Index.Linter/Surface.Invalid"


# $kw: Index.Linter/Files.None --from POI.Linter
# --note emitted when configured valid surfaces contain no markdown files
# --note the linter can run on files or directories, but only markdown files are processed
# --note fix by pointing at markdown files or directories containing markdown files
def _historical_09() -> str:
    return "Index.Linter/Files.None"


# $kw: Index.Linter/Mdblocks.Syntax --from POI.Linter
# --note fallback emitted when the shared markdown-block parser reports a structural issue without a first-class linter code
# --note most known mdblocks issues are promoted to `Index.Linter/Block.*` codes
# --note details include the underlying mdblocks source code for the specific syntax condition
def _historical_10() -> str:
    return "Index.Linter/Mdblocks.Syntax"


# $kw: Index.Linter/Block.NoHeadings --from POI.Linter
# --note emitted when a markdown file contains no headings in the configured heading range
# --note usually means a non-index document is inside a linted surface, or the file is an empty shell
# --note fix by moving the file out of the linted surface, adding the intended block heading, or passing a narrower file set
def _historical_11() -> str:
    return "Index.Linter/Block.NoHeadings"


# $kw: Index.Linter/Block.UnclosedCodeFence --from POI.Linter
# --note emitted when a file appears to contain an unclosed fenced code block
# --note unclosed fences make heading and separator parsing unreliable
# --note fix by closing the code fence before interpreting downstream block findings
def _historical_12() -> str:
    return "Index.Linter/Block.UnclosedCodeFence"


# $kw: Index.Linter/Block.SeparatorOutsideSemantics --from POI.Linter
# --note emitted when a `****` separator is not consumed as a block opening or closing boundary
# --note common causes are a separator followed by plain text, duplicate separators, or misplaced structural markers
# --note fix by placing separators immediately before block headings and after block bodies
def _historical_13() -> str:
    return "Index.Linter/Block.SeparatorOutsideSemantics"


# $kw: Index.Linter/Block.EmptyHeading --from POI.Linter
# --note emitted when a heading title is empty after markdown sanitization
# --note empty headings cannot name index concepts or appendix sections
# --note fix by naming the heading or removing the empty heading marker
def _historical_14() -> str:
    return "Index.Linter/Block.EmptyHeading"


# $kw: Index.Linter/Block.TooLong --from POI.Linter
# --note emitted when a separator-anchored block exceeds the hard block line limit
# --note details include `line_span`, `max_block_lines`, and `end_line`
# --note fix by splitting depth into scoped appendix blocks or moving non-fundamental detail out of the block
def _historical_15() -> str:
    return "Index.Linter/Block.TooLong"


# $kw: Index.Linter/Block.DuplicateHeading --from POI.Linter
# --note emitted when a file repeats the same heading title at the same markdown level
# --note duplicate local headings are usually ambiguous for block search and citation
# --note fix by merging, renaming, or scoping one of the repeated headings
def _historical_16() -> str:
    return "Index.Linter/Block.DuplicateHeading"


# $kw: Index.Linter/Block.UnanchoredSection --from POI.Linter
# --note emitted when an H2-H6 heading appears outside a separator-anchored block
# --note plain starting text before the first block is allowed
# --note the depot router `000-INDEX.md` is exempt because its sections are control-plane structure, not concept blocks
# --note fix by wrapping the section in a block using `****`, or by moving non-block content outside H2-H6 headings
def _historical_17() -> str:
    return "Index.Linter/Block.UnanchoredSection"


# $kw: Index.Linter/Router.Missing --from POI.Linter
# --note emitted when configured surfaces include no depot-root router file
# --note the required router is `000-INDEX.md` at the `Index.Depot` root
# --note fix by adding `000-INDEX.md`, pointing `--depot` at the depot root, or including a surface that belongs to a depot with that router
def _historical_18() -> str:
    return "Index.Linter/Router.Missing"


# $kw: Index.Linter/Router.LegacyName --from POI.Linter
# --note emitted when a depot contains a legacy router filename such as `000-index.md` or `001-index.md`
# --note the only valid router name is `000-INDEX.md` at the `Index.Depot` root
# --note fix by renaming the legacy router to `000-INDEX.md` and placing it at the depot root
def _historical_19() -> str:
    return "Index.Linter/Router.LegacyName"


# $kw: Index.Linter/Router.Empty --from POI.Linter
# --note emitted when the depot router `000-INDEX.md` exists but is empty
# --note the router should provide concept-to-file routing for the index depot
# --note fix by adding routing entries or removing the empty router from the linted depot
def _historical_20() -> str:
    return "Index.Linter/Router.Empty"


# $kw: Index.Linter/Index.InvalidFilename --from POI.Linter
# --note emitted when an index markdown file does not match the chapter filename convention
# --note chapter files use `NNN-<chapter>.md`, where `<chapter>` matches the containing folder name
# --note fix by renaming the file to match its chapter folder or moving non-index markdown out of the linted index scope
def _historical_21() -> str:
    return "Index.Linter/Index.InvalidFilename"


# $kw: Index.Linter/Concept.InvalidHeading --from POI.Linter
# --note emitted when an index block heading does not match the current `Block.Path` pattern
# --note a valid heading starts with a rooted `Dotted.Notation` concept and may continue with `/` segments for concept refs or free labels
# --note fix by renaming the heading to a valid `Block.Path`, or by updating the grammar if the design intentionally permits the form
def _historical_22() -> str:
    return "Index.Linter/Concept.InvalidHeading"


# $kw: Index.Linter/Concept.Inventory --from POI.Linter
# --note used as a blocked-check dependency when concept inventory cannot be trusted or is unavailable
# --note this code is not usually emitted as a direct finding
# --note fix markdown block syntax errors or add discoverable concept blocks before interpreting dependent checks
def _historical_23() -> str:
    return "Index.Linter/Concept.Inventory"


# $kw: Index.Linter/Concept.InventoryEmpty --from POI.Linter
# --note emitted when a configured index scope contains no separator-anchored concept blocks
# --note downstream concept, router, and appendix checks may be blocked when the concept inventory is unavailable
# --note fix by adding concept blocks or pointing the linter at the correct index chapter files
def _historical_24() -> str:
    return "Index.Linter/Concept.InventoryEmpty"


# $kw: Index.Linter/Concept.Duplicate --from POI.Linter
# --note emitted when the same concept heading appears in more than one configured index block
# --note a concept should have one authoritative index block per index depot
# --note fix by merging duplicates, scoping one occurrence, or moving detail into appendix material
def _historical_25() -> str:
    return "Index.Linter/Concept.Duplicate"


# $kw: Index.Linter/Appendix.InvalidFilename --from POI.Linter
# --note emitted when an appendix markdown file does not match the appendix filename convention
# --note expected names use `Concept.Name-appendix.md` or paged forms such as `Concept.Name-appendix-2.md`
# --note fix by renaming the appendix file or moving non-appendix markdown out of the appendix surface
def _historical_26() -> str:
    return "Index.Linter/Appendix.InvalidFilename"


# $kw: Index.Linter/Appendix.Orphan --from POI.Linter
# --note emitted when an appendix file has no matching configured index concept block
# --note appendix discovery starts from an index concept, so orphaned appendix material may be undiscoverable
# --note fix by adding the concept block, correcting the filename, or including the owning index scope in the lint run
def _historical_27() -> str:
    return "Index.Linter/Appendix.Orphan"


# $kw: Index.Linter/Appendix.RouteAnnotationMissing --from POI.Linter
# --note emitted when a routed concept has appendix pages but the router entry has no `[+N]` annotation
# --note annotations expose appendix depth at the router surface
# --note fix by adding `[+N]` to the routed concept, where `N` is the contiguous appendix page count
def _historical_28() -> str:
    return "Index.Linter/Appendix.RouteAnnotationMissing"


# $kw: Index.Linter/Appendix.RouteAnnotationStale --from POI.Linter
# --note emitted when a router `[+N]` annotation does not match discovered appendix page depth
# --note stale annotations mislead agents about available depth for the concept
# --note fix by updating the annotation to the expected count reported by the linter
def _historical_29() -> str:
    return "Index.Linter/Appendix.RouteAnnotationStale"


# $kw: Index.Linter/Appendix.PageGap --from POI.Linter
# --note emitted when appendix page files for a concept are non-contiguous
# --note expected pages are `Concept.Name-appendix.md`, then `Concept.Name-appendix-2.md`, `Concept.Name-appendix-3.md`, and so on without gaps
# --note fix by adding the missing page file, renaming the later page, or consolidating the appendix material
def _historical_30() -> str:
    return "Index.Linter/Appendix.PageGap"


# $kw: Index.Linter/Router.InvalidConcept --from POI.Linter
# --note emitted when a router entry contains a concept name that does not match the current `Block.Path` pattern
# --note routed concepts use the same heading grammar as index block headings
# --note fix by correcting the routed concept name or by updating the grammar if the form is intentional
def _historical_31() -> str:
    return "Index.Linter/Router.InvalidConcept"


# $kw: Index.Linter/Router.EntriesEmpty --from POI.Linter
# --note emitted when router files exist but no routing entries can be parsed from them
# --note this usually means the routing table is missing or does not match the expected bullet format
# --note fix by adding entries like ``- `design/100-design.md` — Concept.Name`` to the router
def _historical_32() -> str:
    return "Index.Linter/Router.EntriesEmpty"


# $kw: Index.Linter/Router.MissingEntry --from POI.Linter
# --note emitted when a discovered concept block is not listed in a configured router
# --note routers are the compressed symbol table for index discovery
# --note fix by adding the concept to the appropriate router entry
def _historical_33() -> str:
    return "Index.Linter/Router.MissingEntry"


# $kw: Index.Linter/Router.MissingFile --from POI.Linter
# --note emitted when a router entry points to a file that does not exist at its routed depot path
# --note route files are resolved depot-root-relatively from `000-INDEX.md`
# --note fix by correcting the route target or restoring the missing chapter file
def _historical_34() -> str:
    return "Index.Linter/Router.MissingFile"


# $kw: Index.Linter/Router.UnknownConcept --from POI.Linter
# --note emitted when a router entry points to a concept block that was not discovered
# --note this can mean the routed concept is stale, misspelled, or outside the configured lint scope
# --note fix by correcting the router, adding the missing block, or including the owning chapter file in the lint run
def _historical_35() -> str:
    return "Index.Linter/Router.UnknownConcept"


# $kw: Index.Linter/Router.WrongFile --from POI.Linter
# --note emitted when a router entry names a real concept but routes it to a different file than the discovered block
# --note fix by updating the route file or moving the concept block to the routed chapter file
def _historical_36() -> str:
    return "Index.Linter/Router.WrongFile"


# $kw: Index.Linter/DepotDependency.Unresolved --from POI.Linter
# --note [DF] emitted when a declared Index depot dependency cannot be resolved through the configured dependency resolver
# --note [CT] the instance preserves the dependency identity and resolver evidence reported by the existing check
# --note [RJ] this migration does not add a new repair or blessing policy
def _historical_37() -> str:
    return "Index.Linter/DepotDependency.Unresolved"


# $kw: Index.Linter/DepotDependency.Collision --from POI.Linter
# --note [DF] emitted when engaged Index depots expose colliding concept definitions
# --note [CT] the instance preserves the colliding concept and depot evidence reported by the existing check
# --note [RJ] this migration does not decide which definition should own the concept
def _historical_38() -> str:
    return "Index.Linter/DepotDependency.Collision"


# $kw: Index.Linter/DepotDependency.DanglingMention --from POI.Linter
# --note [DF] emitted when the enabled dangling-mention check finds an Index name that does not resolve across engaged depots
# --note [CT] the instance preserves the mentioned name and source location reported by the existing check
# --note [RJ] this migration does not infer whether the source or target should change
def _historical_39() -> str:
    return "Index.Linter/DepotDependency.DanglingMention"


# $kw: Index.Linter/Line.Type.Syntax --from POI.Linter
# --note [DF] emitted when an Index kernel line has malformed `Line.Type` bracket syntax
# --note [CT] evaluation uses the parser-backed kernel-line model rather than reparsing raw text in the check
# --note [RJ] this migration does not change the accepted syntax
def _historical_40() -> str:
    return "Index.Linter/Line.Type.Syntax"


# $kw: Index.Linter/Line.Type.UnknownCode --from POI.Linter
# --note [DF] emitted when an Index kernel line uses a `Line.Type` code outside the configured vocabulary
# --note [CT] the instance preserves the observed code and source line
# --note [RJ] this migration does not extend or reinterpret the vocabulary
def _historical_41() -> str:
    return "Index.Linter/Line.Type.UnknownCode"


# $kw: Index.Linter/Source.Axis.Placement --from POI.Linter
# --note [DF] emitted when a source-axis line appears outside a surface where the existing Index policy permits it
# --note [CT] the instance preserves the source location and placement evidence
# --note [RJ] this migration does not change placement policy
def _historical_42() -> str:
    return "Index.Linter/Source.Axis.Placement"


# $kw: Index.Linter/Anchor.LegacySigil --from POI.Linter
# --note [DF] emitted when an Index surface cites an Anchory anchor with the legacy `@` sigil instead of `^`
# --note [CT] the instance preserves the observed anchor and mechanical replacement
# --note [RJ] this migration does not change anchor resolution or repair the source
def _historical_43() -> str:
    return "Index.Linter/Anchor.LegacySigil"


# $kw: Index.Linter/Anchor.Unprefixed --from POI.Linter
# --note [DF] emitted when an Index kernel line cites a bare anchor without its namespace prefix
# --note [CT] the instance preserves the observed anchor and source location
# --note [RJ] this migration does not infer the missing namespace
def _historical_44() -> str:
    return "Index.Linter/Anchor.Unprefixed"


# $kw: Index.Linter/TypeStatement.LegacySigil --from POI.Linter
# --note [DF] emitted when an Index surface uses the legacy `:` type-statement sigil instead of `::`
# --note [CT] the instance preserves the observed statement and mechanical replacement
# --note [RJ] this migration does not change type-statement semantics
def _historical_45() -> str:
    return "Index.Linter/TypeStatement.LegacySigil"


# $kw: Index.Linter/Line.Unlinked --from POI.Linter
# --note [DF] emitted when a live Index kernel line has no `Support.Reference`
# --note [CT] the line remains live under `Index.Presumption` while grounding is unresolved
# --note [RJ] this migration does not infer or mint missing support
def _historical_46() -> str:
    return "Index.Linter/Line.Unlinked"


# $kw: Index.Linter/Block.Ungrounded --from POI.Linter
# --note [DF] emitted when an Index concept block has kernel lines without a resolvable nonempty support set
# --note [CT] the instance preserves the block path and existing grounding coverage evidence
# --note [RJ] this migration does not infer or mint missing support
def _historical_47() -> str:
    return "Index.Linter/Block.Ungrounded"


# $kw: Index.Linter/Anchor.LineDrift --from POI.Linter
# --note [DF] `Index.Linter/Anchor.LineDrift` is emitted when an occurrence’s canonical `Line.Type + Index.Line.Body + Anchor.Id` triplet differs from its dossier’s attachment assertion ^c20260802-249u
# --note [CT] evaluation compares the current canonical triplet with the attachment assertion; support, gate, and provenance relationships do not participate in that comparison ^c20260802-250u
# --note [CT] moving or copying an unchanged anchored line does not create drift because location is outside the attachment assertion ^c20260802-251u
# --note [DC] resolution makes the dossier attachment assertion agree with the retained anchored-line projection ^c20260802-252u
# --note [FR] the maintainer may preserve the anchor and refresh its attachment assertion, restore the line projection to its asserted state, or assign an independent anchor according to the application semantics ^c20260802-253u
# --note [CT] refreshing an attachment assertion does not by itself change support, gate, or provenance relationships ^c20260802-254u
# --note [CT] an independent anchor establishes its own relationships; support may retain equivalent members, change, or remain absent according to the available evidence ^c20260802-255u
# --note [RJ] drift does not authorize automatic content search, anchor relocation, or relationship rewriting ^c20260802-256u
# --note [DC] the class is not blessable while the asserted and observed triplets disagree ^c20260802-257u
def _historical_48() -> str:
    return "Index.Linter/Anchor.LineDrift"


# $kw: Index.Linter/Issue.InvalidFilename --from POI.Linter
# --note [DF] emitted when a file inside `issues/` does not follow the `NNN-issues.md` convention
def _historical_49() -> str:
    return "Index.Linter/Issue.InvalidFilename"


# $kw: Index.Linter/Issue.InvalidIdentity --from POI.Linter
# --note [DF] emitted when an Issue.Block heading does not match `Issue.I####[.Dotted.Name]`
def _historical_50() -> str:
    return "Index.Linter/Issue.InvalidIdentity"


# $kw: Index.Linter/Issue.Line.TypeRequired --from POI.Linter
# --note [DF] emitted when an Issue.Block kernel line has no valid `Line.Type`
def _historical_51() -> str:
    return "Index.Linter/Issue.Line.TypeRequired"


# $kw: Index.Linter/Issue.Line.GroundingRequired --from POI.Linter
# --note [DF] emitted when an `Issue.Block` kernel line has no trailing `Index.Line.Anchor` token ^c20260809-196u
# --note [CT] the anchor is the dossier handle through which the line’s `Support.Reference` is evaluated; it is not itself that relationship ^c20260809-197u
def _historical_52() -> str:
    return "Index.Linter/Issue.Line.GroundingRequired"
