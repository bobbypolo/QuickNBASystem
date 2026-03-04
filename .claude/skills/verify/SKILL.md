---
name: verify
description: Run verification steps for the current phase.
agent: qa
context: fork
---

## Verification Process

1. **Read the Plan**
   - Open `.claude/docs/PLAN.md`
   - Identify the current phase (first phase not marked Complete)
   - Extract the "Done When" criteria, "Verification Command", and story ID
   - Identify the prd.json story corresponding to the current phase

2. **Run Automated QA Steps via qa_runner.py**

   Run the automated QA runner to execute all 12 steps programmatically:

   ```bash
   python .claude/hooks/qa_runner.py \
     --story [STORY-ID] \
     --prd .claude/prd.json \
     --test-dir .claude/hooks/tests \
     --changed-files [comma-separated list from git diff] \
     --checkpoint [base-commit-hash] \
     --plan .claude/docs/PLAN.md
   ```

   - Parse the JSON output from qa_runner.py
   - All 12 steps are fully automated (no manual review steps)
   - If qa_runner.py is not available, fall back to running verification commands manually

3. **Run Plan Verification Command**
   - Execute the verification command from the plan
   - Capture full output including any errors
   - Note exit codes

4. **Check Each Criterion**
   - Go through each "Done When" item
   - Mark as PASS or FAIL with evidence
   - For subjective criteria, provide reasoning

5. **UI Verification (if applicable)**
   - If the phase involves UI changes, use Playwright/Stagehand
   - Navigate to relevant pages
   - Verify visual and functional requirements
   - Capture screenshots as evidence

6. **Generate Human-Readable Report**

   Display the report in the following format (preserves existing human-readable output):

   ## Verification Report - Phase [N]: [Name]

   **Date**: [timestamp]

   ### Automated Checks (qa_runner.py)

   | Step | Name | Result         | Evidence  |
   | ---- | ---- | -------------- | --------- |
   | 1    | Lint | PASS/FAIL/SKIP | [summary] |
   | ...  | ...  | ...            | ...       |

   ### Done Criteria

   | Criterion     | Status    | Evidence        |
   | ------------- | --------- | --------------- |
   | [criterion 1] | PASS/FAIL | [output/reason] |
   | [criterion 2] | PASS/FAIL | [output/reason] |

   ### Overall Result: PASS / FAIL

   ### Issues Found
   - [List any issues that caused failures]

   ### Recommendations
   - [Any suggestions for fixes or improvements]

   ***

7. **Append JSONL Entry to Verification Log**

   After generating the human-readable report, append a structured JSONL entry to `.claude/docs/verification-log.jsonl` (create if it does not exist).

   Each entry is a single JSON object on one line with the following schema:

   ```json
   {
     "story_id": "[STORY-ID]",
     "timestamp": "[ISO 8601 timestamp]",
     "attempt": 1,
     "qa_steps": [
       {"step": 1, "name": "lint", "result": "PASS", "evidence": "...", "duration_ms": 120},
       ...
     ],
     "spot_check": null,
     "overall_result": "PASS|FAIL",
     "criteria_verified": ["R-PN-01", "R-PN-02"],
     "files_changed": ["file1.py", "file2.py"],
     "production_violations": 0
   }
   ```

   This log is append-only. Do not overwrite existing entries. Each `/verify` run adds one line.

   If qa_runner.py produced JSON output, use its `steps` array directly for the `qa_steps` field. Otherwise, construct the entry from manual verification results.

8. **Persist Human-Readable Summary to verification-log.md**

   Also append a summary block to `.claude/docs/verification-log.md` (create if it does not exist):

   ```
   ---
   ## Phase [N]: [Name] -- [PASS/FAIL]

   **Date**: [timestamp]
   **Verification Command Exit Code**: [0 or error]

   | Criterion (ID)       | Result    | Key Evidence        |
   | -------------------- | --------- | ------------------- |
   | R-PN-01: [criterion] | PASS/FAIL | [one-line evidence] |

   **Mock Quality**: [PASS -- no issues / FAIL -- list issues]
   **Plan Conformance**: [PASS -- no unexpected files / FAIL -- list unexpected files]
   **Notes**: [any warnings or observations]
   ---
   ```

   This log persists across sessions. Do not overwrite -- always append.

## After Verification

If overall result is **PASS**:

1. Clear workflow state flags by running tests (which triggers `post_bash_capture.py` to clear `needs_verify` and `prod_violations` in `.workflow-state.json`), or note that the verification run itself has already cleared the flags.
2. Report: "Verification passed. Marker cleared."

If overall result is **FAIL**:

1. Do NOT clear the marker
2. Report which checks failed
3. Builder must fix issues before re-running /verify

## Failure Protocol

- If **FAIL**: Do not proceed to next phase
- Report issues clearly so Builder can address them
- Do not attempt fixes (that's Builder's job)
