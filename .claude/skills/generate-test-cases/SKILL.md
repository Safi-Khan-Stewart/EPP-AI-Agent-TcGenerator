---
name: generate-test-cases
description: Generate Azure DevOps test cases for an EPP User Story by ID — runs the rule-based generator, reviews and refines the result against Rules.md, then creates only the test cases the user approves in ADO, linked to the story. Use when the user gives a User Story ID and asks for test cases.
argument-hint: <user-story-id>
---

# Generate test cases for User Story $ARGUMENTS

If no User Story ID was given, ask for one.

Prefer the `epp-testcase-generator` MCP tools: they run without permission
prompts (except the push). If they aren't available, use the command line from
the repo root, where `PY` is `.venv/Scripts/python.exe` (or `python` if the venv
is missing) and `JSON` is `reports/test_cases_US<ID>.json`:

| Step | MCP tool | Command line |
| --- | --- | --- |
| Refresh domain doc | — | `PY test/_probe_repo_domain.py --force` |
| Generate | `generate_test_cases` | `PY test/ado_advisor.py --json <ID>` |
| Rules | `get_generation_rules` (with lessons) | read `Rules.md`, `LessonsLearned.md` |
| Save edits | `update_test_cases` (full list) | edit `JSON`, then `PY test/ado_advisor.py --check JSON` |
| Push | `push_test_cases` | `PY test/ado_advisor.py --push JSON --select <numbers>` |
| Browser review | `open_review_page` | `PY test/ado_advisor.py --review JSON` in the background |

## 1. Refresh the domain doc, then generate

Always refresh the domain doc first, every time a User Story ID is given (the
user asked for this): run `PY test/_probe_repo_domain.py --force` on the
command line. It reads the EPP source repos from ADO (takes a few minutes) and
rewrites the source-code section of `EPP_Portal_Business_Documentation.md`. The
generator itself uses a built-in catalogue, so the refreshed doc mainly feeds
your review in step 2: use it for real screen names, routes, roles and labels.
If the refresh fails (e.g. the PAT lacks Code (Read) scope), say so and carry
on with generation.

Generation takes about a minute and only reads from ADO. If it fails on missing
`ADO_*` variables, point the user to the Configuration section of README.md and
stop.

Note from the result: the EPP area tag, scope cues and out-of-scope items in
the generator log, the neighbouring stories used, and the test cases already
linked to the story in ADO (`existing_test_cases`).

## 2. Review against the rules

Check every test case against Rules.md:

- **Scope (RULE SCOPE 16):** nothing beyond the story's Title, Description and
  Acceptance Criteria; out-of-scope items stay out.
- **Coverage (RULE GEN 03):** every acceptance criterion has at least one test
  case. Note any that don't.
- **Title (RULE GEN 02):** starts with "Verify", no "that", names the actor
  when role-based, reads as a complete business statement. Generic or clipped
  titles such as "... correctly handles X per story spec" need rewriting.
- **Steps and expected results:** concrete actions using the story's UI labels
  and business terms, one expected result per step, no "AC1" / RULE IDs in
  the text, negative tests check the error message (RULE FUNC 11).
- **Fields:** priority 1-4; `test_type` and `test_category` from the Rules.md
  lists.
- **Duplicates:** compare with the existing test cases in ADO and with each
  other (RULE GEN 04 clubbing).

## 3. Refine

Unless the user asked for the generator output as-is, fix the real problems:
reword, merge, delete, or add a test case for an uncovered acceptance
criterion. Change only the test cases (not the story fields or `session_id`),
keep `ado_id` on any already pushed, and don't invent scope. Save, and fix
anything the validation rejects. The numbering after saving is the numbering
used for pushing.

## 4. Present in the browser review screen

Always open the browser review page with the refined test cases (the user
asked for this): `open_review_page`, or `PY test/ado_advisor.py --review JSON`
run in the background (it serves the page until the user pushes, then stops by
itself). In chat, show a table: number, title, category, type, priority. Under
it, list briefly what you changed and why, any acceptance criterion still
uncovered, any overlap with test cases already in ADO, and open questions. Tell
the user to tick the test cases they want and click "Add to ADO" on the page,
or to name the numbers in chat instead.

## 5. Push (only by the user's click or after they name the numbers)

- If the user pushed from the review page, report the created test cases from
  the server output (or the `ado_id` values now saved in `JSON`).
- If the user names numbers in chat, push exactly those (all of them only if
  they said so). If the review page is still open, stop its server first so
  it can't push the same test cases again.
- Report each created test case with its ADO link
  (`https://dev.azure.com/<ADO_ORG>/<ADO_PROJECT>/_workitems/edit/<id>`). If
  some failed, show the errors. Retrying is safe: test cases already pushed
  from this session are skipped.

If the user's feedback points at a recurring generator problem (not a one-off
wording fix), suggest `/add-lesson` so the generator is fixed too.
