# Brainstorm: Sync Check False Positive + Ralph Delegation Failure

**Date**: 2026-03-03
**Problem**: Two ADE infrastructure issues: (1) `check_plan_prd_sync()` reports false "added" markers when PLAN.md references R-markers outside "Done When" sections or when prd.json uses `legacyMarkerIds`, and (2) Ralph intermittently fails to delegate to ralph-worker sub-agents because SKILL.md references a non-existent "Task tool" instead of "Agent tool".

## Evidence Gathered

### Issue 1: Sync Check False Positive

**Confirmed via hook_audit.jsonl** (line 249): The false positive occurred on the MemeSystem project (`/f/MemeSystem`), whose `prd.json` contains a `legacyMarkerIds` field. The investigation script explicitly checked `prd.get('legacyMarkerIds', [])`, confirming the field exists in that project's prd.json.

**Root cause chain**:

1. `extract_plan_r_markers()` (`_qa_lib.py:554-561`) uses `_PLAN_R_MARKER_RE = re.compile(r"R-P\d+-\d{2}")` which matches markers **anywhere** in PLAN.md — Done When sections, Changes tables, descriptions, references, inventory tables
2. `check_plan_prd_sync()` (`_qa_lib.py:588-623`) only collects prd markers from `stories[].acceptanceCriteria[].id` — it does **not** union in `legacyMarkerIds`
3. Ralph SKILL.md STEP 1 (lines 26-30) uses the `added` field to STOP the sprint: `"If added is non-empty: display drift detected, then STOP"`
4. Result: Legacy markers documented in PLAN.md inventory tables are extracted as plan markers but not found in prd stories, producing false "added" reports that block the sprint

**Additional fragility**: `compute_plan_hash()` (`_qa_lib.py:568-585`) uses `_PLAN_R_MARKER_LINE_RE` to hash ALL lines containing markers. A marker reference in a description (e.g., "See R-P1-01 for context") adds that line to the hash, potentially causing hash mismatches even when criteria haven't changed.

**Consumer analysis**:

- `qa_runner.py` step 10 (lines 614-630): Only uses `plan_hash` — does NOT check `added`/`removed`
- Ralph SKILL.md STEP 1 (lines 26-30): Uses BOTH `added`/`removed` AND `plan_hash` — the primary consumer that blocks on false positives

### Issue 2: Ralph Not Delegating

**SKILL.md line 111**: `"Launch ralph-worker agent via Task tool with subagent_type: ralph-worker"`

**There is no "Task tool"** in Claude Code. The correct tool is the **Agent tool**. The name "Task tool" originated in early brainstorms (2026-02-27, `ralph-v3-redesign.md` and `ralph-vmodel-upgrade.md`) as a conceptual name and was never corrected when writing the production SKILL.md.

**Behavior is non-deterministic**: hook_audit.jsonl lines 262-304 show a ralph-worker WAS dispatched to a worktree (`F:\MemeSystem\.claude\worktrees\agent-afffd454`) in one session — meaning Claude sometimes infers the correct tool from the wrong name. But the user reports it often doesn't delegate, doing the work inline instead.

**Nesting PoC** (`2026-03-03-nesting-poc-results.md`): Confirmed the Agent tool is available ONLY to the top-level conversation. Sub-agents do NOT have it. Since Ralph runs as a skill (not a sub-agent), it runs in the top-level context and DOES have Agent tool access. The architecture is correct — only the tool name in the instruction is wrong.

---

## Ideas

### 1. Section-Scoped Marker Extraction (Issue 1)

Modify `extract_plan_r_markers()` to only extract markers from lines starting with `- R-P` (the "Done When" bullet format), rather than scanning the entire file.

**Implementation**: Change the regex or add a line-prefix filter:

```python
_PLAN_CRITERIA_RE = re.compile(r"^-\s+(R-P\d+-\d{2}):", re.MULTILINE)

def extract_plan_r_markers(plan_path: Path) -> set[str]:
    content = plan_path.read_text(encoding="utf-8")
    return set(_PLAN_CRITERIA_RE.findall(content))
```

- **Pros**: Precise — only extracts markers that ARE acceptance criteria. Eliminates all false positives from table references, descriptions, inventory tables. Minimal code change (one regex swap). No breaking change to consumers since return type is unchanged.
- **Cons**: Couples extraction to PLAN.md formatting convention (markers must be `- R-Pn-nn:` bullet format). If a plan uses different formatting, markers would be missed. However, this format is enforced by `plan_validator.py` so all valid plans use it.

### 2. Union in legacyMarkerIds (Issue 1)

Modify `check_plan_prd_sync()` to also include markers from `prd_data.get("legacyMarkerIds", [])` in the prd_markers set before computing the diff.

**Implementation**:

```python
prd_markers: set[str] = set()
# ... existing story criteria extraction ...
for legacy_id in prd_data.get("legacyMarkerIds", []):
    prd_markers.add(legacy_id)
```

- **Pros**: Directly addresses the confirmed root cause (MemeSystem's legacyMarkerIds). Backward compatible — projects without legacyMarkerIds are unaffected. Small, targeted change.
- **Cons**: Only fixes one symptom (legacy markers). Markers appearing in non-criteria PLAN.md sections (descriptions, tables) would still be extracted and could still produce false positives. Treats the symptom, not the root cause.

### 3. Both Fixes Combined (Issue 1)

Apply both Idea 1 (section-scoped extraction) AND Idea 2 (legacyMarkerIds union). Defense in depth.

- **Pros**: Eliminates both known false positive vectors. Section-scoped extraction prevents extraction of stray references; legacyMarkerIds union handles the prd.json side.
- **Cons**: Slightly more code to maintain. The section-scoped extraction alone would likely be sufficient since legacy markers in PLAN.md inventory tables wouldn't be extracted if they don't follow the `- R-Pn-nn:` format. But the legacyMarkerIds fix is cheap insurance.

### 4. Fix Tool Name Only (Issue 2)

Replace "Task tool" with "Agent tool" in SKILL.md line 111.

**Implementation**: Single line change.

- **Pros**: Directly fixes the naming mismatch. Makes behavior deterministic (Claude will always find the Agent tool). Trivial change, zero risk.
- **Cons**: Doesn't address potential follow-on issues — e.g., if context compaction loses the dispatch instruction and Claude falls back to inline work.

### 5. Fix Tool Name + Add Dispatch Anchor (Issue 2)

Replace "Task tool" with "Agent tool" AND add a reinforcing instruction earlier in the skill (e.g., in the header or a "Core Rule" box) that emphasizes delegation is mandatory.

**Implementation**:

```markdown
## Core Rule

Every story MUST be dispatched to a `ralph-worker` sub-agent via the Agent tool
with `subagent_type: "ralph-worker"`. Ralph NEVER implements story work directly.
```

- **Pros**: Survives context compaction better — the rule appears early in the document (more likely retained). Makes the delegation requirement unambiguous. Prevents future regression.
- **Cons**: Slightly more verbose SKILL.md. The agent definition's `isolation: worktree` already implies sub-agent usage, but explicit is better than implicit.

### 6. Fix Tool Name + Remove ralph-worker.md Outdated Constraint (Issue 2)

In addition to fixing the SKILL.md tool name, update `ralph-worker.md` line 26 which says "Sub-agents cannot spawn sub-agents." The nesting PoC proved this is technically true (Agent tool unavailable to sub-agents), but the phrasing is misleading — it was written as a behavioral instruction, not a platform fact. Clarify it to say the worker doesn't need to spawn sub-agents (it IS the leaf agent).

- **Pros**: Removes a confusing instruction that was debated across multiple brainstorms. Makes the architecture clearer.
- **Cons**: Very minor change. Low risk.

---

## Recommendation

**Issue 1**: Apply **Idea 3 (Both Fixes Combined)**.

The section-scoped extraction (Idea 1) is the primary fix — it eliminates the fundamental problem of extracting markers from non-criteria contexts. The `legacyMarkerIds` union (Idea 2) is cheap insurance for the prd.json side and directly addresses the confirmed MemeSystem scenario. Together they provide defense in depth.

The `compute_plan_hash()` function should ALSO use the section-scoped regex (`_PLAN_CRITERIA_RE`) instead of `_PLAN_R_MARKER_LINE_RE` to prevent hash instability from stray marker references. This keeps the hash and the marker extraction aligned — both only consider criteria lines.

**Issue 2**: Apply **Idea 5 (Fix Tool Name + Add Dispatch Anchor)** plus **Idea 6 (Clarify worker constraint)**.

The tool name fix is essential and non-negotiable. The dispatch anchor helps survive context compaction. Clarifying the ralph-worker constraint removes confusion documented across 5+ brainstorms.

**Why this combination**: Both issues have a clear primary fix (section-scoped regex, tool name correction) plus cheap reinforcements (legacyMarkerIds union, dispatch anchor, worker clarification). The reinforcements cost almost nothing to implement but meaningfully reduce the chance of recurrence.

## Sources

**Project docs read**:

- `PROJECT_BRIEF.md` — tech stack, constraints
- `.claude/docs/ARCHITECTURE.md` — system diagram, component tables, design decisions
- `.claude/docs/PLAN.md` — current plan (Plugin Review Integration)
- `.claude/docs/knowledge/lessons.md` — prior incidents
- `.claude/docs/HANDOFF.md` — last session context
- `.claude/hooks/_qa_lib.py` lines 545-629 — sync check implementation
- `.claude/hooks/qa_runner.py` lines 567-639 — step 10 plan conformance
- `.claude/hooks/tests/test_qa_lib.py` lines 360-495 — sync check tests
- `.claude/skills/ralph/SKILL.md` — full orchestrator instructions
- `.claude/agents/ralph-worker.md` — worker agent definition
- `.claude/docs/brainstorms/2026-03-03-nesting-poc-results.md` — Agent tool nesting limitation
- `.claude/docs/brainstorms/2026-03-03-orchestrator-infinite-context-and-speed.md` — architecture proposals
- `.claude/docs/brainstorms/2026-02-27-ralph-v3-redesign.md` — origin of "Task tool" naming
- `.claude/errors/hook_audit.jsonl` lines 240-304 — MemeSystem false positive evidence

---

## Build Strategy

### Module Dependencies

```
Issue 1 (Sync Check):
  _qa_lib.py::_PLAN_CRITERIA_RE (new regex)
    ↑
  _qa_lib.py::extract_plan_r_markers()  ←  depends on new regex
    ↑
  _qa_lib.py::compute_plan_hash()       ←  should also use new regex
    ↑
  _qa_lib.py::check_plan_prd_sync()     ←  add legacyMarkerIds union
    ↑
  qa_runner.py::_step_plan_conformance() ← no changes needed (consumer)
    ↑
  ralph/SKILL.md STEP 1                  ← no changes needed (consumer)

Issue 2 (Ralph Delegation):
  ralph/SKILL.md line 111    ←  "Task tool" → "Agent tool"
  ralph/SKILL.md header      ←  add Core Rule dispatch anchor
  ralph-worker.md line 26    ←  clarify sub-agent constraint
  (all independent of each other)
```

### Build Order

**Phase A** (can be parallel):

1. `_qa_lib.py` — new regex + extract + hash + legacyMarkerIds (all in one file)
2. `ralph/SKILL.md` — tool name fix + dispatch anchor
3. `ralph-worker.md` — constraint clarification

**Phase B** (sequential after Phase A): 4. `tests/test_qa_lib.py` — add edge-case tests for section-scoped extraction + legacyMarkerIds 5. Run full test suite — verify no regressions

All Phase A items are independent and can be built in parallel. Phase B depends on Phase A completion.

### Testing Pyramid

- **Unit tests** (90%): `test_qa_lib.py` — test `extract_plan_r_markers()` with markers in tables/descriptions (should NOT extract), test `check_plan_prd_sync()` with `legacyMarkerIds`, test `compute_plan_hash()` consistency
- **Integration tests** (10%): Run `qa_runner.py` step 10 against a PLAN.md with stray marker references and verify no false positives
- **E2E tests** (0%): Ralph delegation is a behavioral instruction — tested via manual `/ralph` run, not automated

Ratio: 90/10/0

### Risk Mitigation Mapping

| Risk                                                             | Mitigation                                                                                                                                                                            |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Section-scoped regex misses valid markers in non-standard format | `plan_validator.py` enforces `- R-Pn-nn:` format — all valid plans conform. Add unit test with edge cases.                                                                            |
| `compute_plan_hash()` change invalidates stored hashes           | Hashes are recomputed on each check. Stored hash in prd.json is updated by `/plan`. A hash mismatch would trigger a "run /plan to regenerate" message, which is the correct behavior. |
| Tool name fix doesn't fully resolve delegation failures          | Dispatch anchor in SKILL.md header provides redundant instruction. Monitor next Ralph sprint for delegation behavior.                                                                 |
| legacyMarkerIds field doesn't exist in some projects             | `prd_data.get("legacyMarkerIds", [])` returns empty list — no effect on projects without the field.                                                                                   |

### Recommended Build Mode

**Manual Mode**.

Rationale: These are 3 tightly-coupled changes to infrastructure code (hooks, skill, agent definition) with a small blast radius (5 files, ~20 lines changed). The changes are well-understood from the investigation — no ambiguity in requirements. Ralph mode adds overhead (prd.json generation, worktree setup, QA pipeline) that isn't warranted for this scope. Manual mode with targeted test runs is more efficient.
