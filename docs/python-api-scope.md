# Python API scope for loupe4py

The first remaining step in [issue #4](https://github.com/ide4cj/cjmcp/issues/4)
is to define the operations cjmcp needs. The target is a programmable Cangjie
frontend: an agent runs Python that queries syntax and semantics, combines the
results, and prepares project changes. New analyses should not require a new
MCP tool for each question.

This is a proposed capability contract and implementation order, not the
completed binding map or a working Python API. Source observations use
cjls/loupe **371069c9312b8ddb4cc5045349937235218693f8**, pinned in `cjpm.lock`.
Python names below are proposed. Binding feasibility and runtime behavior are
the next steps of issue #4; the dependency lock remains unchanged.

## Meaning of full access

Expose all existing frontend capabilities through the separate loupe4py facade,
including structured syntax and semantic queries needed to compose analyses.
The initial hover/diagnostics/definition scenario establishes the binding and
lifecycle; it is not the final API boundary.

Provide two complementary Python surfaces:

- **Analysis operations:** project discovery, symbols, navigation, references,
  diagnostics, completion, formatting, expansions and revision-checked edits.
- **Structured frontend access:** syntax nodes and tokens, declarations,
  imports, signatures, bodies, inferred types, resolved calls, members and
  hierarchy. Concrete views adapt the relevant public HIR/AST queries. Preserve
  variants and identity so scripts can join results without parsing hover text.

The facade owns the root database, VFS, loaders and snapshots. Python receives
read views and controlled mutation methods. Database storage, query-cache
internals, LSP transport and arbitrary mutation of HIR are implementation details.
An operation missing from the public frontend needs a neutral upstream API.

The eventual map must account for every public operation in `loupe`, `loupe.db`,
`loupe.vfs` and `project_model`: a Python operation, a facade-owned implementation
detail, or a documented omission. Supporting `loupe.syntax`, HIR, `cjsyntax`,
`ginkgo`, rope and formatting types enter through the capabilities below.
Automatic export of every transitive package is not required.

## Required operations

“Direct” means a public operation supplies the analysis, not that its types
already cross the Python boundary. “Adapt” requires facade composition or
concrete views. “Gap” requires additional frontend behavior or a public entry
point. Availability evidence in this table is source inspection.

| Capability and proposed Python operations | Existing source and implementation path | Purpose and constraints |
| --- | --- | --- |
| `Workspace.open`, `reload`, `project`, `files`, `read_text` | Adapt [findProject and ProjectLoad][project], [SDK discovery][sdk], [VFS][vfs], [loaders][loader], [setProject][db] | Load manifests, loose files, dependencies, SDK and target configuration; expose load problems, partial loading, inactive files and dependency provenance. Add `project_model` as a dependency during implementation. |
| `set_text`, `create_file`, `delete_file`, `apply_edits` | Adapt `Vfs.setFileContents`, `takeChanges`, `AnalysisDatabase.applyChanges` and `setProject` ([VFS][vfs], [database][db]) | Maintain an overlay and project membership. File creation/deletion and manifest changes may require rebuilding the project model. Disk persistence is explicit. |
| `snapshot`, `cancel`, `close`, `capabilities` | Adapt [AnalysisDatabase.snapshot][db]; facade capability metadata | Give one script a consistent revision; expose supported operations and known limitations. |
| `symbols`, `file_symbols`, `structure` | Direct [workspaceSymbols, fileSymbols][symbols], [fileStructure][structure] | Discover declarations and enclosing items. Workspace symbol matching is case-insensitive subsequence matching; empty query matches all names. Expose truncation. |
| `hover`, `definition`, `implementations`, `references`, `related` | Direct [hoverAt][hover], [definitionAt][definition], [implementationsAt][implementation], [findReferences][references], [highlightRelated][related] | Disambiguate homonyms and inspect read/write access. Navigation locations alone are insufficient as declaration identities. |
| `diagnostics` for a file or file set | Direct [diagnostics][diagnostics]; facade loops over files | Preserve severity, ranges and messages. Empty diagnostics do not prove compiler acceptance. |
| `complete`, `completion_details` | Direct [completionsAt, completionDetails][completion] | Resolve details lazily; retain original file, offset, revision and `CompletionSource`. |
| `format`, `format_range`, `new_file_package_line` | Direct [formatting, rangeFormatting][formatting], [newFilePackageLine][new-file] | Produce edits and a project-aware package header. Application is separate. |
| `highlights`, `folding_ranges`, `selection_ranges`, builtin documentation | Direct [highlight][highlight], [foldingRanges][folding], [extendSelection][selection], [builtin documentation][builtins] | Preserve the remaining presentation/documentation capabilities even if the first benchmark does not need them. |
| `macro_at`, `expansion`, `expanded_file`, expansion navigation and mapping | Direct/adapt [macroCallAt, expandedMacro][macro], [expandFile and mapping objects][expanded-file], [hoverInExpansion][hover], [definitionInExpansion][definition], [sourceRangeOf, expansionRangeOf][macro-call] | Preserve expansion origin and coordinate spaces. Reading expansions does not arrange macro compilation/execution. |
| `syntax`, node/token traversal, kind/range/text, parent/children and parse errors | Adapt [loupe.syntax.parse][parse] and its `CjParse` result | Select expressions/statements and preserve comments during edits. Concrete syntax views need separate binding-map entries. |
| `declarations`, `imports`, scope lookup and `resolve` | Adapt [itemTree][items], [activeItemTree][when], [defMap][defs], [lookUp and imports][scope], [resolveBodyName][body-resolution]; positional identity lookup is a gap ([classifyName][classify]) | Expose declaration identities, modifiers, visibility and import targets. Distinguish written syntax from declarations active for the selected configuration. |
| `signature`, `body`, `inference`, `type_of` | Adapt [signatureWithSourceMap][signature], [signatureTypes][signature-types], [bodyWithSourceMap][body], [inferBody, declaredTyOf][infer], [Ty][ty] | Provide typed expression/local/pattern views and source mappings. `type_of` needs a position-to-owner/expression adapter; no public position-based type query was found at this revision. |
| `members`, `supertypes`, `subtypes`, overrides, importers, resolved calls | Adapt [membersNamed, allMembers, supertypes][members], [hierarchy queries][hierarchy], [InferenceResult][infer] | Compose impact analysis and static call graphs. Preserve overloads, selected initializers, operators and unresolved calls; do not claim a complete runtime dispatch graph. |
| Semantic rename, type relations, higher refactorings | Gap: [references][references] is not rename; [isSubtype/isAssignable][relations] are package-private | Require collision/visibility checks and handling of incomplete resolution. Scripts can propose range edits once structured views exist; guaranteed semantic refactoring needs more. |

## Session and value contract

Use an explicit workspace lifetime and short-lived read snapshots. A facade
revision counter advances on successful mutation and invalidates older analysis
contexts; it is not a raw calca identifier. Upstream snapshots are cancelled
when files change, not retained as historical databases ([implementation][db]).
Serialize root writes against request execution and translate cancellation into
a distinct Python exception. Discard interrupted analysis rather than mixing
revisions.

File handles belong to one workspace. Definition, type, body, syntax, completion
and expansion handles additionally belong to one snapshot/revision. Reject
foreign or stale handles. Snapshot closure releases retained objects; workspace
closure invalidates its contexts. Double close is harmless, and context managers
provide deterministic release. Python runtime probes must verify these rules.

Small results use immutable detached values: ranges, hover text, diagnostics,
text edits and copied location metadata. They remain readable after closure,
but their coordinates describe the original revision. A location identifies its
document, revision and coordinate space (source or a particular expansion), plus
full/focus ranges where available. Detached values must not conceal a live
`MacroCallId` or other database reference.

Large or contextual values use handles. A type view exposes tagged kind, type
arguments, declaration identity and display text. Preserve `ErrorTy`,
`TodoTy(reason)`, `UnknownTy(reason)` and absence of a value type as different
states ([Ty][ty], [inference][infer]). Expression/local identities include their
owning body. Names, rendered strings, raw integers and offsets alone are not
stable semantic identities. Completion handles retain the candidate and context.
Reacquire expansions after changes through a source anchor/key where supported,
never a persisted raw `MacroCallId` ([analysis rules][analysis-rules]).

Offsets and half-open ranges count **UTF-8 bytes**, not Python string indices.
Provide byte-range text access and explicit conversion helpers. Validate bounds,
UTF-8 boundaries and document identity. Use `None` for legitimate absence;
invalid arguments, missing/deleted files, stale handles, cancellation and
unsupported operations have distinct errors. A deleted file may retain internal
identity while disappearing from live-file enumeration ([database][db], [VFS][vfs]).

Exhaustive-query results carry coverage metadata: selected scope/configuration,
load/analysis gaps, truncation and continuation. Some upstream queries return
empty arrays for both absence and unsupported cases. Report known limitations
and mark completeness unknown where it cannot be determined. Pagination bounds
returned data; it does not necessarily bound upstream computation.

## Transformations

A script produces an edit plan with source documents, expected revision and
content hashes, byte ranges and replacement strings. Validate the entire plan
before mutation: reject overlaps, invalid boundaries, stale contents and unmapped
generated locations. Apply ranges against the same original text, for example
in descending byte order. Validate file operations alongside text edits before
publishing the new analysis state. This transaction is facade work to implement,
not an existing guarantee of `TextEdit`.

Provide preview/diff, application to the overlay, and explicit persistence.
Persistence rechecks disk contents and reports per-file failures; do not promise
atomic multi-file filesystem writes. A fresh snapshot provides post-edit
diagnostics. Compiler/test execution supplies separate validation, with failures
included in the transformation result.

Migrating calls of one API needs resolved callees/arguments, overload selection,
source mapping and edit construction. Replacing every spelling or every reference
does not implement it. Generated code and missing resolution produce skipped
cases or an incomplete plan, with reasons.

## Python execution and MCP

Keep Python bindings independent of MCP schemas. MCP needs workspace lifecycle,
Python execution with access to that workspace, and selected results/artifacts
and edit previews. Exact tool names and the execution host are a separate design
step. Define which session survives between executions; native objects and
Python globals must not be assumed to survive worker restart.

Intermediate AST/HIR objects stay in the script process. Loops, filters, joins
and aggregation finish before output enters model context. Provide concise
discoverable signatures/examples and detailed type documentation on demand.
The agent can request full results; compact output must not silently lose matches.

Illustrative desired usage, not executable with the current package:

```python
from loupe4py import Workspace

with Workspace.open(project_root) as workspace:
    with workspace.snapshot() as analysis:
        report = analysis.references(source_path, byte_offset)
        counts = {}
        for ref in report.items:
            if not ref.is_declaration:
                path = ref.location.path
                counts[path] = counts.get(path, 0) + 1
        print({"uses_by_file": counts, "coverage": report.coverage})
```

Large results may still cross the native/Python boundary. Choose wrappers,
batching and lazy views using measurements. Small MCP output alone says nothing
about conversion time or retained memory.

## Upstream requirements

1. **Identity at a position.** Navigation returns ranges; `classifyName` is
   package-private. Define neutral position-to-definition/type APIs preserving
   ambiguity and local/body ownership, or demonstrate equivalent composition
   of public queries. Avoid copying the resolver into loupe4py ([definition][definition],
   [classification][classify]).
2. **References and rename.** `findReferences` explicitly excludes names declared
   by macros. Determine other coverage limits with fixtures, expose them, and
   implement collision-aware rename separately ([references][references]).
3. **Type predicates.** Subtype/assignability helpers are package-private. If
   scripts need them, request APIs preserving unknown/error states rather than
   exposing inference's permissive boolean checks unchanged ([relations][relations]).
4. **Macro lifecycle.** Macro-server orchestration lives in cjls
   ([macro_work][macro-work]). Identify reusable neutral hosting APIs and how
   outputs reach the root database. Advertise expansion reading separately
   from workspace macro execution until both work.
5. **Composition boundaries.** Workspace diagnostic loops, aggregation, static
   call indexes and edit validation can be facade/script composition. Complete
   rename, extract/move refactorings and exhaustive dynamic call analysis are
   not established by those primitives.

Track neutral frontend changes separately from interop fixes and facade work.
Keep Python-specific dependencies outside cjls/loupe.

## Test of the token hypothesis

Hypothesis: on complex semantic tasks, Python composition over the frontend
reduces model tokens for an equally correct answer/patch compared with `rg`/grep,
file reads and ordinary Python text processing. The expected mechanism is fewer
irrelevant excerpts and fewer model-mediated joins. This is not yet measured.

| Task | Example | Independent success check |
| --- | --- | --- |
| Textual control | Find a literal or unique declaration | Expected locations; captures cases where frontend overhead outweighs savings. |
| References | Count uses despite homonyms, aliases and shadowing | Fixture reference set with declaration/read/write classification. |
| Impact analysis | Find implementations/callers affected by a signature change | Reviewed expected edges, unresolved/dynamic cases stated separately. |
| Typed structural query | Find calls satisfying receiver/type-argument conditions | Reviewed matches, overload and unknown-type cases included. |
| Transformation | Migrate one overload across multiple files | Expected locations, unrelated code preserved, build and behavioral tests. |
| Difficult inputs | Conditional compilation, Unicode, macros, missing dependencies | Expected coverage/limitations and byte ranges; check honest incompleteness. |

Use small fixtures with known answers and pinned real projects. Include negative
matches and unsupported frontend cases. Ground truth must be independent of the
facade output; fixtures alone cannot establish savings on large projects.

Run both arms with the same model/version, reasoning configuration, task wording,
initial repository state, answer requirements and resource budget. The baseline
can batch grep and use Python freely; the frontend arm gets the facade as an
additional tool and may fall back to text search. Record fallbacks. Freeze tool
instructions and count their token cost. Use repeated paired tasks, fresh agent
contexts and randomized order. Separate initial loading from workspace reuse.

Measure total input/output tokens over each complete attempt, including schemas,
docs, script generation, tool results, retries and validation. Record cache usage
and provider-reported reasoning tokens separately without double-counting them
inside output tokens. Also capture wall time, success rate, tool calls,
cold/warm initialization, conversion cost and peak memory. Retain transcripts,
patches, versions, usage records and independent verdicts.

For each pair compute `1 - frontend_tokens / baseline_tokens`. Report per-task
results and distributions across repeated runs, stratified by task class and
correctness. Include failed attempts and their token cost in overall success/cost
results; report savings on pairs where both succeed separately. Fewer tokens from
an incomplete answer do not validate the hypothesis. Choose the required saving
and tolerated success-rate difference before inspecting benchmark outcomes.

## Implementation order

1. Review this capability boundary. It addresses the first unchecked item of
   issue #4, including structured frontend access and transformations.
2. Select/validate the interop revision, reassess probes and run Python execution
   checks before changing the lock file. Map required signatures, conversions in
   both directions, nested values, ownership, binding strategy and evidence.
3. Implement the session slice: load a real project, enumerate/read files,
   update text, obtain a fresh snapshot, call hover/diagnostics/definition.
   Verify cancellation, deletion, UTF-8 and closure. This is the first end-to-end
   gate, not a token benchmark.
4. Add symbols/references, syntax/declaration/body/type views and the identity
   bridge. Add edit plans and validate a multi-file transformation. This is the
   minimum useful complex-query pilot.
5. Complete the other capability rows, macro lifecycle and contextual-handle
   tests. Account for every primary public operation and track remaining gaps.
   Validate copying, retention and large-result behavior.
6. Run the paired token experiment when the relevant capabilities work. Expand
   or optimize the API using failed tasks and measured costs, keeping correctness
   and completeness alongside token savings.

This proposal does not complete issue #4's API map or runtime acceptance criteria.

[project]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/project_model/src/project.cj#L117
[sdk]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/project_model/src/sdk.cj#L30
[vfs]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/vfs/vfs.cj#L90
[loader]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/vfs/loader.cj
[db]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/db/db.cj#L30
[symbols]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/symbols.cj#L45
[structure]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/structure.cj#L59
[hover]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/hover.cj#L54
[definition]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/definition.cj#L22
[implementation]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/implementation.cj#L16
[references]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/references.cj#L29
[related]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/highlight_related.cj#L45
[diagnostics]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/diagnostics.cj#L47
[completion]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/completion.cj#L73
[formatting]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/formatting.cj#L16
[new-file]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/new_file.cj#L15
[highlight]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/highlight.cj#L174
[folding]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/folding.cj#L68
[selection]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/selection.cj#L33
[builtins]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/builtin_docs.cj#L176
[macro]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/expand_macro.cj#L93
[expanded-file]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/expanded_file.cj#L137
[macro-call]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/hir/macro_call.cj#L190
[parse]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/syntax/syntax.cj#L19
[items]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/hir/item_tree.cj#L183
[when]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/hir/when.cj#L367
[defs]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/hir/def_map.cj#L220
[scope]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/hir/scope.cj#L476
[body-resolution]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/hir/body_resolution.cj#L106
[classify]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/defs.cj#L68
[signature]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/hir/signature.cj#L177
[signature-types]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/hir/signature_types.cj#L194
[body]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/hir/body.cj#L601
[infer]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/hir/infer.cj#L169
[ty]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/hir/ty.cj#L48
[members]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/hir/members.cj#L596
[hierarchy]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/hir/hierarchy.cj#L15
[relations]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/hir/ty_relations.cj#L201
[analysis-rules]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/docs/design/02-analysis.md
[macro-work]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/cjls/src/server/macro_work.cj
