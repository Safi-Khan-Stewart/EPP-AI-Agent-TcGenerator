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
python test/ado_advisor.py 432288
```

**Output:**
- Test Case work items created in ADO (linked to the user story)
- `test_cases_US417882.html` — local HTML report

### Step-by-step mode (no browser)

The same pipeline can be split into separate steps. Claude uses these, and they
are handy for scripting too. Generated test cases are saved to
`reports/test_cases_US<ID>.json`, which can be edited before pushing.

```powershell
# 1. Generate only (reads from ADO, writes the JSON, no server)
python test/ado_advisor.py --json 432288

# 2. (optional) after editing the JSON: validate it, re-number, list the test cases
python test/ado_advisor.py --check reports/test_cases_US432288.json

# 3a. Push chosen test cases (numbers from the list) to ADO and link them to the story
python test/ado_advisor.py --push reports/test_cases_US432288.json --select 1,3-5

# 3b. ...or review them in the browser page instead
python test/ado_advisor.py --review reports/test_cases_US432288.json
```

Pushed test cases are recorded in the JSON, so re-running a push never creates
duplicates. Generation also lists the test cases already linked to the story in ADO.

---

## Using with Claude

The project ships with Claude support (replacing the previous GitHub Copilot setup):

| File | What it does |
| ---- | ------------ |
| `CLAUDE.md` | Project instructions Claude loads automatically |
| `.claude/skills/` | Slash commands: `/generate-test-cases`, `/sprint-status`, `/add-lesson` |
| `.claude/settings.json` | Lets safe commands run without prompts; always asks before pushing to ADO |
| `.mcp.json` + `test/mcp_server.py` | MCP server exposing the generator as tools (Claude Code and Claude Desktop) |

### Claude Code (terminal or VS Code chat panel)

Set the `ADO_*` environment variables (see [Configuration](#configuration)) and
install the dependencies into `.venv`, then open the project folder:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
claude          # or open the Claude Code panel in VS Code
```

Then ask in plain language or use a slash command:

```
/generate-test-cases 432288
```

Claude generates the test cases, reviews them against `Rules.md` (scope, titles,
steps, coverage of every acceptance criterion), fixes real problems, shows you a
numbered table and asks which numbers to push. Nothing is created in ADO until
you name the test cases, and Claude Code asks for confirmation before the push
runs. Say "open the review page" if you prefer the browser checkboxes.

- `/sprint-status` (or `/sprint-status full` for the advisor report)
- `/add-lesson <feedback> [story id]` turns reviewer feedback into a
  `LessonsLearned.md` entry and the matching generator code fix.

**First run:** start `claude` in this folder once from a terminal and accept
both prompts: **trust this folder** (until then Claude Code ignores the
project's `.claude/settings.json` permissions) and **approve the
`epp-testcase-generator` MCP server** from `.mcp.json`. With the server
approved, generating and refining test cases runs without permission prompts
and only the push asks for confirmation. Without it, the skills fall back to the
command line. Claude Code's PowerShell tool then asks before every generator
command, because its permission rules can't pre-approve commands that contain
file paths.

### Claude Desktop

Add the server to `%APPDATA%\Claude\claude_desktop_config.json`, using the
absolute path of your clone, then restart Claude Desktop:

```json
{
  "mcpServers": {
    "epp-testcase-generator": {
      "command": "D:\\EPP AI Generator\\EPP-AI-Agent-TcGenerator\\.venv\\Scripts\\python.exe",
      "args": ["D:\\EPP AI Generator\\EPP-AI-Agent-TcGenerator\\test\\mcp_server.py"]
    }
  }
}
```

In a chat, pick the **"Generate EPP test cases for a User Story"** prompt from
the + menu, or just ask, e.g. *"Generate test cases for user story 432288"*.
Tools: `get_user_story`, `generate_test_cases`, `get_test_cases`,
`update_test_cases`, `push_test_cases`, `open_review_page`,
`get_generation_rules`, `sprint_status`.

The server reads the `ADO_*` variables from your user environment; if Claude
Desktop doesn't see them, put them in a `.env` file in the project root (same
format as `.env.example`). To keep tool calls fast, the server skips the
14-day refresh of the domain documentation; the command line still runs it.

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
│   ├── domain_context.py    # EPP portal/screen/role catalogue + area tag
│   ├── history_context.py   # Prior stories in the same Area Path
│   ├── sprint_status.py     # Standalone sprint status report generator
│   └── mcp_server.py        # MCP server for Claude Desktop / Claude Code
├── reports\                  # All generated reports go here
│   ├── sprint_status.html
│   ├── sprint_report.html
│   ├── test_cases_US*.html
│   ├── test_cases_US*.json   # Review sessions (generate → edit → push)
│   └── review_test_cases_US*.html
├── .claude\
│   ├── settings.json         # Shared Claude Code permissions
│   └── skills\               # /generate-test-cases, /sprint-status, /add-lesson
├── CLAUDE.md                 # Instructions Claude loads for this project
├── .mcp.json                 # Registers the MCP server with Claude Code
├── Rules.md                  # Test case generation rules (single source of truth)
├── LessonsLearned.md         # Reviewer feedback enforced by the generator
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
