# Situation Chains

<!-- tarav.sessions
3537df0a = claude-code:2bff854f-66a0-4e8c-8f96-9078af34c479 @3537df0a6015d884a94e9594478f971cb92e38df63776b87b5eea38741740d8a
-->

What we understand about how Tarav models checking and its follow-up.
Implementation: request 926 (`notes/live/926-situation-chains-impl-req.md`).

## The chain

Situation → Check → POI → Action → Closing (blessed, gone, or another
Closing Type) is one model, a Situation Chain: a set of Types implementing the
relationships between those links. They are integrated; POIs show no evident
use outside such chains, and not every POI scales to an Action.
<!-- tarav.breadcrumb 579a3bc78306 -->

Blessing is not a general model. It is one closing path of the actions of a
chain. Tarav may provide several POI/Check/Action primitives; do not
generalize one of them.
<!-- tarav.breadcrumb f16e9796463b -->

`SituationChain` is a class that encapsulates the Types of its links. Its
POIs all belong to it; links are bound by a field. A chain may be
instantiated; consumers decide what they instantiate.
<!-- tarav.breadcrumb 998ef24371ff -->
<!-- tarav.breadcrumb 10f24efe6e8b -->

## Identity

A chain works with one situation. Its objects' identity is
hash(type, hash(situation)). A Check may produce several POIs; there is one
Action per POI and one POI per Action, as a Type relationship. Every POI Type
has its own Action Type, as every check has its own Check Type; there is no
generic Action Type. Many situations of one kind are many instances of the
same Chain Type. Actions are their own objects and exist outside chains too.
<!-- tarav.breadcrumb 4690ab66e511 -->
<!-- tarav.breadcrumb b122583915ad -->

A blessing accepts a situation: the situation holds every fact relevant to
the check, so when one changes, the check raises a different POI, which the
blessing does not cover. Details carry no meaning for identity or blessings.
<!-- tarav.breadcrumb 57b059698c9f -->

## Checks are atomic; Suites find situations

The caller creates the situation and passes it to the Check. A Check is
atomic: one that reads a whole package and finds many problems is
ill-conditioned.
<!-- tarav.breadcrumb 5cab28894895 -->

A Suite knows how to run Checks: it finds the situations, shares expensive
loading, and runs one atomic Check per situation. Suites nest, have names,
and the Suite can be a generic Type. Check Suites keep their role; they are
one consumer of chains. The Project is left out of the chain for now.
<!-- tarav.breadcrumb e5cf4e262682 -->
<!-- tarav.breadcrumb dc562b4c3e43 -->

## External tools: the Gitleaks template

Run the tool's native checks, store its report as natively as possible, and
let Tarav find situations by revisiting that report. Gitleaks already works
this way (`l1/git/gitleaks.py`: the report in a depot, Project checks
re-reading the latest one); it is the template for any external tool.
<!-- tarav.breadcrumb 39db3b820934 -->

## Open

- A general positive-result POI ("checked and found fine", with no Action)
  was named as useful for every chain; not designed yet.
  <!-- tarav.breadcrumb 9824f320608c -->

## Implemented so far (request 926)

The User left the open choices to the Agent.
<!-- tarav.breadcrumb ee98c2aa4a43 -->

- `tarav.l1.checks.chains.SituationChain` names a chain's atomic
  `SituationCheck` and its POI Types and binds them (`chain`); a chain's
  Check raises only its POIs; an instance is one situation. POI Types name
  their Action Types (`action`), so chains do not import Actions.
- Blessing is an exit of `BlessableResolution` Action Types
  (`tarav.l1.actions.pois`); `BlessablePOI` is gone, and the generic
  `Tarav.Actions.POI.Resolution` closes only as gone. Each blessable POI Type
  names its own Action Type.
- Gitleaks is the first chain user: `GitleaksSuite` revisits the native
  report and yields one atomic Check per situation (`l1/git/gitleaks.py`).
- Not yet: the positive-result POI, an Action Type for every POI Type
  outside chains.

## Implemented: the Skillware analysis (request 927)

The User asked for it next, after Gitleaks.
<!-- tarav.breadcrumb fd589074cc02 -->

- A skill's Suite (`SkwSkillSuite`, `l2/skw/chains.py`) loads the package
  once and runs one atomic Check per situation: the skill (marker,
  loading), each source, product, product drift, block, context entry,
  freshness snapshot, consumer file, link and dependency.
- The rules stay in the native analysis, split per subject in l1
  (`Document.block_findings`, `source_findings`, the product reading);
  `lint()` composes them. A Check per finding would only re-raise what the
  analysis decided; a Check per subject runs the rule.
- Situations stay "the place", with declared relative paths; what a check
  compares joins the situation only where that is the problem (ProductDrift,
  freshness).
- Every Skillware POI Type names `<its name>.Resolution`.
- Not yet: the Project's agents file, which still raises chain POI Types
  from outside their chains.

## Implemented: the reading graph (request 928)

The User chose it next.
<!-- tarav.breadcrumb 77cd993bf9b6 -->

- The reading analysis is one traversal of the whole graph: reachability,
  cycles and paths cannot be decided per block. It plays the part of a
  native report: `ReadingAnalysis` runs it once and each reading Check
  (graph, node, declaration target, source-block binding, requirement,
  reading path, prose link) reads its own subject's part. Where a rule is
  local (a block's binding, a link's prose), the Check runs it itself.
- A missing context keeps the path that misses it in its situation, as the
  reading-path Wiki asks ("identify an unmet dependency and the path that
  misses it", `tarav-md/notes/wiki/reader-context-path.md`); a requirement
  met on some paths and not others is its own situation.
  <!-- tarav.breadcrumb ad65590db5fd -->

## Naming: a chain's Types end on what they are (request 930)

The User asked to homogenize the names of a chain around one prefix, as a
formalism for readability: the name ends on the kind of Type, so it says
what it is, with optional extras between the chain and the kind.
<!-- tarav.breadcrumb 940058930892 -->
<!-- tarav.breadcrumb 8d28a12a36d3 -->
<!-- tarav.breadcrumb 559c4802e903 -->

```text
<chain>.<extras>.<kind>      kind: Chain, Check, POI, Action
Tarav.Git.Gitleaks.Finding.Chain
Tarav.Git.Gitleaks.Finding.Check
Tarav.Git.Gitleaks.Finding.Reported.POI
Tarav.Git.Gitleaks.Finding.Reported.Action
```

- A POI and the Action it opens carry the problem as their extra, also in a
  one-POI chain, so a chain can gain a POI without a rename; the shared
  problem pairs them. `.Resolution` is gone: this supersedes the 927 note
  above that Skillware Actions are `<its name>.Resolution`.
- A helper builds the names, so the code tells the next chains the
  convention (`chain_type_name`, `CHAIN_KINDS`), and defining a chain
  refuses a Check, POI or Action named otherwise; that also enforces one
  Action Type per POI Type in a chain.
  <!-- tarav.breadcrumb 6e2cd7baf44b -->
- Names are labels, ids are identity: check, POI and action identities hash
  Type ids, so renaming kept them. Stored action records keep names, and
  were migrated once outside Tarav
  (`~/Documents/tarav/migrations/20261019-chain-type-names/`).
- Not covered: suite names (a suite's identity uses its name), Python class
  names. One POI's situation holds a Type name, `Tarav.Project.Root.ChildPOIs`
  (child POIs counted by Type), so a rename re-identifies it; open.
