# Azure DevOps Advisor & Sprint Status Reporter

A Python-based framework that connects to Azure DevOps REST API to analyze sprint progress, generate test cases, and produce beautiful HTML reports.

---

## Prerequisites

- Python 3.10+
- Azure DevOps Personal Access Token (PAT) with read access to work items and projects
- Install dependencies:
  ```powershell
  python -m pip install -r requirements.txt
  ```

---

## Quick Start — Sprint Status Report

Generate an HTML report of the **current sprint** showing all user stories, their states, and assigned team members.

```powershell
# Generate report (terminal output + HTML file)
python test/sprint_status.py

# Generate report AND auto-open in browser
python test/sprint_status.py --open
```

**Output:** `sprint_status.html` — a modern, visually appealing report containing:

- Sprint name, path, and dates
- Summary cards (total stories + count per state)
- Color-coded progress bar with hover tooltips
- User stories table with ID, title, assignee (with avatar), and state badges
- Team allocation grid

---

## Generate & Push Test Cases to ADO

Given a **User Story ID**, the script will:
1. Fetch the user story's title, description, and all acceptance criteria
2. Parse each AC (GIVEN / WHEN / THEN format)
3. Generate comprehensive test cases (one per AC + E2E + Negative + UI + Regression)
4. **Create them as Test Case work items in Azure DevOps** in proper TCM Steps XML format
5. **Link each test case to the user story** with a "Tests / Tested By" relation
6. Generate an HTML report locally

```powershell
# Just pass the User Story ID as an argument
python test/ado_advisor.py 417882
```

**Output:**
- Test Case work items created in ADO (linked to the user story)
- `test_cases_US417882.html` — local HTML report

---

## Full Advisor Report

Run the full Azure DevOps Advisor to get agent pool analysis, pipeline recommendations, sprint progress with pie charts, resource allocation, test case details, and AI-suggested test cases for stories without coverage.

```powershell
python test/ado_advisor.py
```

**Output:** `sprint_report.html` — comprehensive sprint report with:

- DevOps recommendations (agent pools, pipeline health)
- Sprint progress by user story state
- CSS-only pie charts for user story and test case allocation
- Expandable test case details under each user story
- AI-suggested test cases for stories with no test coverage
- Resource-wise allocation summary

---

## Generate Test Cases for a Specific User Story

The advisor can generate detailed test cases based on a user story's acceptance criteria. Edit the `main()` function in `test/ado_advisor.py` to target a specific work item ID:

```python
generate_test_cases_report_html(417882)
```

**Output:** `test_cases_US417882.html` — includes:

- Parsed acceptance criteria (GIVEN / WHEN / THEN)
- One test case per acceptance criterion
- End-to-end flow test case
- Negative / boundary test case
- UI/UX and regression test cases

---

## Project Structure

```
d:\ADO with PAT\
├── test\
│   ├── ado_advisor.py       # Full advisor: analysis, reports, test case generation
│   └── sprint_status.py     # Standalone sprint status report generator
├── reports\                  # All generated reports go here
│   ├── sprint_status.html
│   ├── sprint_report.html
│   ├── test_cases_US*.html
│   └── review_test_cases_US*.html
├── Rules.md                  # Test case generation rules (single source of truth)
├── Testcase_Generator.md     # Workflow & instructions
├── requirements.txt          # Python dependencies
├── README.md                 # This file
└── .vscode/
    └── tasks.json            # VS Code tasks
```

---

## Configuration

All Azure DevOps credentials are loaded from **environment variables** so secrets never end up in source control.

### Required environment variables

| Variable        | Description                                            | Example                  |
| --------------- | ------------------------------------------------------ | ------------------------ |
| `ADO_ORG`       | Azure DevOps organization name                         | `StewartTitle`           |
| `ADO_PROJECT`   | Target project name                                    | `Enterprise Payments`    |
| `ADO_PAT`       | Personal Access Token (Read & Write on Work Items)     | `xxxxxxxxxxxxxxxxxxxx`   |
| `ADO_USERNAME`  | *(Optional)* Username — leave empty for PAT-only auth  | *(empty)*                |
| `ADO_PASSWORD`  | *(Optional)* Password if not using PAT                 | *(empty)*                |

### Set in PowerShell (current session only)

```powershell
$env:ADO_ORG     = "StewartTitle"
$env:ADO_PROJECT = "Enterprise Payments"
$env:ADO_PAT     = "your_personal_access_token_here"
$env:ADO_USERNAME = ""
$env:ADO_PASSWORD = ""
```

### Set in PowerShell (persist across sessions — User scope)

```powershell
[Environment]::SetEnvironmentVariable("ADO_ORG",     "StewartTitle",          "User")
[Environment]::SetEnvironmentVariable("ADO_PROJECT", "Enterprise Payments",   "User")
[Environment]::SetEnvironmentVariable("ADO_PAT",     "your_pat_here",         "User")
[Environment]::SetEnvironmentVariable("ADO_USERNAME","",                       "User")
[Environment]::SetEnvironmentVariable("ADO_PASSWORD","",                       "User")
```

> Open a **new** PowerShell window after setting User-scope vars for them to take effect.

### Verify

```powershell
$env:ADO_ORG; $env:ADO_PROJECT; $env:ADO_PAT.Substring(0,6) + "..."
```

### Remove (if needed)

```powershell
[Environment]::SetEnvironmentVariable("ADO_PAT", $null, "User")
```

> A `.env.example` file is included as a template. Never commit your real `.env` — it's already in `.gitignore`.

---

## License

Internal use only — Stewart Title.
