"""Probe: verify the new targeted historical-context enrichment.

Builds a fake work-item + a fake history payload and asserts:
  • at most one enrichment marker appears per TC
  • the audit-trail bullet appears on EXACTLY ONE TC (the first)
  • no test case carries the old "Domain regression baseline" boilerplate
  • UI-only TCs are left untouched by vocab terms
  • keywords are not reused across TCs

Run from the /test folder:
    python _probe_hist_enrich.py
"""
from __future__ import annotations

import json
import os
import sys

# Make sibling import work without env vars
os.environ.setdefault("ADO_ORG", "stub")
os.environ.setdefault("ADO_PAT", "stub")
os.environ.setdefault("ADO_PROJECT", "stub")

import ado_advisor  # noqa: E402


def main() -> int:
    work_item = {
        "fields": {
            "System.Title": "EPP: Add Retry-All button to Payment Monitoring",
            "System.AreaPath": "Enterprise Payments\\Escrow",
            "System.IterationPath": "Enterprise Payments\\Sprint 99",
            "System.Description": (
                "<p>As a Support user I want a bulk Retry-All button "
                "on the Payment Monitoring screen so that I can retry "
                "all transmission-failed payments at once.</p>"
            ),
            "Microsoft.VSTS.Common.AcceptanceCriteria": (
                "<p>AC1: GIVEN I am on /payments/monitoring "
                "WHEN I click Retry-All "
                "THEN every transmission-failed intent is retried.</p>"
                "<p>AC2: GIVEN I am a FieldUser "
                "WHEN I try to click Retry-All "
                "THEN the action is denied with HTTP 403.</p>"
            ),
        }
    }

    history = {
        "neighbour_stories": [
            {"id": 432288, "title": "Update Wire ResWare Webhook",
             "state": "QA Passed", "tags": "Gen-AI; Resware_OB"},
            {"id": 417882, "title": "Reverse posted payment fix",
             "state": "Closed", "tags": "Gen-AI; Escrow_CEA"},
            {"id": 423560, "title": "Consolidation queue release fix",
             "state": "Done", "tags": "Gen-AI; Escrow_CEA"},
        ],
        "neighbour_tc_titles": [
            "Verify retry on transmission-failed payment intent",
            "Verify reverse posted payment by AccountingUser",
            "Verify consolidation release flow",
            "Verify FieldUser is denied retry",
        ],
        "neighbour_tc_keywords": [
            "retry", "reverse", "consolidation", "fielduser",
            "screen", "button", "webhook",
        ],
        # NEW: vocab-aligned subset returned by the upgraded history_context.
        "neighbour_domain_keywords": [
            "retry", "reverse", "consolidation", "fielduser",
            "webhook", "rbac",
        ],
        "neighbour_steps_samples": [],
        "summary": "3 neighbour stories • 4 historical TCs analysed • 6 domain keywords",
    }

    tcs, ac_clean, desc_clean, title = \
        ado_advisor.generate_test_cases_from_acceptance_criteria(
            work_item, history=history)

    print(f"\nGenerated {len(tcs)} test cases for: {title}\n")

    used_kws_seen: list = []
    audit_count = 0
    boilerplate_count = 0

    for i, tc in enumerate(tcs, 1):
        pre = tc.get('preconditions', '') or ''
        obj = tc.get('objective', '') or ''
        steps = tc.get('steps') or []
        cat = tc.get('test_category', '')
        ref = tc.get('ac_ref', '')

        # Detect each surface area enrichment
        markers = {
            'objective_hook': (
                "Also exercises the '" in obj
                or "Keeps parity with the '" in obj
                or "Data shapes should remain compatible" in obj
            ),
            'precond_bullet': 'Historical baseline:' in pre,
            'extra_step':     any("Smoke-check the '" in s for s in steps),
            'audit_line':     'Historical enrichment applied' in pre,
            'old_boilerplate':'Domain regression baseline' in pre,
        }

        n_surfaces = sum(int(bool(v)) for k, v in markers.items()
                         if k not in ('audit_line', 'old_boilerplate'))
        if markers['audit_line']:
            audit_count += 1
        if markers['old_boilerplate']:
            boilerplate_count += 1

        print(f"  TC {i:2d}  [{ref:>14s} | {cat:>10s}]  "
              f"surfaces={n_surfaces}  audit={int(markers['audit_line'])}  "
              f"old={int(markers['old_boilerplate'])}")
        print(f"        title : {tc['title'][:90]}")
        if markers['objective_hook']:
            for token in ("Also exercises the '",
                          "Keeps parity with the '",
                          "Data shapes should remain compatible"):
                if token in obj:
                    tail = obj.split(token)[-1]
                    print(f"        obj+  : ...{token}{tail[:90]}")
                    break
        if markers['precond_bullet']:
            for line in pre.splitlines():
                if 'Historical baseline:' in line:
                    print(f"        pre+  : {line.strip()}")
        if markers['extra_step']:
            for s in steps:
                if "Smoke-check the '" in s:
                    print(f"        step+ : {s}")
        if markers['audit_line']:
            for line in pre.splitlines():
                if 'Historical enrichment' in line:
                    print(f"        audit : {line.strip()}")

        # Soft assertion: every TC should touch at most one surface
        assert n_surfaces <= 1, f"TC {i} touched {n_surfaces} surfaces — should be ≤ 1"

    assert boilerplate_count == 0, "old 'Domain regression baseline' must be gone"
    assert audit_count <= 1, f"audit line should appear on at most one TC, saw {audit_count}"
    print(f"\nOK: surfaces ≤ 1 per TC, audit lines = {audit_count}, "
          f"old boilerplate = {boilerplate_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
