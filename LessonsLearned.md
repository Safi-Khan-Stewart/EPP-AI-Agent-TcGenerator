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

## 2026-09-15 — Deep story-context reading (Description → Background → Approach → Scope)

### 16. Read every narrative section, not just In-Scope / Out-of-Scope
**Symptom:** Reviewers wanted the generator to *read the whole story*
— Description, Background / Context, Business Context, Objective,
**Decision on Approach**, Technical Approach, Design, Flow, Rationale,
Assumptions, Dependencies, Impact, Risks, Notes — before generating any
TC. The previous scope reader only recognised **In Scope, Summary,
Business Context, Objective, Background, Description, Overview**, so
approach / rationale / assumption paragraphs were silently dropped and
generated TCs drifted toward generic templates.

**Fix — `_extract_story_scope` in `test/ado_advisor.py`:**
- **Header set expanded** to include: `scope`, `goal(s)`, `problem
  statement`, `context`, `decision on approach`, `approach`,
  `technical approach`, `proposed solution`, `design`, `flow`,
  `rationale`, `assumption(s)`, `dependencies`, `impacted area(s)`,
  `impact`, `risks`, `notes`.
- **Stop-set widened** so a section body no longer swallows the next
  section's header (`approach`, `assumption`, `dependencies`,
  `impact`, `risks`, `notes`).
- **`section_hits`** returned alongside `description_focus` so the
  phase-4 output shows exactly which sections were found.

### 17. Distil story-specific *vocabulary* and drive TC generation from it
**Symptom:** Even after reading the extra sections, the extra content
influenced only the `Scope cues` flags. The generated TCs still didn't
mention the story's actual nouns / feature names, so titles felt
generic.

**Fix — `_extract_story_scope`:**
- New `story_terms` list distilled from `description_focus + title`
  via a lightweight regex that captures:
  - **2-3 word Title-Cased phrases** (e.g. `Sender Display Name`,
    `Onboarding Generation Link`, `Payment Monitoring`, `Approver
    Validation Rules`),
  - **ALL-CAPS acronyms** (`ACH`, `RTP`, `IBA`, `GIS`, `EMD`, `CSV`),
  - **Quoted phrases** (`"From"`, `"Stewart"`).
- A stop-word set filters out generic words (`The`, `System`, `EPP`,
  `Story`, `Context`, …).
- The list is capped at 12 terms and surfaced in phase 4 as a
  `Story terms :` line so the reviewer can see what the generator
  latched onto.

### 18. `RULE FOCUS 19` — one laser-focused TC per story term
**Fix (new rule):** For up to **3 surviving story terms**, the
generator now emits a dedicated TC whose title, steps and expected all
mention the term verbatim. Every step / expected string embeds the
term in quotes, so the tester can trace the TC directly back to the
story's own language.

Rule guard-rails:
- Skip a term when it's already visible in an existing TC's title
  (avoids duplication with AC-driven TCs).
- Steps quote the nearest matching `description_focus` line so the TC
  reproduces the story scenario, not a template.
- Priority 2, category **Functional**, `ac_ref` = `Focus: <term>`.

**Rule addition — RULE FOCUS 19:** The generator must produce at least
one TC per distinctive noun / acronym / quoted term extracted from the
User Story's narrative sections (up to 3), so coverage is anchored to
the story's own vocabulary.

---

## 2026-09-15 — Historical enrichment fully removed from TC bodies

### 15. Historical enrichment must not appear in the Objective either
**Symptom:** After Lessons 7 and 10 moved historical enrichment out of
Preconditions and into the Objective, reviewers pushed back — the
Objective is a *behavioural statement about the story under test*, not
a place for cross-story audit trails. The `Historical baseline: …` and
`Historical enrichment applied: … — Reference prior stories: #…`
sentences were still noise, just relocated.

**Root cause:** Two separate code paths were still writing history
into user-visible fields:
1. The per-TC enrichment loop wrote `Historical baseline` / `Also
   exercises` / `Keeps parity` / `Data shapes should remain compatible`
   sentences into `objective`.
2. The per-story anchor block wrote `Historical enrichment applied … —
   Reference prior stories …` as an audit sentence on the first TC's
   `objective`.

**Fix (`test/ado_advisor.py`):**
- **All user-visible historical enrichment removed.** The per-TC
  enrichment loop no longer mutates `objective` for AC-driven,
  negative, security, data or happy-path TCs. Only workflow / API TCs
  still get a *behavioural* extra step (`Smoke-check the '{kw}'
  regression path …`) — that step describes the system under test, not
  the history.
- **Per-story audit sentence removed.** The `Historical enrichment
  applied … Reference prior stories: #… ` block no longer touches
  Objective.
- **`_apply_lessons_learned` scrubber tightened.** A single regex
  (`_HIST_RX`) now strips any surviving `Historical baseline`,
  `Historical enrichment applied`, and `Reference prior stories …`
  fragments from **every** user-visible field — Title, Objective,
  Preconditions, Overall Expected, Steps and Expected.
- **Where history still lives.** The `history_ctx` object is fully
  intact and continues to render the "Historical Context Used" panel
  on the review page (`RULE HIST 15`), so testers can still see which
  neighbouring stories informed generation. It just never leaks into
  the TC body pushed to ADO.

**Rule update — RULE HIST 15:** Historical context is a *reviewer
transparency* concern, not a test-case concern. It lives on the review
page and (optionally) in generator logs. It never appears on the TC.

---

## 2026-09-15 — Third round of feedback from US #518468 (edge-case polish)

### 12. Edge-case Step 1 was still `Log in to the EPP`
**Symptom:** The `RULE EDGE 18` block called `domain.get('portal') or 'EPP'`
directly instead of the portal-inference helper introduced in Lesson 8,
so edge TCs for the SendGrid story still read `Log in to the EPP` even
though the story is clearly an Admin-portal + email flow.

**Fix (`test/ado_advisor.py`):**
- Extracted the portal-inference logic into a shared helper
  `_resolve_portal(portal_label, title)` and swapped **every** call site
  (AC loop, happy-path, negative, workflow, edge-case) to use it.
  Portals now resolve consistently across all TC families.
- `_resolve_portal` also recognises `sendgrid` as an Admin-portal cue.

### 13. Email-flow edges must verify the mailbox, not just the API
**Symptom:** Edge TCs for the SendGrid story didn't ask the tester to
open the recipient's mailbox (e.g. Gmail) to confirm the delivered
email — arguably the most important verification for a template story.

**Fix (`test/ado_advisor.py`):** The `RULE EDGE 18` builder now detects
email cues (`email`, `sendgrid`, `mailbox`, `inbox`, `recipient`) in
the story blob and, when they fire, inserts an explicit mailbox
verification step and its own expected result:

- **Extra step:** *Open the recipient's mailbox (e.g., Gmail) and
  inspect the delivered email content, headers and any leaked
  placeholders.*
- **Extra expected:** *Recipient's mailbox shows exactly one email
  whose subject, body, logo, support-email link and template render as
  specified — no `{{placeholder}}` tokens are visible.*
- Preconditions also grow a `test mailbox available` line for email
  flows.

### 14. Edge-case titles were still being truncated at ~120 chars
**Symptom (TC 2 / TC 3):**
> Verify … behaves gracefully when the SendGrid template ID
> Verify … still renders when optional payload fields (logo

The `RULE GEN 02` hard cap (120 chars) was chopping natural sentences
whose feature label alone was ≥ 65 chars.

**Fix:** raised the `_normalize_title` cap to **150 chars**. Dangling-
verb / dangling-operator sweeps still run, so a longer title still
never ends on `the`, `ID`, `(`, `=`, etc. Titles that don't need the
extra room stay short.

---

## 2026-09-15 — Second round of feedback from US #518468

### 10. `Historical enrichment applied …` still leaking into Preconditions
**Symptom:** The audit-trail sentence
> • Historical enrichment applied: Approval — Reference prior stories: #429086, #432937, #447423

was still being attached to the **Preconditions** field of the first
generated TC, even after Lesson 7 moved the *baseline* bullet out.

**Root cause:** Two separate code paths write historical context —
(a) the per-TC `Historical baseline` bullet (fixed in Lesson 7), and
(b) the per-story `Historical enrichment applied` audit-trail bullet
appended to the first TC. Only (a) was moved to the Objective.

**Fix (`test/ado_advisor.py`):**
- The audit-trail sentence is now appended to the anchor TC's
  **Objective** (with a period), not to Preconditions.
- `_apply_lessons_learned` gains a defensive sweep that, for every TC,
  strips any leftover `Historical baseline` / `Historical enrichment
  applied` lines from Preconditions and re-homes them on the Objective.
  This closes the door on any future code path that tries to write
  history into Preconditions again.
- **Rule reinforcement — RULE HIST 15:** All historical context is a
  narrative field concern (Objective / step notes). The Preconditions
  field is reserved for concrete setup steps a tester can reproduce.

### 11. Add story-driven Edge-Case coverage — RULE EDGE 18
**Symptom:** Reviewers wanted at least one edge-case TC when the story
touches obvious failure modes (template misconfiguration, missing
optional payload fields, transient provider failures, Unicode input,
audit trail completeness). The retired data-variation block was too
generic; nothing had replaced it.

**Fix (`test/ado_advisor.py`):** new `RULE EDGE 18` block. It scans
`story_blob` (title + description + AC) for concrete cues and emits
**one targeted edge-case TC per cue that fires**, with a real action
step and an expected outcome grounded in the cue itself:

| Cue keyword(s)                                             | Edge case generated                                    |
|-----------------------------------------------------------|--------------------------------------------------------|
| `sendgrid`, `template`, `template id`                     | Template ID missing / misconfigured → safe fallback    |
| `payload`, `extra field`, `new field`, `extended`         | Optional payload fields null → no leaked placeholders  |
| `retry`, `transient`, `rate limit`, `429`, `5xx`          | Transient provider failure → retry, no dup emails      |
| `unicode`, `emoji`, `non-ascii`, `international`, `accent`| Unicode payload round-trip                             |
| `audit`, `log`, `correlation`                             | Complete audit trail for success / fail / retry        |

Each edge TC is:
- **Story-driven** (only fires when the cue is genuinely present),
- **Not a data-variation clone** (has its own action + expected),
- **Deduplicated** by `ac_ref` so re-runs don't produce duplicates,
- **Priority 2, Regression**, category `Negative` for failure-mode
  edges and `Functional` for happy-path edges.

Extend the table above whenever a new domain-specific edge is worth
covering across the platform (e.g. currency rounding, timezone
boundaries, feature-flag ON/OFF).

---

## 2026-09-15 — Feedback from US #518468 (SendGrid template payload)

### 7. Historical baseline was polluting Preconditions
**Symptom:** Negative/security TCs got a `• Historical baseline: prior
stories …` bullet added to the **Preconditions** field. Preconditions
are supposed to be a concrete reproduction checklist; narrative
context belongs in the Objective.

**Fix (`test/ado_advisor.py` — history enrichment block):**
- Historical-baseline enrichment for negative / security TCs is now
  appended to the **Objective** via `_join_sentence`, not to
  Preconditions.
- **Rule reinforcement — RULE HIST 15:** Historical context enriches
  narrative fields (Objective / step notes); it never appears in the
  Preconditions checklist.

### 8. Test-step ambiguity — vague portal, redundant navigation, meaningless "set up preconditions" step
**Symptom (steps for TC on US #518468):**
1. `Log in to the EPP as a User` — which EPP application?
2. `Navigate to the <feature> screen / functionality` — reads as
   filler when the feature label *is* the whole story title.
3. `Set up preconditions from GIVEN` — restates what's already in the
   Preconditions field.
4. Downstream step numbers become inconsistent.

**Fix (`test/ado_advisor.py` — AC step builder):**
- **Step 1 portal disambiguation.** When `domain.get('portal')` returns
  the bare `EPP`, the builder now infers a concrete portal from the
  story title: `AP Admin Portal` (Admin / A/P stories),
  `Escrow Customer Portal`, `Escrow Dashboard` (default for Escrow &
  Payment Monitoring), `Parties Onboarding Portal`. Step 1 always
  reads `Log in to the <concrete portal> as a <role>`.
- **Step 2 pruning.** The generic `Navigate to the <feature> screen /
  functionality` step is dropped unless we have a real route
  (`domain['route']`) or a distinct screen name that isn't already
  part of the feature label.
- **Removed the "Set up preconditions from GIVEN" step.** The GIVEN
  clause is already surfaced in the Preconditions field — restating it
  as a step was noise.
- **Rule addition — RULE STEP 17:** Steps must be *actionable and
  non-redundant*. Never leave Step 1 as bare `EPP`. Never restate the
  Preconditions field as a step. Skip navigation steps when the
  feature label is the target screen.

### 9. Titles clipped mid-object for outcome-verb patterns
**Symptom (TC 1):**
> Verify Admin: Update SendGrid Email Templates with Extended Payload sends the new

The condition builder recognised the outcome-verb pattern (`sends`) and
routed it through `_clip_words(max_words=8)`, but 8 words was too tight
for typical `<verb> the <object> …` prose.

**Fix (`test/ado_advisor.py`):**
- Outcome-verb branch now uses `max_words=12`, and the generic
  fallback uses `max_words=10`, so the verb's object survives the clip.
- Dangling-verb / dangling-operator sweeps still run, so we never end
  on `sends`, `contains`, `=`, etc.
- **Rule tightening — RULE GEN 02 (titles):** Never clip so tight that
  the outcome verb's object is lost. Titles up to ~90 chars are
  preferred over amputated 60-char fragments.

---

## 2026-09-15 — Description-driven scope analysis (visibility)

### 6. Prove the generator reads the Description, not just the ACs
**Symptom:** Reviewers weren't sure whether the generator considered the
User Story **Description** (Summary / Business Context / In Scope /
Out of Scope) or only the Acceptance Criteria block. When the AC was
sparse, the generator sometimes felt like it was guessing.

**Root cause:** `_extract_story_scope` already parsed **Out of Scope**
markers, but there was no equivalent extraction for the positive
Description sections (Summary / In Scope / Business Context / Objective
/ Background / Overview) and none of the scope analysis surfaced in the
phase-4 output. So the analysis existed but was invisible.

**Fix (in `test/ado_advisor.py`):**
- `_extract_story_scope` now also parses named sections from the
  Description (`Summary`, `In Scope`, `Business Context`, `Objective`,
  `Background`, `Description`, `Overview`) and returns them as
  `description_focus` (max 8 short phrases).
- Phase 4/5 of the runner prints:
  - the number of characters analyzed from the Description,
  - the top `In-Scope` focus phrases,
  - the `Out-of-Scope` exclusions (so testers see what's being skipped),
  - a compact `Scope cues` line listing which expansion families
    (`ui`, `data`, `workflow`, `security`, `multi_role`) the story
    activated, or `AC-only (no extra expansions)` when nothing else
    fires.
- **Rule reinforcement — RULE SCOPE 16:** Description + Scope sections
  are first-class inputs to test-case generation. Every run must show
  which sections were read, so reviewers can trust the output.

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


## Lesson 2026-09-15 — Related work-item context + weighted term scoring

**Symptom.** Generated TCs occasionally missed module-history vocabulary
(terms established in the Parent Feature or sibling stories) and, when
several terms were extracted from the Description, low-signal terms
sometimes ranked above high-signal ones (Approach / Scope), producing
generic focused TCs.

**Fix.**
1. Added `_fetch_related_story_context(work_item_id, area_path)` which
   pulls Parent / Related links AND recent stories in the same
   `System.AreaPath` (best-effort, silent on failure) and returns a
   concatenated Description+AC blob plus the related IDs / titles.
2. `_extract_story_scope(...)` now accepts a `related=` kwarg. The
   related blob is added as a low-weight source (0.8) so it can BOOST
   an existing term but rarely introduces a new top-N term alone.
3. Replaced the flat de-dupe list for `story_terms` with a WEIGHTED
   score: `score = Σ (section_weight × occurrences)`. Weights:
   Approach / Decision on Approach / Scope = 4.5–5.0, Objective /
   Goals = 4.0, Description / Summary = 3.0, Background / Context =
   2.5, Assumptions / Dependencies = 2.0, Notes = 1.5, Title = 5.0,
   AC = 1.5, Related = 0.8. Top-12 by score become `story_terms`;
   RULE FOCUS 19 picks the top 3 for laser-focused TCs.
4. Surfaced `story_term_scores`, `related_ids`, `related_titles` on
   the scope dict and printed them in phase 4 for reviewer
   transparency (terms shown with their scores, related items
   listed by ID + title).
5. Folded `related_blob` into `story_blob` so downstream keyword
   checks (edge-case triggers, portal resolution, security cues)
   also see module-history vocabulary.

**Effect.** Focused TCs now consistently target the highest-signal
story vocabulary first, and pick up terms that only exist in the
Parent Feature / sibling stories — eliminating generic fill-in TCs.
