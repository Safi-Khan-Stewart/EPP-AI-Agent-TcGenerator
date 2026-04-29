"""
Sprint Status Report Generator
================================
Run this script to generate an HTML report of the current sprint,
listing all user stories with their assigned team members and states.

Usage:
    python sprint_status.py
    python sprint_status.py --open   (auto-open in browser)
"""

import requests
import base64
import urllib.parse
import urllib3
import sys
import os
import webbrowser
from datetime import datetime
from jinja2 import Template

# ── Configuration loaded from environment variables ──────────────────────────
# Set these in PowerShell before running. See README.md for instructions.
ADO_ORG = os.environ.get("ADO_ORG")
ADO_PAT = os.environ.get("ADO_PAT")
ADO_PROJECT = os.environ.get("ADO_PROJECT")
ADO_USERNAME = os.environ.get("ADO_USERNAME", "")  # optional, usually empty for PAT auth

_missing = [n for n, v in (("ADO_ORG", ADO_ORG), ("ADO_PAT", ADO_PAT), ("ADO_PROJECT", ADO_PROJECT)) if not v]
if _missing:
    print(f"ERROR: Missing required environment variable(s): {', '.join(_missing)}")
    print("Set them in PowerShell before running. See README.md for instructions.")
    sys.exit(1)
# ───────────────────────────────────────────────────────────────────────────────

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

b64_pat = base64.b64encode(f'{ADO_USERNAME}:{ADO_PAT}'.encode()).decode()
HEADERS = {
    'Content-Type': 'application/json',
    'Authorization': f'Basic {b64_pat}'
}
BASE_URL = f"https://dev.azure.com/{urllib.parse.quote(ADO_ORG)}"


def api_get(url):
    resp = requests.get(url, headers=HEADERS, verify=False, timeout=30)
    resp.raise_for_status()
    return resp.json()


def api_post(url, payload):
    resp = requests.post(url, headers=HEADERS, json=payload, verify=False, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_current_sprint():
    project = urllib.parse.quote(ADO_PROJECT)
    url = f"{BASE_URL}/{project}/_apis/work/teamsettings/iterations?$timeframe=current&api-version=7.1-preview.1"
    data = api_get(url)
    iterations = data.get('value', [])
    if not iterations:
        return None
    it = iterations[0]
    return {
        'id': it['id'],
        'name': it['name'],
        'path': it['path'],
        'start': it.get('attributes', {}).get('startDate', ''),
        'end': it.get('attributes', {}).get('finishDate', ''),
    }


def get_user_stories(iteration_path):
    project = urllib.parse.quote(ADO_PROJECT)
    wiql = {
        "query": (
            f"SELECT [System.Id] FROM WorkItems "
            f"WHERE [System.WorkItemType] = 'User Story' "
            f"AND [System.IterationPath] = '{iteration_path}' "
            f"ORDER BY [System.Id]"
        )
    }
    url = f"{BASE_URL}/{project}/_apis/wit/wiql?api-version=7.1"
    data = api_post(url, wiql)
    ids = [wi['id'] for wi in data.get('workItems', [])]
    if not ids:
        return []

    url = f"{BASE_URL}/_apis/wit/workitemsbatch?api-version=7.1"
    batch = api_post(url, {
        "ids": ids,
        "fields": [
            "System.Id", "System.Title", "System.State",
            "System.AssignedTo", "System.WorkItemType"
        ]
    })
    return batch.get('value', [])


def build_report_data(sprint, stories):
    """Organize stories by state and assignee."""
    state_order = {
        'New': 0, 'Ready For Team': 1, 'Ready For Review': 2,
        'In Progress': 3, 'QA In Progress': 4, 'Ready For QA': 5,
        'Ready to Deploy': 6, 'Closed': 7, 'Removed': 8,
    }
    state_colors = {
        'New': '#78909c',
        'Ready For Team': '#7e57c2',
        'Ready For Review': '#5c6bc0',
        'In Progress': '#1e88e5',
        'QA In Progress': '#00acc1',
        'Ready For QA': '#26a69a',
        'Ready to Deploy': '#66bb6a',
        'Closed': '#43a047',
        'Removed': '#ef5350',
    }

    story_list = []
    state_counts = {}
    assignee_counts = {}

    for s in stories:
        f = s.get('fields', {})
        state = f.get('System.State', 'Unknown')
        assignee_obj = f.get('System.AssignedTo', {})
        assignee = assignee_obj.get('displayName', 'Unassigned') if isinstance(assignee_obj, dict) else 'Unassigned'
        avatar = assignee_obj.get('imageUrl', '') if isinstance(assignee_obj, dict) else ''

        story_list.append({
            'id': s['id'],
            'title': f.get('System.Title', ''),
            'state': state,
            'assignee': assignee,
            'avatar': avatar,
            'state_color': state_colors.get(state, '#90a4ae'),
        })

        state_counts[state] = state_counts.get(state, 0) + 1
        assignee_counts[assignee] = assignee_counts.get(assignee, 0) + 1

    # Sort stories by state order, then by id
    story_list.sort(key=lambda x: (state_order.get(x['state'], 99), x['id']))

    total = len(story_list)
    # Build state progress data
    palette = ['#78909c', '#7e57c2', '#5c6bc0', '#1e88e5', '#00acc1', '#26a69a', '#66bb6a', '#43a047', '#ef5350', '#ffa726']
    state_progress = []
    for i, (state, count) in enumerate(sorted(state_counts.items(), key=lambda x: state_order.get(x[0], 99))):
        state_progress.append({
            'state': state,
            'count': count,
            'percent': round(count / total * 100, 1) if total else 0,
            'color': state_colors.get(state, palette[i % len(palette)]),
        })

    return {
        'stories': story_list,
        'total': total,
        'state_progress': state_progress,
        'assignee_counts': dict(sorted(assignee_counts.items(), key=lambda x: -x[1])),
    }


HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Sprint {{ sprint.name }} - Status Report</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Inter', sans-serif; background: #f0f2f5; color: #1a1a2e; min-height: 100vh; }

        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #fff; padding: 36px 0 28px; text-align: center;
        }
        .header h1 { font-size: 2em; font-weight: 700; letter-spacing: -0.5px; }
        .header .subtitle { opacity: 0.85; margin-top: 6px; font-size: 1.05em; }
        .header .sprint-dates { margin-top: 10px; font-size: 0.92em; opacity: 0.75; }

        .container { max-width: 1060px; margin: -24px auto 40px; padding: 0 20px; }

        /* ── Summary Cards ─────────────────────────────── */
        .summary-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 28px; }
        .summary-card { background: #fff; border-radius: 14px; padding: 22px 24px; box-shadow: 0 4px 16px rgba(0,0,0,0.06); text-align: center; }
        .summary-card .num { font-size: 2.4em; font-weight: 700; background: linear-gradient(135deg,#667eea,#764ba2); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .summary-card .lbl { color: #666; font-size: 0.92em; margin-top: 4px; }

        /* ── Progress Bar ──────────────────────────────── */
        .progress-section { background: #fff; border-radius: 14px; padding: 24px 28px; margin-bottom: 24px; box-shadow: 0 4px 16px rgba(0,0,0,0.06); }
        .progress-section h2 { font-size: 1.15em; margin-bottom: 14px; color: #333; }
        .progress-bar { height: 30px; border-radius: 15px; overflow: hidden; display: flex; background: #e8eaf0; }
        .progress-segment { height: 100%; transition: width .5s ease; position: relative; }
        .progress-segment:hover::after {
            content: attr(data-label); position: absolute; top: -32px; left: 50%; transform: translateX(-50%);
            background: #333; color: #fff; padding: 4px 10px; border-radius: 6px; font-size: 0.8em; white-space: nowrap;
        }
        .progress-legend { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 14px; }
        .progress-legend-item { display: flex; align-items: center; gap: 6px; font-size: 0.93em; }
        .legend-dot { width: 14px; height: 14px; border-radius: 4px; flex-shrink: 0; }

        /* ── Table ─────────────────────────────────────── */
        .table-section { background: #fff; border-radius: 14px; padding: 24px 28px; box-shadow: 0 4px 16px rgba(0,0,0,0.06); margin-bottom: 24px; }
        .table-section h2 { font-size: 1.15em; margin-bottom: 14px; color: #333; }
        table { width: 100%; border-collapse: collapse; }
        th { background: #f5f6fa; text-align: left; padding: 12px 14px; font-weight: 600; font-size: 0.9em; color: #555; border-bottom: 2px solid #e8eaf0; }
        td { padding: 14px; border-bottom: 1px solid #f0f1f5; vertical-align: middle; }
        tr:hover td { background: #f9f9ff; }
        .state-badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.82em; font-weight: 600; color: #fff; }
        .assignee-cell { display: flex; align-items: center; gap: 10px; }
        .avatar { width: 30px; height: 30px; border-radius: 50%; background: #ddd; object-fit: cover; }
        .avatar-placeholder { width: 30px; height: 30px; border-radius: 50%; background: linear-gradient(135deg,#667eea,#764ba2); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 0.75em; font-weight: 700; flex-shrink: 0; }
        .story-id { color: #667eea; font-weight: 600; }

        /* ── Assignee Summary ──────────────────────────── */
        .assignee-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
        .assignee-card { background: #f9f9ff; border-radius: 10px; padding: 14px 18px; display: flex; justify-content: space-between; align-items: center; border: 1px solid #ece8ff; }
        .assignee-card .name { font-weight: 500; }
        .assignee-card .count { background: linear-gradient(135deg,#667eea,#764ba2); color: #fff; border-radius: 20px; padding: 2px 12px; font-weight: 700; font-size: 0.95em; }

        .footer { text-align: center; color: #aaa; font-size: 0.85em; padding: 20px 0 32px; }

        @media print {
            body { background: #fff; }
            .header { padding: 20px 0; }
            .container { margin-top: 0; }
        }
        @media (max-width: 600px) {
            .header h1 { font-size: 1.4em; }
            .summary-row { grid-template-columns: 1fr 1fr; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Sprint {{ sprint.name }}</h1>
        <div class="subtitle">{{ sprint.path }}</div>
        {% if sprint.start and sprint.end %}
        <div class="sprint-dates">{{ sprint.start[:10] }}  &rarr;  {{ sprint.end[:10] }}</div>
        {% endif %}
    </div>

    <div class="container">
        <!-- Summary Cards -->
        <div class="summary-row">
            <div class="summary-card">
                <div class="num">{{ report.total }}</div>
                <div class="lbl">Total User Stories</div>
            </div>
            {% for sp in report.state_progress %}
            <div class="summary-card">
                <div class="num" style="background:{{ sp.color }};-webkit-background-clip:text;-webkit-text-fill-color:transparent;">{{ sp.count }}</div>
                <div class="lbl">{{ sp.state }}</div>
            </div>
            {% endfor %}
        </div>

        <!-- Progress Bar -->
        <div class="progress-section">
            <h2>Sprint Progress</h2>
            <div class="progress-bar">
                {% for sp in report.state_progress %}
                <div class="progress-segment" style="width:{{ sp.percent }}%;background:{{ sp.color }};" data-label="{{ sp.state }}: {{ sp.count }} ({{ sp.percent }}%)"></div>
                {% endfor %}
            </div>
            <div class="progress-legend">
                {% for sp in report.state_progress %}
                <span class="progress-legend-item"><span class="legend-dot" style="background:{{ sp.color }}"></span>{{ sp.state }} ({{ sp.count }})</span>
                {% endfor %}
            </div>
        </div>

        <!-- User Stories Table -->
        <div class="table-section">
            <h2>User Stories</h2>
            <table>
                <thead>
                    <tr>
                        <th style="width:70px;">ID</th>
                        <th>Title</th>
                        <th style="width:160px;">Assigned To</th>
                        <th style="width:140px;">State</th>
                    </tr>
                </thead>
                <tbody>
                    {% for s in report.stories %}
                    <tr>
                        <td class="story-id">#{{ s.id }}</td>
                        <td>{{ s.title }}</td>
                        <td>
                            <div class="assignee-cell">
                                {% if s.avatar %}
                                <img class="avatar" src="{{ s.avatar }}" alt="">
                                {% else %}
                                <span class="avatar-placeholder">{{ s.assignee[:2]|upper }}</span>
                                {% endif %}
                                <span>{{ s.assignee }}</span>
                            </div>
                        </td>
                        <td><span class="state-badge" style="background:{{ s.state_color }}">{{ s.state }}</span></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <!-- Assignee Summary -->
        <div class="table-section">
            <h2>Team Allocation</h2>
            <div class="assignee-grid">
                {% for name, count in report.assignee_counts.items() %}
                <div class="assignee-card">
                    <span class="name">{{ name }}</span>
                    <span class="count">{{ count }}</span>
                </div>
                {% endfor %}
            </div>
        </div>
    </div>

    <div class="footer">Generated on {{ generated_at }} &bull; Azure DevOps Sprint Status Report</div>
</body>
</html>'''


def generate_report(auto_open=False):
    print("Fetching current sprint...")
    sprint = get_current_sprint()
    if not sprint:
        print("ERROR: No active sprint found.")
        sys.exit(1)

    print(f"Sprint: {sprint['name']}  ({sprint['path']})")

    print("Fetching user stories...")
    stories = get_user_stories(sprint['path'])
    print(f"Found {len(stories)} user stories.")

    report = build_report_data(sprint, stories)

    # Print quick summary to terminal
    print(f"\n{'='*60}")
    print(f"  SPRINT: {sprint['name']}")
    print(f"  STORIES: {report['total']}")
    print(f"{'='*60}")
    for sp in report['state_progress']:
        bar = '#' * int(sp['percent'] / 2)
        print(f"  {sp['state']:20s}  {sp['count']:3d}  ({sp['percent']:5.1f}%)  {bar}")
    print(f"{'='*60}")
    print(f"\n  {'Assignee':30s} Stories")
    print(f"  {'-'*40}")
    for name, count in report['assignee_counts'].items():
        print(f"  {name:30s} {count}")
    print()

    # Render HTML
    html = Template(HTML_TEMPLATE).render(
        sprint=sprint,
        report=report,
        generated_at=datetime.now().strftime('%Y-%m-%d %H:%M'),
    )

    filename = "sprint_status.html"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)

    filepath = os.path.abspath(filename)
    print(f"Report saved: {filepath}")

    if auto_open:
        webbrowser.open(f"file:///{filepath}")
        print("Opened in browser.")


if __name__ == "__main__":
    auto_open = "--open" in sys.argv
    generate_report(auto_open=auto_open)
