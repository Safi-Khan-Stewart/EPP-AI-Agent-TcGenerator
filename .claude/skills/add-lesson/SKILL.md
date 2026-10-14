---
name: add-lesson
description: Turn reviewer feedback about generated test cases into a LessonsLearned.md entry AND a code fix in the generator, so the same problem doesn't come back. Use when the user reports a recurring problem with generated titles, steps, scope or tags.
argument-hint: <feedback> [user-story-id]
---

# Add a lesson learned: $ARGUMENTS

Documentation without enforcement regresses — every lesson needs both parts.
Use the command line below, not the MCP `generate_test_cases` tool: the MCP
server keeps the generator code it started with, so it won't reflect your fix
until it is restarted.

1. **Reproduce.** If a User Story ID is given (or obvious from the
   conversation), run `.venv/Scripts/python.exe test/ado_advisor.py --json <ID>`
   with `EPP_SKIP_DOMAIN_REFRESH=1` and quote the offending test case(s) from
   `reports/test_cases_US<ID>.json`. Keep that output to compare against.
2. **Find the cause.** Locate the code that produced it in
   `test/ado_advisor.py` (title builders such as `_build_condition_phrase`,
   `_clip_words`, `_normalize_title`; scope in `_extract_story_scope`;
   generation in `generate_test_cases_from_acceptance_criteria`), or the
   tagging logic in `test/domain_context.py`. Prefer fixing the root cause; add
   a guard in `_apply_lessons_learned` as well when it is a pattern that must
   never reach ADO.
3. **Fix the code** in the existing style (comments cite the lesson / rule
   number). Run `.venv/Scripts/python.exe -m py_compile` on changed files.
4. **Verify.** Regenerate for the same story and show the before/after titles
   (and steps if relevant). Also regenerate one unrelated story (e.g. `451104`
   or `432288`) to check nothing else changed unexpectedly. Run any relevant
   `test/_probe_*.py`.
5. **Record it** in `LessonsLearned.md` below the intro, above the older
   entries (newest first), matching the existing format: a `## <today's date> — <topic / story>` section with numbered
   `### <next number>. <title>` entries, each with **Symptom:** (quote the bad
   output and story ID) and **Fix —** (the functions changed). If a rule's
   wording changed, update `Rules.md` too.

Never push anything to ADO as part of this workflow.
