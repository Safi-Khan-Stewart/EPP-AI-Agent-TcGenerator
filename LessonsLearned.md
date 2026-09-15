# Lessons Learned — AI Test Case Generator

A running log of feedback collected while running the generator against real
Enterprise Payments (EPP) User Stories, and the improvements made in response.
Each entry lists **what went wrong**, **root cause**, and the **rule / code change**
applied so we don't regress.

> **Automated enforcement.** Every test case produced by
> `generate_test_cases_from_acceptance_criteria` is now passed through the
> `_apply_lessons_learned` scrubber in `test/ado_advisor.py` before it is
> shown on the review page or pushed to ADO. The scrubber loads this file
> at run time and prints the active lesson headings during **Phase 4/5**
> of the generator output (look for the `Guardrails :` line). Any TC that
> hits a hard block (e.g. a retired category) is dropped and reported as
> `Dropped : N TC(s) blocked by lessons-learned guardrails`.
>
> **When you add a new lesson here, also extend `_apply_lessons_learned`
> (or one of the helpers it calls — `_normalize_title`, `_clip_words`,
> `_build_condition_phrase`, `_clean_clause`) so the rule is actually
> enforced. Documentation without enforcement will regress.**

---

## 2026-09-15 — Feedback from US #533032 (Update GIS Sender Email)

### 4. Titles ending on a dangling transitive verb
**Symptom (TC 1):**
> Verify A/P: Update GIS Sender EMail sender display name should not contain

`contain` is a transitive verb whose object was clipped. The title
reads as an incomplete sentence.

**Root cause:** `_normalize_title` and `_clip_words` only removed
trailing **function words** (a / the / in / of / …). Transitive verbs
like `contain`, `include`, `point`, `match`, `send`, `return`,
`display`, `show`, plus modals `should / shall / will / must`, could
still land as the last word after the 90-char cut.

**Fix (in `test/ado_advisor.py`):**
- New `_TRAILING_DANGLING_VERBS` frozenset covering the common
  transitive verbs and modals.
- `_clip_words._is_junk_tail` and `_normalize_title` now drop trailing
  tokens matching this set (with a safety guard: never leave fewer
  than 3 words in the title).
- **Rule update — RULE GEN 02 (titles):** A title must end on a
  complete outcome. Never on a preposition, article, dangling verb,
  or modal.

### 5. HTML entities leaking into titles / steps
**Symptom (TC 2):**
> Verify A/P: Update GIS Sender EMail &quot;From&quot

The AC text came back from ADO with HTML-encoded quotes (`&quot;`)
that were not decoded before parsing.

**Root cause:** `_clean_clause` collapsed whitespace and stripped
bullets, but did not run `html.unescape` on the raw AC text.

**Fix:** `_clean_clause` now calls `html.unescape` before any regex
work. All entities (`&quot;`, `&amp;`, `&nbsp;`, `&#39;`, `&lt;`,
`&gt;`, etc.) are decoded to their real characters, so titles and
steps read as plain English.

---


## 2026-09-02 — Feedback from US #442914 (Manager Takes Ownership API)

### 1. Generic data-variation TCs are noise — remove them
**Symptom (TC 6 – TC 10):** Every story ended up with a fixed block of six
"data variation" test cases:

- `Verify … submission with valid data`
- `Verify … submission with invalid data`
- `Verify … submission with empty/null inputs`
- `Verify … submission with special characters`
- `Verify … submission with maximum-length values`
- `Verify … submission with minimum-length values`

These were not tied to any specific field in the AC, duplicated the
AC-driven negative test, and cluttered the review page.

**Root cause:** `RULE COV 08 + RULE DATA 09` fired whenever
`scope['allow_data']` was true, regardless of whether the AC actually
described field-level validation.

**Fix:**
- Removed the entire data-variant loop from
  `generate_test_cases_from_acceptance_criteria` in `test/ado_advisor.py`.
- Kept the block as a commented-out marker referencing this entry so
  future contributors know why it was retired.
- **New rule (going forward):** Data-boundary coverage must come from the
  AC itself (or a dedicated data-driven story). The generator will never
  auto-fabricate boundary/format TCs.

### 2. Titles leaking raw AC prose — TC 4 was incomplete / logic-less
**Symptom (TC 4):**
> Verify Payment Disbursement: Manager Takes Ownership EPP shall: Set assignedApproverId =

The title carried through the AC subject (`EPP shall:`) *and* was chopped
mid-assignment (`assignedApproverId =`). It reads like a fragment of
source code, not a test case.

**Root cause:**
1. `_build_condition_phrase` only stripped the classic subjects
   ("the system shall", "user will"). It did **not** strip
   product/component-name subjects such as `EPP shall:`, `API shall:`,
   `Service should:`.
2. `_clip_words` kept dangling operators (`=`, `:`, `->`) and lone
   camelCase identifiers at the end of a fragment, so the 8-word clip
   ended on `assignedApproverId =`.
3. `_normalize_title` didn't post-clean trailing assignments either.

**Fix (in `test/ado_advisor.py`):**
- `_build_condition_phrase`: subject-strip regex now also removes
  `epp / api / service / platform / portal` followed by optional
  `:` / `-` and optional modal (`shall / must / should / will / can`).
  Also handles the "no verb" pattern (`EPP: <action>`).
- `_clip_words`: new `_is_junk_tail` helper drops trailing tokens that
  end in `=`, `:`, `->`, `=>`, `<-`, `<=`, `>=`, and drops lone
  camelCase `…Id` identifiers left behind after a clipped assignment.
- `_normalize_title`: adds a final sweep that removes patterns like
  `set <camelCaseIdentifier> =` and `<Word>Id =` from the tail.

### 3. Rule updates
- **RULE COV 08 / DATA 09 — RETIRED.** No auto-generated data-variation
  TCs. If a story needs field-level validation coverage, the AC must
  spell out the field, format, and boundaries.
- **RULE GEN 02 (titles) — TIGHTENED.** A title must never end on an
  operator, a lone identifier, or a trailing function word. The
  subject prefix (`EPP shall`, `API must`, `Service will`, etc.) must
  be stripped before the feature label is prepended.

---

## How to add new lessons
When a reviewer flags a bad TC:
1. Record the **story ID + TC number** and quote the bad title / body.
2. Identify the **rule** (or missing rule) that let it through.
3. Land the **code change**, then link the commit / PR from this file.
4. Update `Rules.md` if the rule wording itself changed.
