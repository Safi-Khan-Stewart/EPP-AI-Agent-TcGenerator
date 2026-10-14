# EPP AI Test Case Generator — Claude instructions

Python tooling for the **Enterprise Payments (EPP)** project in Azure DevOps
(org `StewartTitle`). Given a User Story ID it generates test cases that follow
[Rules.md](Rules.md), lets a reviewer pick which ones to keep, and creates them
as ADO Test Case work items linked to the story. It also produces sprint status
and DevOps advisor reports.

The generator itself is rule-based Python (no LLM calls). Claude's job is to
drive it, review and refine its output against Rules.md, and push only what the
user approves.

## Layout

`test/` is the source folder (despite the name):

| File | Purpose |
| --- | --- |
| `test/ado_advisor.py` | Main CLI: test case generation, review page, ADO push, advisor report |
| `test/domain_context.py` | EPP portal / screen / role catalogue + EPP area tag (RULE TAG 14) |
| `test/history_context.py` | Prior stories in the same Area Path (RULE HIST 15) |
| `test/sprint_status.py` | Current sprint HTML report |
| `test/mcp_server.py` | MCP server exposing the generator to Claude Desktop / Claude Code |
| `test/_probe_*.py`, `test/_smoke_domain.py` | Ad-hoc probes and smoke checks (run directly with Python) |
| `Rules.md` | **Single source of truth** for test case rules |
| `LessonsLearned.md` | Reviewer feedback; enforced in code by `_apply_lessons_learned` |
| `EPP_Portal_Business_Documentation.md` | Domain knowledge used by `domain_context.py` |
| `reports/` | Generated output (gitignored): review JSON + HTML |

## Running

- Python: use `.venv/Scripts/python.exe` (it has `requests`, `fpdf`, `jinja2`, `mcp`).
  Fall back to `python` only if the venv doesn't exist.
- Required environment variables: `ADO_ORG`, `ADO_PROJECT`, `ADO_PAT` (see README).
  Never print, echo or log `ADO_PAT`.

Test case generation commands (`<ID>` = User Story ID):

```
.venv/Scripts/python.exe test/ado_advisor.py --json <ID>          # generate -> reports/test_cases_US<ID>.json (read-only on ADO, ~1 min)
.venv/Scripts/python.exe test/ado_advisor.py --check <json>       # re-validate an edited JSON, re-number, list TCs
.venv/Scripts/python.exe test/ado_advisor.py --push <json> --select 1,3-5   # WRITES to ADO
.venv/Scripts/python.exe test/ado_advisor.py --review <json>      # browser review page (blocks; run in background)
.venv/Scripts/python.exe test/ado_advisor.py <ID>                 # original flow: generate + browser review (blocks)
```

Other reports: `test/sprint_status.py` (writes `sprint_status.html`) and
`test/ado_advisor.py` with no arguments (advisor + `sprint_report.html`).

Use the `/generate-test-cases`, `/sprint-status` and `/add-lesson` skills for
these workflows.

The `epp-testcase-generator` MCP server (`.mcp.json`) exposes the same
operations as tools; prefer them when available. In the PowerShell tool,
permission rules can't pre-approve commands that contain file paths, so the
command-line route prompts on every run. The server loads the generator code
once: after editing `test/*.py`, use the command line (or reconnect the
server via `/mcp`) to see the change.

## Hard rules

- **Never write to Azure DevOps without explicit approval.** `--push`, the MCP
  `push_test_cases` tool and the review page's "Add to ADO" button all create
  real work items. Push only the test case numbers the user named in this
  conversation; "looks good" about a list is not approval to push it.
- Don't start the blocking browser flows (`ado_advisor.py <ID>` without
  `--json`, or `--review`) in the foreground — they serve a page until the user
  pushes or presses Ctrl+C. Run them in the background.
- **Rules.md is the single source of truth.** When refining test cases, obey
  RULE SCOPE 16: the story's Title, Description and Acceptance Criteria are the
  only source of scope — never add roles, screens, data flows or workflows the
  story doesn't mention.
- **Lessons must be enforced in code.** When adding to `LessonsLearned.md`,
  also extend `_apply_lessons_learned` (or the helpers it calls) in
  `test/ado_advisor.py`; documentation without enforcement regresses.
- **When the user gives a User Story ID:** always run
  `test/_probe_repo_domain.py --force` first (it rewrites the source-code section
  of `EPP_Portal_Business_Documentation.md`). Once the test cases are generated
  and refined, always open them in the browser review screen (`--review`, in
  the background). Both are the user's standing preference.
- On its own, the generator re-runs that refresh only every 14 days. Set
  `EPP_SKIP_DOMAIN_REFRESH=1` to skip it, e.g. for code test runs; never for a
  user's story request.

## Review session JSON

`reports/test_cases_US<ID>.json` is the hand-off between generate, review and
push. Edit only the `test_cases` array. Each test case needs `title`,
`steps[]`, `expected[]` (one per step, never more than steps) and accepts
`objective`, `preconditions`, `overall_expected`, `priority` (1-4),
`test_type` (Integration, Master, One-time validation, Performance, Regression,
Smoke, Smoke & Regression) and `test_category` (API, Functional, Negative);
anything missing gets the Rules.md default. `--check` (and every push)
re-applies the LessonsLearned guardrails and rejects invalid values. Test cases
that carry an `ado_id` were already pushed and are skipped on later pushes.
The review page has an inline editor whose saves also go into this JSON, so
re-read it before reporting or pushing after the user has used the page.
`existing_test_cases` lists test cases already linked to the story in ADO.

## Code conventions

- Match the existing style: progress printed as `[n/5]` phases with aligned
  labels, comments that cite the rule they implement (`RULE GEN 02`, `Lesson 4`).
- Working-copy files use CRLF line endings.
- No test suite; verify changes by running `--json` against a real story (e.g.
  `451104`, `432288`) and comparing the generated titles before/after, plus
  the relevant `_probe_*.py` script.
