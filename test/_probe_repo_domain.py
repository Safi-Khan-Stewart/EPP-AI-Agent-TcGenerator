"""Extract the business domain from EPP Azure DevOps Git repositories and
append a structured summary to `EPP_Portal_Business_Documentation.md`.

Uses the same env vars (`ADO_ORG`, `ADO_PAT`, `ADO_PROJECT`) as
`ado_advisor.py`. Requires the PAT to have **Code (Read)** scope.

Run:
    python test/_probe_repo_domain.py
"""

from __future__ import annotations

import base64
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from typing import Iterable

import requests

ADO_ORG = os.environ.get("ADO_ORG")
ADO_PAT = os.environ.get("ADO_PAT")
ADO_PROJECT = os.environ.get("ADO_PROJECT", "Enterprise Payments")

if not ADO_ORG or not ADO_PAT:
    print("ERROR: ADO_ORG / ADO_PAT env vars must be set.", file=sys.stderr)
    sys.exit(1)

_AUTH = {
    "Authorization": "Basic " + base64.b64encode(f":{ADO_PAT}".encode()).decode(),
    "Accept": "application/json",
}

REPOS = [
    "Epp.Admin",
    "Epp.Api",
    "Epp.Api.Escrow.Operations",
    "Epp.Escrow.Admin",
    "Epp.Escrow.Customer",
    "Epp.Parties.Onboarding",
    "Epp.Parties.Payment",
    "Epp.Parties.Profile",
]

BASE = f"https://dev.azure.com/{ADO_ORG}/{ADO_PROJECT}/_apis/git/repositories"

# File-name patterns worth inspecting for domain vocabulary.
INTEREST_EXT = (".cs", ".ts", ".tsx", ".md", ".json", ".yml", ".yaml")
README_RX = re.compile(r"^readme(\.md|\.txt)?$", re.IGNORECASE)
DOCS_DIR_RX = re.compile(r"(^|/)(docs?|documentation)/", re.IGNORECASE)
CONTROLLER_RX = re.compile(r"controller\.cs$", re.IGNORECASE)
DTO_RX = re.compile(r"(dto|model|entity|contract|command|query)\.cs$", re.IGNORECASE)
ROUTE_RX = re.compile(r"\[route\(\"([^\"]+)\"\)\]", re.IGNORECASE)
HTTP_VERB_RX = re.compile(
    r"\[Http(Get|Post|Put|Delete|Patch)(?:\(\"([^\"]*)\"\))?\]",
    re.IGNORECASE,
)
CLASS_NAME_RX = re.compile(r"public\s+(?:sealed\s+|abstract\s+|static\s+)?class\s+(\w+)")
ENUM_RX = re.compile(r"public\s+enum\s+(\w+)")
NAMESPACE_RX = re.compile(r"namespace\s+([\w\.]+)")


def _get(url: str, **kwargs) -> requests.Response:
    r = requests.get(url, headers=_AUTH, timeout=30, **kwargs)
    return r


def _list_items(repo: str) -> list[dict]:
    url = (f"{BASE}/{repo}/items"
           f"?recursionLevel=Full&api-version=7.1&$format=json"
           f"&includeContentMetadata=true&latestProcessedChange=true")
    r = _get(url)
    if r.status_code != 200:
        print(f"  [{repo}] list failed: {r.status_code} {r.text[:180]}")
        return []
    return r.json().get("value", []) or []


def _get_text(repo: str, path: str, max_bytes: int = 60_000) -> str:
    url = (f"{BASE}/{repo}/items?path={requests.utils.quote(path)}"
           f"&api-version=7.1&$format=text&includeContent=true")
    try:
        r = _get(url)
        if r.status_code != 200:
            return ""
        return r.text[:max_bytes]
    except Exception:
        return ""


def _first_paragraph(md: str, max_chars: int = 600) -> str:
    if not md:
        return ""
    # Strip badges / front-matter
    lines = [l for l in md.splitlines()
             if l.strip() and not l.strip().startswith(("![", "[!", "<!--"))]
    body = "\n".join(lines[:60])
    # First markdown paragraph
    m = re.search(r"^#\s+.+?\n+([^#].+?)(?:\n\s*\n|\Z)", body, re.DOTALL)
    para = m.group(1).strip() if m else body[:max_chars]
    para = re.sub(r"\s+", " ", para).strip()
    return para[:max_chars]


def _analyze_repo(repo: str) -> dict:
    print(f"→ {repo}")
    items = _list_items(repo)
    files = [i for i in items if i.get("gitObjectType") == "blob"]
    print(f"    {len(files)} file(s)")

    readmes: list[tuple[str, str]] = []
    docs: list[tuple[str, str]] = []
    controllers: list[str] = []
    routes: set[str] = set()
    endpoints: set[str] = set()
    dtos: set[str] = set()
    enums: set[str] = set()
    namespaces: set[str] = set()
    project_names: set[str] = set()

    # Cap file reads so we don't hammer the API
    inspected = 0
    for f in files:
        path = f.get("path", "")
        name = path.rsplit("/", 1)[-1]
        if not name:
            continue
        low = name.lower()

        if low.endswith(".csproj"):
            project_names.add(name[:-7])

        if README_RX.match(low) and inspected < 12:
            content = _get_text(repo, path)
            if content:
                readmes.append((path, _first_paragraph(content)))
                inspected += 1
            continue

        # `docs/**/*.md` — pull additional narrative context
        if low.endswith(".md") and DOCS_DIR_RX.search(path) and len(docs) < 12:
            content = _get_text(repo, path, max_bytes=40_000)
            if content:
                docs.append((path, _first_paragraph(content, max_chars=800)))
                inspected += 1
            continue

        if not low.endswith(INTEREST_EXT):
            continue

        if CONTROLLER_RX.search(low) or DTO_RX.search(low):
            if inspected >= 80:
                continue
            content = _get_text(repo, path, max_bytes=25_000)
            inspected += 1
            if not content:
                continue

            if CONTROLLER_RX.search(low):
                controllers.append(name[:-3])
                # Extract [Route(...)] and HTTP verbs
                for m in ROUTE_RX.finditer(content):
                    routes.add(m.group(1))
                for m in HTTP_VERB_RX.finditer(content):
                    verb = m.group(1).upper()
                    ep = m.group(2) or ""
                    endpoints.add(f"{verb} {ep}".strip())

            for m in CLASS_NAME_RX.finditer(content):
                nm = m.group(1)
                if DTO_RX.search(low):
                    dtos.add(nm)
            for m in ENUM_RX.finditer(content):
                enums.add(m.group(1))
            for m in NAMESPACE_RX.finditer(content):
                namespaces.add(m.group(1))

    return {
        "repo":        repo,
        "file_count":  len(files),
        "readmes":     readmes,
        "docs":        docs,
        "controllers": sorted(controllers),
        "routes":      sorted(routes),
        "endpoints":   sorted(endpoints)[:60],
        "dtos":        sorted(dtos)[:60],
        "enums":       sorted(enums)[:40],
        "namespaces":  sorted(namespaces)[:20],
        "projects":    sorted(project_names),
    }


def _classify_context(repo: str) -> str:
    r = repo.lower()
    if "admin" in r and "escrow" not in r and "parties" not in r:
        return "Administration Portal"
    if "escrow.admin" in r:
        return "Escrow Administration"
    if "escrow.customer" in r:
        return "Escrow Customer Experience"
    if "api.escrow.operations" in r:
        return "Escrow Operations API"
    if "parties.onboarding" in r:
        return "Parties Onboarding"
    if "parties.payment" in r:
        return "Parties Payment"
    if "parties.profile" in r:
        return "Parties Profile"
    if r == "epp.api":
        return "Core Platform API"
    return "Other"


def _render_markdown(summaries: list[dict]) -> str:
    now = datetime.utcnow().strftime("%Y-%m-%d")
    lines: list[str] = []
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("# 📦 Business Domain — Source-Code Derived")
    lines.append("")
    lines.append(f"*Auto-generated {now} by `test/_probe_repo_domain.py` "
                 f"from the following Azure DevOps repositories in "
                 f"`{ADO_ORG}/{ADO_PROJECT}`.*")
    lines.append("")
    lines.append("This section is a **fact-based snapshot** of the code base "
                 "(controllers, routes, DTOs, enums, README summaries). It is "
                 "meant as an evidence layer supporting the human-authored "
                 "business documentation above, not a replacement for it.")
    lines.append("")

    # Bounded-context table of contents
    by_ctx: dict[str, list[dict]] = defaultdict(list)
    for s in summaries:
        by_ctx[_classify_context(s["repo"])].append(s)

    lines.append("## Bounded Contexts")
    lines.append("")
    lines.append("| Bounded Context | Repositories |")
    lines.append("|---|---|")
    for ctx in sorted(by_ctx):
        repos = ", ".join(f"`{s['repo']}`" for s in by_ctx[ctx])
        lines.append(f"| **{ctx}** | {repos} |")
    lines.append("")

    for ctx in sorted(by_ctx):
        lines.append(f"## {ctx}")
        lines.append("")
        for s in by_ctx[ctx]:
            lines.append(f"### `{s['repo']}`")
            lines.append("")
            lines.append(f"- **Files scanned:** {s['file_count']}")
            if s["projects"]:
                lines.append(f"- **Projects (`*.csproj`):** "
                             + ", ".join(f"`{p}`" for p in s["projects"][:20]))
            if s["namespaces"]:
                lines.append(f"- **Root namespaces:** "
                             + ", ".join(f"`{n}`" for n in s["namespaces"][:8]))
            if s["controllers"]:
                lines.append(f"- **Controllers ({len(s['controllers'])}):** "
                             + ", ".join(f"`{c}`" for c in s["controllers"][:25]))
            if s["routes"]:
                lines.append(f"- **Base routes:** "
                             + ", ".join(f"`{r}`" for r in s["routes"][:15]))
            if s["endpoints"]:
                lines.append(f"- **Sample HTTP endpoints ({len(s['endpoints'])}):**")
                lines.append("")
                lines.append("  ```")
                for ep in s["endpoints"][:20]:
                    lines.append(f"  {ep}")
                lines.append("  ```")
            if s["dtos"]:
                lines.append(f"- **DTO / Model / Command / Query types "
                             f"({len(s['dtos'])}):** "
                             + ", ".join(f"`{d}`" for d in s["dtos"][:25]))
            if s["enums"]:
                lines.append(f"- **Domain enums:** "
                             + ", ".join(f"`{e}`" for e in s["enums"][:15]))
            if s["readmes"]:
                lines.append("- **README excerpt:**")
                for path, para in s["readmes"][:2]:
                    lines.append("")
                    lines.append(f"  > *{path}* — {para}")
            if s["docs"]:
                lines.append(f"- **`docs/` narrative ({len(s['docs'])} file(s)):**")
                for path, para in s["docs"][:5]:
                    lines.append("")
                    lines.append(f"  > *{path}* — {para}")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("### How to refresh")
    lines.append("")
    lines.append("Re-run `python test/_probe_repo_domain.py`. The probe "
                 "replaces the section between the "
                 "`# 📦 Business Domain — Source-Code Derived` "
                 "heading and end-of-file so the human-authored content "
                 "above is preserved.")
    lines.append("")
    return "\n".join(lines)


def _upsert_into_doc(doc_path: str, new_section: str) -> None:
    marker = "# 📦 Business Domain — Source-Code Derived"
    existing = ""
    if os.path.isfile(doc_path):
        with open(doc_path, "r", encoding="utf-8") as fh:
            existing = fh.read()

    if marker in existing:
        head = existing.split(marker, 1)[0].rstrip() + "\n"
        # Strip the previous "---\n\n" separator we appended last time
        head = re.sub(r"\n---\s*\n\s*$", "\n", head)
        merged = head + new_section
    else:
        merged = existing.rstrip() + "\n" + new_section

    with open(doc_path, "w", encoding="utf-8") as fh:
        fh.write(merged)


def main() -> None:
    force = ("--force" in sys.argv) or ("-f" in sys.argv)
    max_age_days = 14
    doc = os.path.join(os.path.dirname(__file__), "..",
                       "EPP_Portal_Business_Documentation.md")
    doc = os.path.abspath(doc)
    stamp_path = os.path.join(os.path.dirname(__file__),
                              ".repo_domain_lastrun")
    now_ts = datetime.utcnow()

    if not force and os.path.isfile(stamp_path):
        try:
            with open(stamp_path, "r", encoding="utf-8") as fh:
                last = datetime.fromisoformat(fh.read().strip())
            age = (now_ts - last).days
            if age < max_age_days:
                print(f"⏭  Domain doc refreshed {age} day(s) ago "
                      f"(< {max_age_days}-day cadence). "
                      f"Use --force to re-run anyway.")
                return
            else:
                print(f"⏰  Last refresh was {age} day(s) ago — "
                      f"running scheduled update.")
        except Exception:
            pass  # corrupt stamp — treat as due

    print(f"Target org/project : {ADO_ORG}/{ADO_PROJECT}")
    print(f"Repositories       : {len(REPOS)}")
    summaries: list[dict] = []
    for repo in REPOS:
        try:
            summaries.append(_analyze_repo(repo))
        except Exception as e:
            print(f"  [{repo}] error: {e}")

    md = _render_markdown(summaries)
    _upsert_into_doc(doc, md)

    # Persist run timestamp for the 14-day cadence gate
    try:
        with open(stamp_path, "w", encoding="utf-8") as fh:
            fh.write(now_ts.isoformat())
    except Exception:
        pass

    print(f"\n✅ Updated: {doc}")
    print(f"⏱  Next automatic refresh due after: "
          f"{(now_ts.replace(microsecond=0)).isoformat()} + {max_age_days} days")


if __name__ == "__main__":
    main()
