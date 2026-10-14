"""
EPP Test Case Generator — MCP server
====================================
Exposes the AI Test Case Generator to Claude (Claude Desktop, Claude Code
or any MCP client) over stdio. Every tool wraps the same functions the CLI
uses in `ado_advisor.py`, so Rules.md, the LessonsLearned guardrails and
the ADO field mapping are identical whichever way the generator is driven.

Workflow the tools support:
    generate_test_cases  ->  (Claude reviews / refines)  update_test_cases
    ->  user picks test cases  ->  push_test_cases

Run (normally started by the MCP client, see README.md):
    .venv\\Scripts\\python.exe test\\mcp_server.py
"""

import contextlib
import io
import json
import os
import socket
import subprocess
import sys
import threading
import urllib.parse
from typing import Any, Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

# A tool call must never block on the multi-minute repo-domain scan; the CLI
# keeps running it on its 14-day cadence.
os.environ.setdefault('EPP_SKIP_DOMAIN_REFRESH', '1')


def _load_dotenv():
    """Fill missing ADO_* settings from a repo-root .env file (see
    .env.example) — handy when the MCP client doesn't inherit your user
    environment variables. Real environment variables always win."""
    path = os.path.join(ROOT, '.env')
    if not os.path.isfile(path):
        return
    with open(path, 'r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

# The generator reports progress with print(); tools capture it into the
# result, one call at a time because redirect_stdout is process-wide.
_lock = threading.Lock()
_advisor_module = None


def _advisor():
    """Import ado_advisor lazily so a missing ADO_* variable becomes a
    readable tool error instead of killing the server at startup."""
    global _advisor_module
    if _advisor_module is None:
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                import ado_advisor
            except SystemExit:
                raise ToolError(
                    "ADO_ORG, ADO_PROJECT and ADO_PAT must be set (user "
                    "environment variables or a .env file in the repo root) "
                    "before the MCP server starts.") from None
        _advisor_module = ado_advisor
    return _advisor_module


@contextlib.contextmanager
def _captured():
    buf = io.StringIO()
    with _lock, contextlib.redirect_stdout(buf):
        yield buf


def _work_item_url(a, work_item_id):
    return (f"https://dev.azure.com/{urllib.parse.quote(a.ADO_ORG)}/"
            f"{urllib.parse.quote(a.ADO_PROJECT)}/_workitems/edit/{work_item_id}")


def _session_path(a, story_id):
    path = a.review_session_path(story_id)
    if not os.path.isfile(path):
        raise ToolError(f"No generated test cases for US #{story_id} yet — "
                        f"call generate_test_cases first.")
    return path


def _load(a, path):
    """Load + validate a saved session; validation problems become tool
    errors the model can read and fix."""
    with _captured():
        try:
            return a.load_review_session(path)
        except ValueError as e:
            raise ToolError(str(e)) from None


def _session_view(a, ctx, path):
    """What the tools return: the story plus numbered test cases (the
    numbers are what push_test_cases expects)."""
    history = ctx.get('history') or {}
    test_cases = []
    for n, tc in enumerate(ctx['test_cases'], 1):
        view = {'number': n}
        view.update({k: v for k, v in tc.items() if k not in ('index', 'uid')})
        if tc.get('ado_id'):
            view['ado_url'] = _work_item_url(a, tc['ado_id'])
        test_cases.append(view)
    return {
        'session_file': path,
        'story': {
            'id': ctx['story_id'],
            'url': _work_item_url(a, ctx['story_id']),
            'title': ctx.get('title', ''),
            'state': ctx.get('state', ''),
            'assigned_to': ctx.get('assignee', ''),
            'area_path': ctx.get('area_path', ''),
            'iteration_path': ctx.get('iteration_path', ''),
            'epp_area_tag': ctx.get('epp_area', ''),
            'description': ctx.get('description', ''),
            'acceptance_criteria': ctx.get('acceptance_criteria', ''),
        },
        'history_used': {
            'summary': history.get('summary', ''),
            'neighbour_stories': [
                f"#{s.get('id')} [{s.get('state', '')}] {s.get('title', '')}"
                for s in history.get('neighbour_stories') or []],
            'domain_keywords': history.get('neighbour_domain_keywords') or [],
        },
        # Already linked to the story in ADO when generation ran — don't
        # push duplicates of these.
        'existing_test_cases_in_ado': ctx.get('existing_test_cases') or [],
        'test_cases': test_cases,
    }


server = MCPServer(
    "epp-testcase-generator",
    instructions=(
        "Generates Azure DevOps test cases for EPP (Enterprise Payments) User "
        "Stories following Rules.md. Typical flow: generate_test_cases -> "
        "review the result against get_generation_rules and refine with "
        "update_test_cases (stay strictly within the story's scope) -> show "
        "the user a numbered list -> push_test_cases ONLY with the numbers "
        "the user explicitly approved. Pushing creates real work items in "
        "Azure DevOps."),
)


@server.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
def get_user_story(story_id: int) -> dict[str, Any]:
    """Fetch an Azure DevOps User Story: title, state, assignee, area and
    iteration path, tags, cleaned description and acceptance criteria."""
    a = _advisor()
    with _captured() as log:
        work_item = a.get_work_item_full_details(story_id)
    if not work_item:
        raise ToolError(f"Could not fetch work item {story_id}. {log.getvalue().strip()}")
    f = work_item.get('fields', {})
    return {
        'id': story_id,
        'url': _work_item_url(a, story_id),
        'type': f.get('System.WorkItemType', ''),
        'title': f.get('System.Title', ''),
        'state': f.get('System.State', ''),
        'assigned_to': (f.get('System.AssignedTo') or {}).get('displayName', 'Unassigned'),
        'area_path': f.get('System.AreaPath', ''),
        'iteration_path': f.get('System.IterationPath', ''),
        'tags': f.get('System.Tags', ''),
        'description': a.clean_html(f.get('System.Description') or ''),
        'acceptance_criteria': a.clean_html(
            f.get('Microsoft.VSTS.Common.AcceptanceCriteria') or ''),
    }


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False,
                                         open_world_hint=True))
def generate_test_cases(story_id: int) -> dict[str, Any]:
    """Run the EPP test case generator for a User Story (domain context,
    historical context, scope rules, LessonsLearned guardrails). Saves the
    result as reports/test_cases_US<ID>.json — overwriting any earlier
    unpushed generation — and returns the story, the numbered test cases
    and the generator log. Nothing is written to Azure DevOps. Takes
    roughly a minute."""
    a = _advisor()
    with _captured() as log:
        ctx = a.build_review_session(story_id)
        path = a.save_review_session(ctx) if ctx else None
    if not ctx:
        raise ToolError(f"No test cases generated for US #{story_id}.\n"
                        f"{log.getvalue()[-3000:]}")
    result = _session_view(a, ctx, path)
    result['generator_log'] = log.getvalue()
    return result


@server.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_test_cases(story_id: int) -> dict[str, Any]:
    """Return the saved test cases for a User Story (from the last
    generate_test_cases / update_test_cases), including the ADO ids of any
    that were already pushed."""
    a = _advisor()
    path = _session_path(a, story_id)
    return _session_view(a, _load(a, path), path)


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True,
                                         idempotent_hint=True))
def update_test_cases(story_id: int, test_cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Replace the saved test case list for a User Story with an edited one
    (reworded titles/steps, removed or added test cases). Pass the FULL list
    in the order you want; each item uses the same fields get_test_cases
    returns (title, objective, preconditions, steps[], expected[],
    overall_expected, priority 1-4, test_type, test_category, ...). Keep
    `ado_id` on test cases that were already pushed. The list is validated
    against Rules.md enumerations and the LessonsLearned guardrails; invalid
    input is rejected with the reasons. Nothing is written to Azure DevOps."""
    a = _advisor()
    path = _session_path(a, story_id)
    with open(path, 'r', encoding='utf-8') as fh:
        ctx = json.load(fh)
    ctx['test_cases'] = [{k: v for k, v in tc.items() if k not in ('number', 'ado_url')}
                         for tc in test_cases]
    with _captured():
        try:
            ctx = a.normalize_review_session(ctx)
        except ValueError as e:
            raise ToolError(str(e)) from None
        a.save_review_session(ctx, path)
    return _session_view(a, ctx, path)


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False,
                                         idempotent_hint=True, open_world_hint=True))
def push_test_cases(story_id: int, numbers: Optional[list[int]] = None,
                    push_all: bool = False) -> dict[str, Any]:
    """Create the chosen saved test cases as Test Case work items in Azure
    DevOps and link each to the User Story ("Tests / Tested By").
    `numbers` are the 1-based numbers from get_test_cases. Only call this
    after the user has explicitly confirmed which test cases to push.
    Test cases already pushed are skipped, so retrying never duplicates."""
    a = _advisor()
    path = _session_path(a, story_id)
    ctx = _load(a, path)
    tcs = ctx['test_cases']
    if push_all:
        chosen = tcs
    elif numbers:
        bad = sorted(n for n in set(numbers) if not 1 <= n <= len(tcs))
        if bad:
            raise ToolError(f"Test case number(s) out of range 1-{len(tcs)}: {bad}")
        chosen = [tcs[n - 1] for n in sorted(set(numbers))]
    else:
        raise ToolError("Pass the test case numbers the user approved, or push_all=true.")

    with _captured() as log:
        try:
            results = a.push_test_cases_to_ado(ctx, chosen)
        finally:  # record created ids even if the run is interrupted
            a.save_review_session(ctx, path)
    for r in results:
        if r.get('tc_id'):
            r['url'] = _work_item_url(a, r['tc_id'])
    return {
        'story_id': story_id,
        'created': sum(1 for r in results if r['success'] and not r.get('skipped')),
        'already_in_ado': sum(1 for r in results if r.get('skipped')),
        'failed': sum(1 for r in results if not r['success']),
        'results': results,
        'log': log.getvalue(),
    }


@server.tool(annotations=ToolAnnotations(read_only_hint=True))
def open_review_page(story_id: int) -> str:
    """Open the browser review page (checkboxes + "Add to ADO" button) for
    the saved test cases, for users who prefer to pick and push there. The
    page's local server stops by itself after a push."""
    a = _advisor()
    path = _session_path(a, story_id)
    with socket.socket() as s:
        if s.connect_ex(('127.0.0.1', 8765)) == 0:
            raise ToolError("A review page is already being served on "
                            "http://localhost:8765/review — finish or close "
                            "that one first.")
    flags = 0
    if sys.platform == 'win32':
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [sys.executable, os.path.join(HERE, 'ado_advisor.py'), '--review', path],
        cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True)
    return ("Review page opening in your browser at http://localhost:8765/review. "
            "Pushed test cases are recorded back into the saved session.")


@server.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_generation_rules(include_lessons_learned: bool = False) -> str:
    """Return Rules.md — the single source of truth for test case structure,
    coverage, scope (RULE SCOPE 16) and ADO tagging — and optionally
    LessonsLearned.md (reviewer feedback the generator must not regress)."""
    names = ['Rules.md'] + (['LessonsLearned.md'] if include_lessons_learned else [])
    parts = []
    for name in names:
        with open(os.path.join(ROOT, name), 'r', encoding='utf-8') as fh:
            parts.append(f"===== {name} =====\n{fh.read()}")
    return '\n\n'.join(parts)


@server.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
def sprint_status() -> str:
    """Summarise the current sprint: user story counts per state and per
    assignee. Also writes reports/sprint_status.html."""
    reports = os.path.join(ROOT, 'reports')
    os.makedirs(reports, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, 'sprint_status.py')],
        cwd=reports, capture_output=True, text=True, encoding='utf-8',
        errors='replace', timeout=300,
        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    output = (proc.stdout or '') + (proc.stderr or '')
    if proc.returncode != 0:
        raise ToolError(output.strip() or f"sprint_status.py exited with {proc.returncode}")
    return output


@server.prompt(title="Generate EPP test cases for a User Story")
def generate_test_cases_for_story(story_id: str) -> str:
    """Guided workflow: generate, review against Rules.md, refine, then push
    only the test cases you approve."""
    return f"""Generate Azure DevOps test cases for EPP User Story #{story_id}.

1. Call generate_test_cases with story_id={story_id}.
2. Call get_generation_rules (include_lessons_learned=true) and review every
   generated test case against them. The story's Title, Description and
   Acceptance Criteria are the ONLY source of scope (RULE SCOPE 16): never add
   roles, screens, data flows or workflows the story doesn't mention.
3. Fix real problems only — clipped or vague titles (RULE GEN 02: start with
   "Verify", no "that"), steps that don't exercise the acceptance criterion,
   expected results that don't match their step, wrong test_type /
   test_category / priority. Save fixes with update_test_cases.
4. Show me a numbered table (number, title, category, type, priority) plus a
   short note on each change you made and any acceptance criterion that is
   still not covered.
5. Ask which numbers to push. Call push_test_cases only with the numbers I
   approve, then list the created ADO test case ids with their links."""


if __name__ == '__main__':
    server.run()
