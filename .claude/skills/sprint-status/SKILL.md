---
name: sprint-status
description: Report the current EPP sprint from Azure DevOps — user stories by state and by assignee — or, when asked for the full/advisor report, agent pools, pipeline health, test coverage and suggested test cases.
argument-hint: "[full]"
---

# Sprint status $ARGUMENTS

- **Default:** call the `sprint_status` tool of the `epp-testcase-generator`
  MCP server (it writes `reports/sprint_status.html`), or if it isn't
  available run `.venv/Scripts/python.exe test/sprint_status.py` from the repo
  root (writes `sprint_status.html`; add `--open` only if the user wants it
  opened in the browser). Summarise the sprint name, story counts per state,
  and stories per assignee.
- **Full / advisor report** (argument `full`, or the user asks about agent
  pools, pipelines or test coverage): run
  `.venv/Scripts/python.exe test/ado_advisor.py` with no arguments. Summarise
  the recommendations and point to `sprint_report.html`.

Both only read from Azure DevOps. If they fail on missing `ADO_*` variables,
point the user to the Configuration section of README.md.
