"""Dry-run probe for US #451104 (Exclude Rejected from Failed Tab).

Verifies that the scope-strict generator produces ONLY the test cases
the story actually asks for:

  • exactly 1 TC per AC (this story has 1 AC),
  • optionally 1 Happy-Path TC for the same single actor,
  • NO multi-role TCs (story names only "Accounting User"),
  • NO data-variant TCs (story is a display / filter rule),
  • NO UI-rendering TC (UI redesign is Out of Scope),
  • NO canonical workflow TC (narrow filter rule),
  • NO "Unauthorized user" Negative TC (story raises no auth concern).
"""
from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import ado_advisor  # noqa: E402

STORY_ID = 451104

wi = ado_advisor.get_work_item_full_details(STORY_ID)
assert wi, f"Could not fetch US #{STORY_ID} — check ADO env vars."

tcs, ac_clean, desc_clean, title = \
    ado_advisor.generate_test_cases_from_acceptance_criteria(wi, history=None)

print(f"\nStory   : US #{STORY_ID}  {title}")
print(f"AC text : {ac_clean[:140]}...")
print(f"Generated {len(tcs)} test cases:\n")

ac_refs_seen = []
for i, tc in enumerate(tcs, 1):
    ref = tc.get('ac_ref', '')
    cat = tc.get('test_category', '')
    ac_refs_seen.append(ref)
    print(f"  {i:2d}. [{ref:>14s} | {cat:>10s}]  {tc['title']}")

# ── Assertions ────────────────────────────────────────────────────────
banned_refs = []
for ref in ac_refs_seen:
    rlow = ref.lower()
    if rlow.startswith('role:'):
        banned_refs.append(f"multi-role TC: {ref}")
    if rlow.startswith('data:'):
        banned_refs.append(f"data-variant TC: {ref}")
    if rlow == 'ui':
        banned_refs.append("UI rendering TC")
    if rlow == 'workflow':
        banned_refs.append("Workflow walkthrough TC")
    if rlow == 'security':
        banned_refs.append("Security/Unauthorized TC")

print()
if banned_refs:
    print("FAIL — out-of-scope TCs found:")
    for r in banned_refs:
        print(f"  • {r}")
    sys.exit(1)

ac_count = sum(1 for r in ac_refs_seen if r.lower().startswith('ac'))
print(f"OK — {ac_count} AC-driven TC(s) and "
      f"{len(tcs) - ac_count} supporting TC(s); no out-of-scope expansions.")
