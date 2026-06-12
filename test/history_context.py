"""
EPP Historical Context
======================

Given a current User Story, this module finds **similar / neighbouring**
User Stories in the same Azure DevOps Area Path (and ideally with the
same EPP area-tag), pulls their linked Test Cases, and extracts a small
"prior art" summary that the test case generator can use to:

  • adopt the same naming style for new test cases,
  • avoid duplicating coverage that already exists,
  • surface domain-specific edge cases the team has tested before.

Public API
----------
    ctx = build_history_context(
        current_story_id      = 443590,
        current_area_path     = "Enterprise Payments\\\\Escrow",
        current_iteration     = "...",                # optional, used for recency
        epp_area              = "STEPS_OB",           # optional, narrows the search
        ado_org               = ADO_ORG,
        ado_project           = ADO_PROJECT,
        headers               = headers,              # the global auth headers
        max_stories           = 8,
        max_tcs_per_story     = 5,
    )

Returns a dict shaped like::

    {
        "neighbour_stories": [
            {"id": 432288, "title": "EPP: Update Wire ResWare Webhook", "state": "QA Passed"},
            ...
        ],
        "neighbour_tc_titles": [
            "Verify retry on transmission-failed payment intent...",
            ...
        ],
        "neighbour_tc_keywords": ["retry", "reverse", "consolidation", ...],
        "neighbour_domain_keywords": ["retry", "reverse", "consolidation"],
        "neighbour_steps_samples": ["Log in to Escrow Dashboard as AccountingUser", ...],
        "summary": "8 neighbour stories • 27 historical TCs analysed • 9 domain keywords",
    }

``neighbour_domain_keywords`` is a curated subset restricted to the
EPP business vocabulary (see ``_DOMAIN_VOCAB``) — prefer it over
``neighbour_tc_keywords`` when enriching generated test cases.

If the lookup fails or no neighbours are found, the dict still has all
keys with empty values so the caller can use it safely.
"""

from __future__ import annotations

import re
import urllib.parse
from collections import Counter
from typing import Dict, List, Optional

import requests


# Words that carry NO domain signal — excluded from the keyword pool so
# we don't suggest generic words like "verify", "user", "the".
_STOPWORDS = frozenset({
    "verify", "validate", "ensure", "check", "confirm", "test", "tests",
    "the", "and", "a", "an", "to", "of", "in", "on", "for", "with",
    "from", "by", "is", "are", "be", "as", "it", "this", "that", "then",
    "when", "user", "users", "users\u2019", "page", "screen", "system",
    "should", "shall", "will", "can", "must", "able",
    "epp", "azure", "ado",
})


# Curated EPP business vocabulary — words that, when present in prior test
# case titles / steps, are HIGH-SIGNAL domain terms for the Enterprise
# Payment Platform. The generator boosts these when picking enrichment
# keywords (vs. generic words like "screen" or "click").
#
# Keep this list aligned with the screens / workflows / API hints in
# ``EPP_Portal_Business_Documentation.md`` and ``domain_context.py``.
_DOMAIN_VOCAB = frozenset({
    # Payment lifecycle
    "retry", "reverse", "resolve", "reject", "release", "sync", "post",
    "consolidate", "consolidation", "aggregate", "transmission",
    "transmit", "intent", "intents", "monitoring", "monitor",
    "overnight", "pending", "failed", "stuck",
    # Banks / accounts
    "bank", "banks", "iba", "rails", "ach", "wire", "rtp",
    "sameday", "samedayach", "account", "accounts", "reveal",
    # Counterparties / onboarding
    "counterparty", "counterparties", "onboard", "onboarding",
    "verification", "ews", "pnc",
    # Settings / preferences
    "threshold", "thresholds", "preference", "preferences", "rule",
    "rules", "etag",
    # Integrations
    "webhook", "resware", "ewis", "integration", "integrations",
    "transactee", "callback",
    # Bulk / approvals
    "bulk", "import", "approve", "approved", "approval", "rejected",
    "history", "csv", "fis", "ami",
    # Identity / RBAC
    "fielduser", "accountinguser", "support", "administrator",
    "ceafraudinvestigator", "accountverificationadministrator",
    "role", "roles", "permission", "permissions", "rbac",
    "unauthorized", "forbidden", "denied",
    # Generic financial / data
    "payment", "payments", "invoice", "amount", "currency",
    "audit", "log", "event", "events",
})


def _is_domain_keyword(word: str) -> bool:
    """True if a keyword is part of the curated EPP business vocabulary."""
    return word.lower() in _DOMAIN_VOCAB


def _wiql(query: str, ado_org: str, ado_project: str, headers: dict,
          timeout: int = 20) -> List[int]:
    """Run a WIQL query and return the list of returned work item IDs."""
    org = urllib.parse.quote(ado_org)
    project = urllib.parse.quote(ado_project)
    url = (f"https://dev.azure.com/{org}/{project}/_apis/wit/wiql"
           f"?api-version=7.1")
    try:
        resp = requests.post(url, headers=headers, json={"query": query},
                             verify=False, timeout=timeout)
        resp.raise_for_status()
        items = resp.json().get('workItems', []) or []
        return [int(it['id']) for it in items]
    except Exception as e:
        print(f"  [history] WIQL error: {e}")
        return []


def _batch_get(ids: List[int], fields: List[str], ado_org: str,
               headers: dict, timeout: int = 30) -> List[dict]:
    """Batch-fetch a list of work items, returning their .json() payloads."""
    if not ids:
        return []
    out: List[dict] = []
    org = urllib.parse.quote(ado_org)
    url = (f"https://dev.azure.com/{org}/_apis/wit/workitemsbatch"
           f"?api-version=7.1")
    # ADO batch endpoint caps at 200; chunk just to be safe.
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        try:
            resp = requests.post(url, headers=headers,
                                 json={"ids": chunk, "fields": fields},
                                 verify=False, timeout=timeout)
            resp.raise_for_status()
            out.extend(resp.json().get('value', []) or [])
        except Exception as e:
            print(f"  [history] batch fetch error: {e}")
    return out


def _get_relations(wi_id: int, ado_org: str, headers: dict,
                   timeout: int = 15) -> List[dict]:
    org = urllib.parse.quote(ado_org)
    url = (f"https://dev.azure.com/{org}/_apis/wit/workitems/{wi_id}"
           f"?$expand=relations&api-version=7.1")
    try:
        resp = requests.get(url, headers=headers, verify=False, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get('relations', []) or []
    except Exception:
        return []


def _strip_html(s: str) -> str:
    if not s:
        return ''
    s = re.sub(r'<[^>]+>', ' ', s)
    s = re.sub(r'&nbsp;', ' ', s, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', s).strip()


def _extract_keywords(texts: List[str], top_n: int = 20) -> List[str]:
    """Pick the most distinctive single-word keywords from a list of
    test case titles / steps. Filters generic verbs and stopwords."""
    counter: Counter = Counter()
    for t in texts:
        if not t:
            continue
        for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", t.lower()):
            if w in _STOPWORDS:
                continue
            counter[w] += 1
    return [w for w, _ in counter.most_common(top_n)]


def _extract_domain_keywords(texts: List[str], top_n: int = 12) -> List[str]:
    """Same as ``_extract_keywords`` but restricted to the curated EPP
    business vocabulary — the words most likely to add real domain
    colour to a generated test case.

    Returns up to ``top_n`` keywords ordered by frequency.
    """
    counter: Counter = Counter()
    for t in texts:
        if not t:
            continue
        for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", t.lower()):
            if _is_domain_keyword(w):
                counter[w] += 1
    return [w for w, _ in counter.most_common(top_n)]


def build_history_context(current_story_id: int,
                          current_area_path: str,
                          ado_org: str,
                          ado_project: str,
                          headers: dict,
                          *,
                          epp_area: Optional[str] = None,
                          max_stories: int = 8,
                          max_tcs_per_story: int = 5) -> Dict:
    """Main entry point — see module docstring for shape."""
    empty_ctx = {
        "neighbour_stories": [],
        "neighbour_tc_titles": [],
        "neighbour_tc_keywords": [],
        "neighbour_domain_keywords": [],
        "neighbour_steps_samples": [],
        "summary": "0 neighbour stories",
    }

    if not current_area_path:
        return empty_ctx

    # ── 1. WIQL: find recent User Stories in the same Area Path ────────
    area_path_escaped = current_area_path.replace("'", "''")
    wiql_query = (
        "Select [System.Id], [System.Title], [System.State], [System.Tags] "
        "From WorkItems "
        "Where [System.WorkItemType] = 'User Story' "
        f"  And [System.AreaPath] Under '{area_path_escaped}' "
        f"  And [System.Id] <> {current_story_id} "
        "  And [System.State] In ('QA Passed', 'Closed', 'Done', "
        "                          'QA In Progress', 'Dev Complete', 'Resolved') "
        "Order By [System.ChangedDate] Desc"
    )
    story_ids = _wiql(wiql_query, ado_org, ado_project, headers)
    if not story_ids:
        return empty_ctx

    # ── 2. Fetch tags/title for the top N candidates and rank them ─────
    candidates = _batch_get(
        story_ids[: max_stories * 4],   # over-fetch so we can rank/filter
        ["System.Id", "System.Title", "System.State", "System.Tags"],
        ado_org, headers,
    )

    def _has_area_tag(wi: dict) -> bool:
        tags = (wi.get('fields', {}).get('System.Tags') or '').lower()
        return bool(epp_area) and (epp_area.lower() in tags)

    # Prefer stories sharing the EPP area-tag; keep order otherwise.
    ranked = sorted(candidates, key=lambda wi: (0 if _has_area_tag(wi) else 1))
    neighbours = ranked[:max_stories]

    neighbour_stories = [
        {
            "id": wi.get('id'),
            "title": wi.get('fields', {}).get('System.Title', ''),
            "state": wi.get('fields', {}).get('System.State', ''),
            "tags":  wi.get('fields', {}).get('System.Tags', ''),
        }
        for wi in neighbours if wi.get('id')
    ]

    # ── 3. For each neighbour, pull its "Tested By" test cases ─────────
    tc_ids: List[int] = []
    for wi in neighbours:
        wi_id = wi.get('id')
        if not wi_id:
            continue
        relations = _get_relations(wi_id, ado_org, headers)
        linked = [
            int(r['url'].split('/')[-1])
            for r in relations
            if r.get('attributes', {}).get('name') in ('Tested By', 'Tests')
        ]
        tc_ids.extend(linked[: max_tcs_per_story])

    # De-duplicate while preserving order, then cap
    seen, dedup = set(), []
    for i in tc_ids:
        if i not in seen:
            seen.add(i)
            dedup.append(i)
    tc_ids = dedup[: max_stories * max_tcs_per_story]

    # ── 4. Fetch TC titles + steps ─────────────────────────────────────
    tcs = _batch_get(
        tc_ids,
        ["System.Id", "System.Title", "Microsoft.VSTS.TCM.Steps"],
        ado_org, headers,
    )

    tc_titles: List[str] = []
    steps_samples: List[str] = []
    for tc in tcs:
        f = tc.get('fields', {})
        title = f.get('System.Title', '').strip()
        if title:
            tc_titles.append(title)
        steps_xml = f.get('Microsoft.VSTS.TCM.Steps', '') or ''
        # Each step is wrapped in <step><parameterizedString>action</…><parameterizedString>expected</…>
        if steps_xml:
            plain = _strip_html(steps_xml)
            # Keep just the first ~200 chars per TC to bound the sample.
            steps_samples.append(plain[:200])

    keywords = _extract_keywords(tc_titles + steps_samples, top_n=18)
    domain_keywords = _extract_domain_keywords(
        tc_titles + steps_samples, top_n=12)

    return {
        "neighbour_stories": neighbour_stories,
        "neighbour_tc_titles": tc_titles[:30],
        "neighbour_tc_keywords": keywords,
        # Vocab-aligned subset — preferred for enrichment because every
        # word in it is a known EPP business term.
        "neighbour_domain_keywords": domain_keywords,
        "neighbour_steps_samples": steps_samples[:10],
        "summary": (f"{len(neighbour_stories)} neighbour stories"
                    f" • {len(tc_titles)} historical TCs analysed"
                    f" • {len(domain_keywords)} domain keywords"),
    }
