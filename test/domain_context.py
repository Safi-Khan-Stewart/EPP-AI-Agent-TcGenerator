"""
EPP Portal Domain Context
=========================

Loads `EPP_Portal_Business_Documentation.md` and exposes a structured
"domain context" for a given User Story (title + description + AC). The
context is consumed by `ado_advisor.py` to enrich generated test cases
with portal-specific roles, routes, workflows, and API references — so
the output reflects the real Enterprise Payment Platform, not generic
boilerplate.

Public API
----------
    ctx = build_domain_context(title, description, acceptance_criteria)

Returns a dict shaped like::

    {
        "portal":   "Escrow Dashboard" | "AP Admin Portal" | "EPP",
        "feature":  "Payment Monitoring",          # short label for titles
        "route":    "/payments/monitoring",         # canonical route, if any
        "roles":    ["AccountingUser", "Support"],  # allowed roles for the screen
        "primary_role": "AccountingUser",           # best actor to use in steps
        "negative_role": "FieldUser",               # a role that should be denied
        "workflow_steps": ["...", "..."],           # canonical user-journey hints
        "api_hints":  ["POST /api/Escrow/Payments/Intents/{key}/Retry → 202"],
        "preconditions": ["User has the AccountingUser role",
                          "User is on /payments/monitoring"],
        "matched_screen": "Payment Monitoring",
        "confidence": 0.82,
    }

If nothing matches well, the dict still has all keys (with empty lists /
None values) so the caller can use it safely without `.get()` guards.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

DOC_FILENAME = "EPP_Portal_Business_Documentation.md"


# ────────────────────────────────────────────────────────────────────────
#  Static knowledge derived from the business documentation.
#  Keeping this as a Python catalogue (instead of re-parsing the .md every
#  call) gives us deterministic, fast, well-typed lookups. If the .md is
#  updated, refresh the entries below.
# ────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Screen:
    name: str                              # short, human-friendly feature label
    portal: str                            # "Escrow Dashboard" | "AP Admin Portal"
    route: Optional[str]                   # canonical route (None if N/A)
    roles: Tuple[str, ...]                 # roles that can access this screen
    keywords: Tuple[str, ...]              # words that signal this screen
    workflow_steps: Tuple[str, ...] = ()   # canonical user-journey hints
    api_hints: Tuple[str, ...] = ()        # API references for expected results


# ── Catalogue of screens / features (derived from EPP_Portal_Business_Documentation.md) ──
_SCREENS: Tuple[Screen, ...] = (
    # ── Escrow Dashboard ────────────────────────────────────────────────
    Screen(
        name="Payment History",
        portal="Escrow Dashboard",
        route="/payments",
        roles=("FieldUser", "AccountingUser", "Support", "CEAFraudInvestigator"),
        keywords=("payment history", "payment list", "payments list",
                  "payment table", "payments page", "faceted search",
                  "payment search", "search payments"),
        workflow_steps=(
            "Navigate to the Payment History screen at /payments",
            "Use the search bar (minimum 2 characters) to find a payment",
            "Apply filters from the side drawer",
        ),
        api_hints=("Azure AI Search OData query is sent",
                   "EscrowPaymentIndexModel rows are returned"),
    ),
    Screen(
        name="Payment Monitoring",
        portal="Escrow Dashboard",
        route="/payments/monitoring",
        roles=("Support", "CEAFraudInvestigator", "AccountVerificationAdministrator",
               "Administrator", "AccountingUser"),
        keywords=("payment monitoring", "monitor payment", "monitoring tab",
                  "transmission failed", "stuck payment", "consolidation queue",
                  "overnight queue", "pending payments", "monitoring summary",
                  "get transaction status"),
        workflow_steps=(
            "Navigate to /payments/monitoring",
            "Open the appropriate status tab (Pending / Transmission Failed / Consolidation Queue)",
            "Locate the target payment and open its action menu",
        ),
        api_hints=(
            "POST /api/Escrow/Payments/Intents/{key}/Retry  → 202 Accepted",
            "POST /api/Escrow/Payments/Intents/{key}/Sync   → 202 Accepted",
            "POST /api/Escrow/Payments/Intents/{key}/MarkAsPosted → 202 Accepted",
            "POST /api/Escrow/Payments/{key}/ResolveManually  → 202 Accepted",
            "POST /api/Escrow/Payments/{key}/Reverse → 202 Accepted",
            "POST /api/Escrow/Payments/Intents/{key}/Reject → 202 Accepted",
        ),
    ),
    Screen(
        name="Payment Request Creation",
        portal="Escrow Dashboard",
        route="/payments/request",
        roles=("FieldUser", "AccountingUser"),
        keywords=("create payment", "new payment", "payment request",
                  "payment creation", "send funds", "payment invitation",
                  "initiate payment"),
        workflow_steps=(
            "Navigate to /payments/request",
            "Select transaction direction (Inbound / Outbound)",
            "Fill in amount, internal bank account, payment use case, escrow file number",
            "Fill in counterparty and escrow officer details",
            "Submit the form",
        ),
        api_hints=(
            "POST /api/Escrow/PaymentRequest → 201 Created (invitation)",
            "POST /api/Escrow/Payments → 201 Created (direct payment)",
        ),
    ),
    Screen(
        name="My Payments",
        portal="Escrow Dashboard",
        route="/payments/my",
        roles=("FieldUser",),
        keywords=("my payments", "self-service payments", "user's own payments"),
        workflow_steps=("Navigate to /payments/my as a FieldUser",),
    ),
    Screen(
        name="Consolidated Payments",
        portal="Escrow Dashboard",
        route="/payments/monitoring",
        roles=("AccountingUser",),
        keywords=("consolidated payment", "payment aggregate", "release aggregate",
                  "consolidation"),
        workflow_steps=(
            "Open /payments/monitoring → Consolidation Queue tab",
            "Select an aggregate and release or reject it",
        ),
        api_hints=(
            "POST /api/Escrow/Payments/Aggregate/{key}/Release → 202 Accepted",
            "POST /api/Escrow/Payments/Aggregate/{key}/Requests/{reqKey}/Reject → 202 Accepted",
        ),
    ),
    Screen(
        name="Banks",
        portal="Escrow Dashboard",
        route="/accounts/banks",
        roles=("Administrator", "Support", "CEAFraudInvestigator"),
        keywords=("banks list", "manage bank", "add bank", "edit bank",
                  "bank details", "bank management", "add bank to"),
        workflow_steps=(
            "Navigate to /accounts/banks as an Administrator",
            "Add or edit a bank record",
        ),
    ),
    Screen(
        name="Internal Bank Accounts",
        portal="Escrow Dashboard",
        route="/accounts/bank-accounts",
        roles=("Administrator", "Support", "CEAFraudInvestigator"),
        keywords=("internal bank account", "iba", "bank-accounts",
                  "reveal account number", "payment rails"),
        workflow_steps=(
            "Navigate to /accounts/bank-accounts",
            "Search for and open an internal bank account",
        ),
        api_hints=(
            "POST /api/InternalBankAccounts/Search → 200 OK",
            "GET  /api/InternalBankAccounts/{key}/Reveal  → 200 OK [CEAFraudInvestigator]",
            "PATCH /api/InternalBankAccounts/{key}/PaymentRails → 204 [Administrator]",
        ),
    ),
    Screen(
        name="Counterparties",
        portal="Escrow Dashboard",
        route="/counterparties",
        roles=("FieldUser", "AccountingUser", "AccountVerificationAdministrator",
               "Support", "CEAFraudInvestigator"),
        keywords=("counterpart", "counterparties", "party list", "party details",
                  "onboard counterparty", "ews rejection", "pnc rejection"),
        workflow_steps=(
            "Navigate to /counterparties",
            "Search for the counterparty and open the details dialog",
        ),
    ),
    Screen(
        name="Counterparty Onboarding",
        portal="Escrow Dashboard",
        route="/counterparties/onboard",
        roles=("AccountVerificationAdministrator",),
        keywords=("onboard counterparty", "counterparty onboarding",
                  "re-onboard", "bypass verification", "account verification"),
        workflow_steps=(
            "Navigate to /counterparties/onboard as an AccountVerificationAdministrator",
        ),
    ),
    Screen(
        name="Payment Monitoring Rule Settings",
        portal="Escrow Dashboard",
        route="/settings/monitoring",
        roles=("Administrator", "AccountingUser"),
        keywords=("monitoring rule", "monitoring settings", "threshold",
                  "rail rule", "ach rule", "wire rule", "rtp rule",
                  "payment rail"),
        workflow_steps=(
            "Navigate to /settings/monitoring",
            "Select a bank (or DEFAULT)",
            "Configure thresholds per rail (ACH / Wire / SameDayACH / RTP)",
            "Save changes — preferences are persisted via Preferences API",
        ),
        api_hints=(
            "POST /api/preferences  → 201 Created",
            "PUT  /api/preferences/{key} → 204 (uses ETag for concurrency)",
        ),
    ),
    Screen(
        name="Tasks",
        portal="Escrow Dashboard",
        route="/tasks",
        roles=("FieldUser", "AccountingUser", "Support", "Administrator"),
        keywords=("task list", "user task", "task details", "shared services task"),
    ),
    Screen(
        name="EWIS Payment Integrations",
        portal="Escrow Dashboard",
        route="/ewis",
        roles=("FieldUser", "AccountingUser", "Support", "Administrator"),
        keywords=("ewis", "wire integration", "resware webhook", "wire resware",
                  "external wire", "transactee", "payment integration"),
        workflow_steps=(
            "Navigate to /ewis",
            "Search for a wire integration record",
            "Open its details dialog",
        ),
        api_hints=("GET /api/ewis/transactee/{id} → 200 OK",),
    ),

    # ── AP Admin Portal ─────────────────────────────────────────────────
    Screen(
        name="AP Admin Dashboard",
        portal="AP Admin Portal",
        route="/home",
        roles=("User.Basic", "User.Admin"),
        keywords=("ap admin dashboard", "payout period summary",
                  "dashboard metric", "payment metric", "channel breakdown"),
    ),
    Screen(
        name="Accounts",
        portal="AP Admin Portal",
        route="/accounts",
        roles=("User.Basic", "User.Admin"),
        keywords=("accounts list", "account search", "party account",
                  "stripe account", "payouts enabled"),
    ),
    Screen(
        name="Account Actions",
        portal="AP Admin Portal",
        route="/accounts/{partyKey}/actions",
        roles=("User.Admin",),
        keywords=("sync stripe", "delete party", "retry disbursement",
                  "set party administrator", "party preferences",
                  "account action"),
        api_hints=(
            "POST   /api/Accounts/Stripe/Actions/Sync → 202 [User.Admin]",
            "DELETE /api/Parties/{key} → 204 [User.Admin]",
            "POST   /api/FundsDisbursements/{key}/Retry → 202 [User.Admin]",
        ),
    ),
    Screen(
        name="Business Units",
        portal="AP Admin Portal",
        route="/business-units",
        roles=("User.Basic", "User.Admin"),
        keywords=("business unit", "business-units", "connected system",
                  "business unit user", "associated user"),
        api_hints=(
            "GET    /api/v2/Operations/BusinessUnits/Mine → 200 OK",
            "POST   /api/v2/Operations/BusinessUnits/{key}/AssociatedUsers [User.Admin]",
            "DELETE /api/v2/Operations/BusinessUnits/{key}/AssociatedUsers [User.Admin]",
        ),
    ),
    Screen(
        name="Bulk Payment Import",
        portal="AP Admin Portal",
        route="/bulk-payments/import",
        roles=("Bulk.AP.Payment.Requester",),
        keywords=("bulk payment import", "csv import", "import bulk",
                  "import payment file", "bulk import"),
        workflow_steps=(
            "Navigate to /bulk-payments/import as a Bulk AP Payment Requester",
            "Select a Business Unit and Connected System",
            "Enter the Batch Total Amount",
            "Drop or browse for a CSV file",
            "Submit the import",
        ),
        api_hints=(
            "POST /api/Payments/Bulk/Import → 200 OK (returns success / file errors / line errors)",
            "GET  /api/Payments/Bulk/Import/CsvTemplate → 200 OK [AllowAnonymous]",
        ),
    ),
    Screen(
        name="Pending Approvals",
        portal="AP Admin Portal",
        route="/bulk-payments/pending-approvals",
        roles=("Bulk.AP.Payment.Approver",),
        keywords=("pending approval", "approve payment", "reject payment",
                  "approval queue", "bulk approve", "bulk reject"),
        workflow_steps=(
            "Navigate to /bulk-payments/pending-approvals as a Bulk AP Payment Approver",
            "Select individual or use Select-All / Select-Page mode",
            "Approve or Reject (with reason) the chosen records",
        ),
        api_hints=(
            "POST /api/Payments/Bulk/Import/Record/{key}/Approve [Approver]",
            "POST /api/Payments/Bulk/Import/Record/{key}/Reject  [Approver]",
            "POST /api/Payments/Bulk/Import/Record/ApproveMultiple [Approver]",
            "POST /api/Payments/Bulk/Import/Record/RejectMultiple  [Approver]",
        ),
    ),
    Screen(
        name="Approved Payments",
        portal="AP Admin Portal",
        route="/bulk-payments/approved",
        roles=("Bulk.AP.Payment.Requester", "Bulk.AP.Payment.Approver",
               "User.Admin", "User.Basic"),
        keywords=("approved payment", "approved bulk", "export approved csv"),
    ),
    Screen(
        name="Rejected Payments",
        portal="AP Admin Portal",
        route="/bulk-payments/rejected",
        roles=("Bulk.AP.Payment.Requester", "Bulk.AP.Payment.Approver",
               "User.Admin", "User.Basic"),
        keywords=("rejected payment", "rejection reason"),
    ),
    Screen(
        name="Approval History",
        portal="AP Admin Portal",
        route="/bulk-payments/approval-history",
        roles=("Bulk.AP.Payment.Requester", "Bulk.AP.Payment.Approver",
               "User.Admin", "User.Basic"),
        keywords=("approval history", "audit trail", "approval audit"),
    ),
    Screen(
        name="ELIS Service Maps",
        portal="AP Admin Portal",
        route="/integration/elis/service-maps",
        roles=("User.Admin",),
        keywords=("elis", "service map", "ledger integration",
                  "accounting integration"),
    ),
    Screen(
        name="Payout Period",
        portal="AP Admin Portal",
        route="/payment-flow/payout-period",
        roles=("User.Basic", "User.Admin"),
        keywords=("payout period", "payment flow", "payout window"),
        api_hints=("GET /api/PaymentFlows/PayoutPeriod → 200 OK",),
    ),
)


# Role → a "negative actor" that should be rejected for that role's screen
# Used to pick realistic unauthorized-access test scenarios.
_NEGATIVE_ROLE_FOR: Dict[str, str] = {
    "FieldUser":                          "Administrator",
    "AccountingUser":                     "FieldUser",
    "Administrator":                      "FieldUser",
    "Support":                            "FieldUser",
    "CEAFraudInvestigator":               "FieldUser",
    "AccountVerificationAdministrator":   "FieldUser",
    "User.Admin":                         "User.Basic",
    "User.Basic":                         "User.Admin",
    "Bulk.AP.Payment.Requester":          "Bulk.AP.Payment.Approver",
    "Bulk.AP.Payment.Approver":           "Bulk.AP.Payment.Requester",
}


# Preference order for picking the "primary actor" of a test case when a
# screen allows multiple roles. Higher priority roles are picked first
# because they are the ones who actually drive the workflows on that
# screen (e.g., AccountingUser drives monitoring actions; Administrator
# manages bank setup; Requester imports bulk payments).
_ROLE_PRIORITY: Tuple[str, ...] = (
    # Escrow Dashboard — action-driving roles first
    "AccountingUser",
    "Administrator",
    "AccountVerificationAdministrator",
    "FieldUser",
    "FieldApprover",
    "CEAFraudInvestigator",
    "Support",
    # AP Admin Portal
    "Bulk.AP.Payment.Requester",
    "Bulk.AP.Payment.Approver",
    "User.Admin",
    "User.Basic",
)


def _pick_primary_role(roles: List[str]) -> Optional[str]:
    """From an allowed-roles list, pick the one most likely to perform
    the action on that screen (so test steps read naturally)."""
    if not roles:
        return None
    for r in _ROLE_PRIORITY:
        if r in roles:
            return r
    return roles[0]


# ────────────────────────────────────────────────────────────────────────
#  EPP Area Tag classifier
#  ----------------------
#  Each story is classified into ONE area-tag used in ADO. The rules
#  below come from QA leadership (project tagging convention):
#
#    AP_Bulk      — Admin portal Bulk Payments
#    Resware_OB   — Escrow + Outbound payments (ACH OB / Legacy TPS Wire /
#                   Legacy TPS Intercompany / Consolidated / Overnight)
#    Escrow_CEA   — Escrow Dashboard main-screen enhancements
#                   (Banks, Bank Accounts, Counterparty, Monitoring,
#                    History, My Payments, Profile)
#    Escrow_IB    — Escrow Inbound payments
#                   (EMD via "New Payment Request" or public EMD form)
#    STEPS_OB     — STEPS integration + Outbound payments
#    AP_WD        — Admin portal + Workday integration / Vendor onboarding /
#                   Vendor payments
#    AP_Portal    — Admin portal UI changes (vendor profile / party user /
#                   party info display)
#    Escrow_OB    — Escrow Outbound payments UI changes
#
#  The classifier returns one tag string (or None when the story doesn't
#  match any area). Rules are evaluated in priority order — the FIRST
#  match wins, so the most specific rules are checked first.
# ────────────────────────────────────────────────────────────────────────

_OUTBOUND_KWS = (
    "outbound", "ach outbound", "ach ob",
    "legacy tps wire", "tps wire", "legacy tps", "legacy-tps",
    "legacy tps intercompany", "intercompany",
    "consolidated payment", "consolidation queue",
    "overnight queue", "overnight payment",
    "disbursement", "disburse",
    "send funds", "wire transfer", "wire payment",
)

_INBOUND_KWS = (
    "inbound", "emd payment", "earnest money", "earnest-money",
    "public emd", "emd form",
    "new payment request button", "payment request button",
    "incoming payment",
)

_BULK_KWS = (
    "bulk payment", "bulk-payment", "bulkpayment",
    "bulk import", "bulk approval", "bulk approver",
    "ap.payment.requester", "ap.payment.approver",
)

_STEPS_KWS = (
    "steps integration", "steps:", "step integration",
    "steps payment", "steps disbursement",
    "steps api", "steps service",
)

_WORKDAY_KWS = (
    "workday", "vendor onboarding", "vendor onboard",
    "vendor payment", "vendor profile creation",
    "vendor master", "vendor record",
)

_AP_PORTAL_UI_KWS = (
    "ap admin ui", "admin portal ui", "admin ui",
    "vendor profile", "party user", "party info",
    "party display", "party screen",
    "edit vendor", "vendor display",
)

_ESCROW_CEA_KWS = (
    "banks list", "bank accounts", "bank-accounts",
    "internal bank account", "counterpart",
    "payment monitoring", "monitoring screen",
    "payment history", "payments history",
    "my payments", "profile screen", "user profile",
    "faceted search",
)


def _has_any(text: str, words: Tuple[str, ...]) -> bool:
    return any(w in text for w in words)


def classify_epp_area(text: str, portal: str) -> Optional[str]:
    """Pick the single EPP area-tag for an ADO test case based on the
    lowercased combined text of (title + description + AC) and the
    already-detected portal name.

    Returns one of:
      'AP_Bulk', 'AP_WD', 'AP_Portal',
      'STEPS_OB',
      'Resware_OB', 'Escrow_OB', 'Escrow_IB', 'Escrow_CEA'
    or None when the story doesn't fit any defined area.
    """
    is_ap = portal == "AP Admin Portal"
    is_escrow = portal == "Escrow Dashboard"
    has_outbound = _has_any(text, _OUTBOUND_KWS)
    has_inbound = _has_any(text, _INBOUND_KWS)
    has_ui = any(k in text for k in (
        " ui ", "ui change", "ui changes", "screen change",
        "screen update", "ui update", "front-end", "frontend",
        "redesign", "layout", "form change",
    ))

    # ── 1. STEPS integration + outbound (most specific — check FIRST) ──
    if _has_any(text, _STEPS_KWS) and has_outbound:
        return "STEPS_OB"

    # ── 2. AP Admin → Workday / Vendor flows ───────────────────────────
    if _has_any(text, _WORKDAY_KWS):
        return "AP_WD"

    # ── 3. AP Admin → Bulk Payments ────────────────────────────────────
    if _has_any(text, _BULK_KWS) or (is_ap and "bulk" in text):
        return "AP_Bulk"

    # ── 4. AP Admin → UI / vendor-profile / party-info changes ─────────
    if is_ap and (_has_any(text, _AP_PORTAL_UI_KWS) or has_ui):
        return "AP_Portal"

    # ── 5. Escrow Inbound (EMD / public form / new payment request) ────
    if is_escrow and has_inbound:
        return "Escrow_IB"

    # ── 6. Escrow Outbound — UI change variant takes precedence ────────
    if is_escrow and has_outbound and has_ui:
        return "Escrow_OB"

    # ── 7. Escrow + Outbound (Resware/legacy-TPS/consolidated/overnight)
    if is_escrow and has_outbound:
        return "Resware_OB"

    # ── 8. Escrow main-screen enhancement (Banks, Counterparty, etc.) ──
    if is_escrow and _has_any(text, _ESCROW_CEA_KWS):
        return "Escrow_CEA"

    # ── 9. Generic AP Admin fallback when portal matched ───────────────
    if is_ap:
        return "AP_Portal"

    # ── 10. Generic Escrow fallback when portal matched ────────────────
    if is_escrow:
        return "Escrow_CEA"

    return None


# ────────────────────────────────────────────────────────────────────────
#  Scoring & match logic
# ────────────────────────────────────────────────────────────────────────

def _score_screen(screen: Screen, text: str) -> int:
    """Return a relevance score for a screen against the lowercased combined
    text of (title + description + AC). Longer keyword matches score more.
    """
    score = 0
    for kw in screen.keywords:
        if kw in text:
            # Reward longer/more specific keywords more strongly
            score += 2 + len(kw.split())
    # Light boost when the route appears verbatim (rare but very high-signal)
    if screen.route and screen.route in text:
        score += 5
    # Boost when an explicit portal name appears
    if screen.portal.lower() in text:
        score += 1
    return score


def _detect_portal(text: str) -> str:
    """Best-effort portal detection independent of screen match."""
    escrow_kws = (
        "escrow", "cea dashboard", "fieldapprover", "field approver",
        "fielduser", "field user", "accountinguser", "accounting user",
        "ceafraudinvestigator", "fraud investigator",
        "internal bank account", "counterpart", "ewis", "wire resware",
        # Escrow-specific business terms
        "tps wire", "legacy tps", "consolidation queue",
        "overnight queue", "ach outbound", "ach ob",
        "emd payment", "earnest money", "earnest-money",
        "public emd", "emd form",
        "payment monitoring", "payment history", "monitoring screen",
        "my payments",
    )
    ap_kws = (
        "ap admin", "admin portal", "bulk payment", "bulkpayment",
        "bulk ap payment", "bulk-payment",
        "payout period", "stripe", "business unit", "elis",
        "user.admin", "user.basic", "payment flow",
        # AP-specific business terms
        "workday", "vendor onboarding", "vendor onboard",
        "vendor payment", "vendor profile", "vendor master",
        "party user", "party info",
    )
    e = sum(1 for k in escrow_kws if k in text)
    a = sum(1 for k in ap_kws if k in text)
    if e == 0 and a == 0:
        return "EPP"
    return "Escrow Dashboard" if e >= a else "AP Admin Portal"


def _short_label(title: str) -> str:
    """Fall-back feature label used when no screen matches well."""
    t = re.sub(r'^(EPP[:\-]\s*)', '', (title or '').strip(),
               flags=re.IGNORECASE)
    # Strip noisy prefixes like "STEPS:", "EXTERNAL:", "(API)"
    t = re.sub(r'\b(STEPS|EXTERNAL|INTERNAL|API)\s*[:\-]\s*', '', t,
               flags=re.IGNORECASE)
    t = re.sub(r'\s*\(API\)\s*$', '', t, flags=re.IGNORECASE)
    t = t.rstrip(' .:;-–—')
    return t[:60]


def build_domain_context(title: str,
                         description: str = '',
                         acceptance_criteria: str = '') -> Dict:
    """Main entry point — see module docstring for the returned shape."""
    combined = ' '.join(filter(None, [title, description, acceptance_criteria])).lower()

    # Score every screen and pick the best one
    scored = sorted(
        ((_score_screen(s, combined), s) for s in _SCREENS),
        key=lambda x: x[0],
        reverse=True,
    )
    top_score, top_screen = scored[0] if scored else (0, None)

    # Confidence: top score normalised to a 0–1 range (cap at 12 for sanity)
    confidence = min(top_score / 12.0, 1.0) if top_score else 0.0

    portal = _detect_portal(combined) if (not top_screen or top_score < 3) \
             else top_screen.portal

    if top_screen and top_score >= 3:
        feature = top_screen.name
        route = top_screen.route
        roles = list(top_screen.roles)
        workflow_steps = list(top_screen.workflow_steps)
        api_hints = list(top_screen.api_hints)
        matched = top_screen.name
    else:
        feature = _short_label(title)
        route = None
        # If we can at least detect the portal, suggest sensible default roles
        if portal == "Escrow Dashboard":
            roles = ["AccountingUser"]
        elif portal == "AP Admin Portal":
            roles = ["User.Admin"]
        else:
            roles = []
        workflow_steps = []
        api_hints = []
        matched = None

    primary_role = _pick_primary_role(roles)
    negative_role = (_NEGATIVE_ROLE_FOR.get(primary_role)
                     if primary_role else None)

    # Build domain-aware preconditions
    preconditions: List[str] = []
    if primary_role:
        preconditions.append(
            f"User is signed in to the {portal} with the '{primary_role}' role"
        )
    if route:
        preconditions.append(f"User can reach the route {route}")

    # EPP area-tag classification (drives the ADO tag on the test case)
    epp_area = classify_epp_area(combined, portal)

    return {
        "portal": portal,
        "feature": feature,
        "route": route,
        "roles": roles,
        "primary_role": primary_role,
        "negative_role": negative_role,
        "workflow_steps": workflow_steps,
        "api_hints": api_hints,
        "preconditions": preconditions,
        "matched_screen": matched,
        "confidence": round(confidence, 2),
        "epp_area": epp_area,
    }


# ────────────────────────────────────────────────────────────────────────
#  Optional: lightweight sanity check when run directly
# ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    samples = [
        ("EPP: Add Bank to faceted search", "", ""),
        ("EPP: STEPS: Payment Disbursement: EXTERNAL: Get Transaction Status (API)", "", ""),
        ("EPP: Update Wire ResWare Webhook", "", ""),
        ("EPP: Bulk Payment Import improvements", "", ""),
        ("EPP: Onboard counterparty after EWS rejection", "", ""),
        ("EPP: ACH Outbound payment retry from Consolidation Queue", "", ""),
        ("EPP: Legacy TPS Wire reversal on monitoring screen", "", ""),
        ("EPP: Overnight Queue UI changes for outbound payments", "", ""),
        ("EPP: EMD payment via public form", "", ""),
        ("EPP: New Payment Request button for inbound EMD", "", ""),
        ("EPP: Workday vendor onboarding integration", "", ""),
        ("EPP: Admin Portal vendor profile UI redesign", "", ""),
    ]
    for t, d, a in samples:
        ctx = build_domain_context(t, d, a)
        print(f"\n{t!r}")
        print(f"  portal     : {ctx['portal']}")
        print(f"  feature    : {ctx['feature']}")
        print(f"  epp_area   : {ctx['epp_area']}")
        print(f"  confidence : {ctx['confidence']}")
