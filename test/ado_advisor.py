import requests
import sys
import os
import base64
import urllib.parse
from datetime import datetime
import re
from typing import Optional
from fpdf import FPDF
from io import BytesIO
from jinja2 import Template
import urllib3

# Domain knowledge from EPP_Portal_Business_Documentation.md — used to make
# generated test cases reflect the real Enterprise Payment Platform domain
# (portals, screens, roles, routes, API endpoints).
try:
    from domain_context import build_domain_context  # when run from /test
except ImportError:  # pragma: no cover  — when run from project root
    from test.domain_context import build_domain_context

# Historical-context lookup — finds and summarises prior User Stories /
# Test Cases in the same Area Path so generation can match house style
# and avoid duplicating existing coverage.
try:
    from history_context import build_history_context  # when run from /test
except ImportError:  # pragma: no cover
    from test.history_context import build_history_context

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Azure DevOps Advisor: Connects to ADO REST API, checks agent pool and pipeline capacity, and recommends improvements.
# ── Configuration loaded from environment variables ───────────────────────────
# Set these in PowerShell before running. See README.md for instructions.
ADO_ORG = os.environ.get("ADO_ORG")
ADO_PAT = os.environ.get("ADO_PAT")
ADO_PROJECT = os.environ.get("ADO_PROJECT")
ADO_USERNAME = os.environ.get("ADO_USERNAME", "")  # optional, usually empty for PAT auth
ADO_PASSWORD = os.environ.get("ADO_PASSWORD", "")  # optional

_missing = [n for n, v in (("ADO_ORG", ADO_ORG), ("ADO_PAT", ADO_PAT), ("ADO_PROJECT", ADO_PROJECT)) if not v]
if _missing:
    print(f"ERROR: Missing required environment variable(s): {', '.join(_missing)}")
    print("Set them in PowerShell before running. See README.md for instructions.")
    sys.exit(1)

ADO_API = f"https://dev.azure.com/{ADO_ORG}/_apis/"

# Helper for correct PAT encoding
b64_pat = base64.b64encode(f'{ADO_USERNAME}:{ADO_PAT}'.encode()).decode()
headers = {
    'Content-Type': 'application/json',
    'Authorization': f'Basic {b64_pat}'
}

def get_agent_pools():
    url = f"{ADO_API}distributedtask/pools?api-version=7.1-preview.1"
    resp = requests.get(url, headers=headers, verify=False)
    resp.raise_for_status()
    return resp.json()

def get_project_info():
    url = f"{ADO_API}projects/{ADO_PROJECT}?api-version=7.1-preview.4"
    resp = requests.get(url, headers=headers, verify=False)
    resp.raise_for_status()
    return resp.json()

def get_pipeline_stats():
    org = urllib.parse.quote(ADO_ORG)
    project = urllib.parse.quote(ADO_PROJECT)
    url = f"https://dev.azure.com/{org}/{project}/_apis/build/builds?api-version=7.1-preview.7"
    resp = requests.get(url, headers=headers, verify=False)
    resp.raise_for_status()
    return resp.json()

def parse_ado_datetime(dt_str):
    # Handles Azure DevOps datetime with variable microseconds
    match = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?Z", dt_str)
    if not match:
        raise ValueError(f"Unrecognized datetime format: {dt_str}")
    base = match.group(1)
    frac = match.group(2) or ".0"
    # Truncate or pad microseconds to 6 digits
    micro = frac[1:7].ljust(6, '0')
    return datetime.strptime(f"{base}.{micro}Z", "%Y-%m-%dT%H:%M:%S.%fZ")

def analyze_and_recommend(project_info, pools, builds):
    recommendations = []
    # Example: Check agent pool count
    if len(pools.get('value', [])) < 2:
        recommendations.append("Consider adding more agent pools for better parallelism and reliability.")
    # Example: Check pipeline activity
    if builds.get('count', 0) < 5:
        recommendations.append("Pipeline activity is low. Ensure regular CI/CD runs for fast feedback.")
    # Example: Check for recent builds
    if builds.get('value'):
        last_build = builds['value'][0]
        finish_time = last_build.get('finishTime')
        if finish_time:
            last_run = parse_ado_datetime(finish_time)
            days_since = (datetime.utcnow() - last_run).days
            if days_since > 7:
                recommendations.append(f"No builds in the last {days_since} days. Investigate pipeline health.")
    if not recommendations:
        recommendations.append("No major issues detected. Keep monitoring your DevOps metrics.")
    return recommendations

def get_current_iteration():
    org = urllib.parse.quote(ADO_ORG)
    project = urllib.parse.quote(ADO_PROJECT)
    url = f"https://dev.azure.com/{org}/{project}/_apis/work/teamsettings/iterations?$timeframe=current&api-version=7.1-preview.1"
    resp = requests.get(url, headers=headers, verify=False)
    resp.raise_for_status()
    iterations = resp.json().get('value', [])
    return iterations[0] if iterations else None

def get_user_stories(iteration_path):
    # Query all user stories in the current iteration
    wiql = {
        "query": f"SELECT [System.Id], [System.Title], [System.State], [System.AssignedTo] FROM WorkItems WHERE [System.WorkItemType] = 'User Story' AND [System.IterationPath] = '{iteration_path}' ORDER BY [System.Id]"
    }
    org = urllib.parse.quote(ADO_ORG)
    project = urllib.parse.quote(ADO_PROJECT)
    url = f"https://dev.azure.com/{org}/{project}/_apis/wit/wiql?api-version=7.1"
    resp = requests.post(url, headers=headers, json=wiql, verify=False)
    resp.raise_for_status()
    ids = [wi['id'] for wi in resp.json().get('workItems', [])]
    return get_work_items(ids)

def get_work_items(ids):
    if not ids:
        return []
    org = urllib.parse.quote(ADO_ORG)
    url = f"https://dev.azure.com/{org}/_apis/wit/workitemsbatch?api-version=7.1"
    resp = requests.post(url, headers=headers, json={"ids": ids, "fields": ["System.Id", "System.Title", "System.State", "System.AssignedTo"]}, verify=False)
    resp.raise_for_status()
    return resp.json().get('value', [])

def get_linked_items(work_item_id):
    org = urllib.parse.quote(ADO_ORG)
    url = f"https://dev.azure.com/{org}/_apis/wit/workitems/{work_item_id}?$expand=relations&api-version=7.1"
    try:
        resp = requests.get(url, headers=headers, verify=False)
        resp.raise_for_status()
        return resp.json().get('relations', [])
    except Exception as e:
        print(f"Warning: Could not fetch linked items for work item {work_item_id}: {e}")
        return []

def get_test_cases_for_story(story_id):
    # Find test cases linked to a user story
    links = get_linked_items(story_id)
    test_cases = [int(link['url'].split('/')[-1]) for link in links if link.get('attributes', {}).get('name') == 'Tested By']
    return get_work_items(test_cases)

def get_bugs_for_story(story_id):
    # Find bugs linked to a user story
    links = get_linked_items(story_id)
    bugs = [int(link['url'].split('/')[-1]) for link in links if link.get('attributes', {}).get('name') == 'Related' and 'Bug' in link.get('attributes', {}).get('comment', '')]
    return get_work_items(bugs)

def get_test_case_details(tc_id):
    org = urllib.parse.quote(ADO_ORG)
    url = f"https://dev.azure.com/{org}/_apis/wit/workitems/{tc_id}?api-version=7.1"
    try:
        resp = requests.get(url, headers=headers, verify=False)
        resp.raise_for_status()
        fields = resp.json().get('fields', {})
        return {
            'id': tc_id,
            'title': fields.get('System.Title', ''),
            'preconditions': fields.get('Microsoft.VSTS.TCM.Preconditions', ''),
            'steps': fields.get('Microsoft.VSTS.TCM.Steps', ''),
            'postconditions': fields.get('Custom.PostConditions', ''),
            'expected': fields.get('Microsoft.VSTS.TCM.ExpectedResult', ''),
            'assignee': fields.get('System.AssignedTo', {}).get('displayName', 'Unassigned'),
        }
    except Exception as e:
        print(f"Warning: Could not fetch details for test case {tc_id}: {e}")
        return {'id': tc_id, 'title': 'Unavailable', 'preconditions': '', 'steps': '', 'postconditions': '', 'expected': '', 'assignee': 'Unassigned'}

def generate_resource_report(user_stories):
    resource_allocation = {}
    for story in user_stories:
        assignee = story.get('fields', {}).get('System.AssignedTo', {}).get('displayName', 'Unassigned')
        resource_allocation.setdefault(assignee, {'stories': [], 'testcases': []})
        resource_allocation[assignee]['stories'].append(story)
        # Test cases
        tcs = get_test_cases_for_story(story['id'])
        for tc in tcs:
            tc_assignee = tc.get('fields', {}).get('System.AssignedTo', {}).get('displayName', 'Unassigned')
            resource_allocation.setdefault(tc_assignee, {'stories': [], 'testcases': []})
            resource_allocation[tc_assignee]['testcases'].append(tc)
    return resource_allocation

def export_sprint_report_pdf(user_stories, allocation, iteration):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, f"Sprint Report: {iteration['name']} ({iteration['path']})", ln=True)
    pdf.ln(5)
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 10, "User Stories:", ln=True)
    for story in user_stories:
        title = story['fields']['System.Title']
        state = story['fields']['System.State']
        assignee = story['fields'].get('System.AssignedTo', {}).get('displayName', 'Unassigned')
        pdf.multi_cell(0, 8, f"#{story['id']}: {title} [{state}] - Assigned to: {assignee}")
        tcs = get_test_cases_for_story(story['id'])
        bugs = get_bugs_for_story(story['id'])
        pdf.cell(0, 8, f"  Test Cases: {[tc['id'] for tc in tcs]}", ln=True)
        pdf.cell(0, 8, f"  Bugs: {[bug['id'] for bug in bugs]}", ln=True)
        pdf.ln(2)
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 10, "Resource-wise Allocation Report:", ln=True)
    for resource, items in allocation.items():
        pdf.ln(4)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(0, 10, f"Resource: {resource}", ln=True)
        pdf.set_font("Arial", size=10)
        pdf.cell(0, 8, f"  User Stories: {[s['id'] for s in items['stories']]}")
        pdf.cell(0, 8, f"  Test Cases: {[tc['id'] for tc in items['testcases']]}")
    pdf_file = f"sprint_report_{iteration['id']}.pdf"
    pdf.output(pdf_file)
    print(f"PDF report exported: {pdf_file}")

def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html).replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')

def export_sprint_report_html(user_stories, allocation, iteration):
    html_template = '''
    <html>
    <head>
        <title>Sprint Report</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://fonts.googleapis.com/css?family=Roboto:400,700&display=swap" rel="stylesheet">
        <style>
            body { font-family: 'Roboto', Arial, sans-serif; margin: 0; background: linear-gradient(135deg, #e3eafc 0%, #f4f6f8 100%); color: #222; }
            .container { max-width: 980px; margin: 40px auto; background: #fff; border-radius: 16px; box-shadow: 0 8px 32px rgba(60,80,180,0.10); padding: 38px 48px; }
            h1 { color: #2c3e50; font-size: 2.3em; margin-bottom: 0.3em; letter-spacing: -1px; }
            h2 { color: #2980b9; margin-top: 2.2em; margin-bottom: 1em; font-size: 1.5em; }
            .sprint-progress { background: linear-gradient(90deg, #e3f2fd 0%, #f5faff 100%); border-radius: 12px; padding: 22px 28px; margin-bottom: 30px; box-shadow: 0 2px 8px #e0e0e0; }
            .sprint-progress h3 { margin-top: 0; color: #1976d2; }
            .progress-bar-container { display: flex; align-items: center; gap: 18px; margin-bottom: 10px; }
            .progress-bar { flex: 1; height: 28px; background: #e0e7ef; border-radius: 14px; overflow: hidden; display: flex; }
            .progress-segment { height: 100%; transition: width 0.4s; }
            .progress-legend { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 8px; }
            .progress-legend-item { display: flex; align-items: center; gap: 6px; font-size: 1em; }
            .legend-dot { width: 16px; height: 16px; border-radius: 4px; display: inline-block; }
            .story, .resource { background: #f9fafb; border-radius: 10px; box-shadow: 0 2px 8px #e0e0e0; margin-bottom: 20px; padding: 20px 26px; transition: box-shadow 0.2s; }
            .story:hover, .resource:hover { box-shadow: 0 6px 24px #d0d8e8; }
            .story-title { font-weight: bold; color: #2980b9; font-size: 1.13em; margin-bottom: 6px; }
            .assignee-badge { display: inline-block; background: #ede7f6; color: #6a1b9a; border-radius: 14px; padding: 2px 12px; font-size: 0.97em; margin-left: 10px; vertical-align: middle; }
            .label { font-weight: bold; color: #555; }
            ul { margin: 0 0 0 20px; padding-left: 18px; }
            .meta { margin-bottom: 8px; }
            .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; }
            .chip { background: #e3f2fd; color: #1565c0; border-radius: 16px; padding: 2px 12px; font-size: 0.95em; display: inline-block; }
            .charts { display: flex; gap: 40px; margin-bottom: 30px; justify-content: center; flex-wrap: wrap; }
            .pie-chart {
                width: 170px; height: 170px; border-radius: 50%; position: relative; margin: 0 auto 12px auto;
            }
            .pie-legend { display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }
            .pie-legend span { display: flex; align-items: center; gap: 8px; font-size: 0.98em; }
            .legend-color { width: 16px; height: 16px; border-radius: 3px; display: inline-block; }
            .dropdown { margin-top: 14px; }
            .dropdown-btn { background: linear-gradient(90deg, #42a5f5 0%, #1976d2 100%); color: #fff; border: none; border-radius: 8px; padding: 8px 20px; font-size: 1em; cursor: pointer; margin-bottom: 6px; transition: background 0.2s, box-shadow 0.2s; box-shadow: 0 2px 8px #b3d4fc; }
            .dropdown-btn:hover { background: linear-gradient(90deg, #1976d2 0%, #1565c0 100%); box-shadow: 0 4px 16px #90caf9; }
            .dropdown-content { display: none; background: #f5faff; border: 1px solid #e0e0e0; border-radius: 10px; box-shadow: 0 4px 16px #e0e0e0; padding: 20px 24px; margin-top: 8px; }
            .dropdown.open .dropdown-content { display: block; }
            .tc-card { background: #fff; border-radius: 10px; box-shadow: 0 2px 8px #e3eafc; padding: 16px 20px; margin-bottom: 16px; border-left: 4px solid #42a5f5; }
            .tc-title { font-weight: bold; color: #1565c0; margin-bottom: 6px; font-size: 1.08em; display: flex; align-items: center; gap: 10px; }
            .tc-assignee { background: #fffde7; color: #f9a825; border-radius: 12px; padding: 2px 10px; font-size: 0.93em; margin-left: 8px; }
            .tc-section { margin-bottom: 10px; background: #f5faff; border-radius: 6px; padding: 10px 14px; white-space: pre-line; font-size: 1em; }
            .tc-section ul { margin: 0; padding-left: 22px; }
            .tc-section li { margin-bottom: 4px; }
            .tc-label { color: #888; font-size: 0.97em; display: block; margin-bottom: 2px; font-weight: 600; }
            hr.tc-divider { border: none; border-top: 1px dashed #d0d8e8; margin: 18px 0 14px 0; }
            /* Suggested Test Cases Styles */
            .suggested-btn { background: linear-gradient(90deg, #ff9800 0%, #f57c00 100%); box-shadow: 0 2px 8px #ffe0b2; }
            .suggested-btn:hover { background: linear-gradient(90deg, #f57c00 0%, #e65100 100%); box-shadow: 0 4px 16px #ffcc80; }
            .suggested-content { background: linear-gradient(135deg, #fff8e1 0%, #fff3e0 100%); border: 1px solid #ffe0b2; }
            .suggested-header { background: #fff3e0; color: #e65100; font-weight: bold; padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; font-size: 1.02em; border-left: 4px solid #ff9800; }
            .suggested-tc-card { background: #fffde7; border-left: 4px solid #ffa726; }
            .suggested-tc-title { color: #e65100; }
            .no-tc-warning { background: #fff3e0; color: #e65100; padding: 10px 16px; border-radius: 8px; margin-top: 10px; font-weight: 500; border-left: 4px solid #ff9800; }
            /* Stories without test cases section */
            .stories-without-tc { background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%); border-radius: 12px; padding: 22px 28px; margin-bottom: 30px; box-shadow: 0 2px 8px #ffe0b2; }
            .stories-without-tc h3 { margin-top: 0; color: #e65100; }
            .stories-without-tc-count { font-size: 2em; font-weight: bold; color: #ff6f00; }
        </style>
        <script>
        function toggleDropdown(id) {
            var el = document.getElementById(id);
            if (el.classList.contains('open')) {
                el.classList.remove('open');
            } else {
                el.classList.add('open');
            }
        }
        </script>
    </head>
    <body>
        <div class="container">
        <h1>Sprint Report: {{ iteration.name }} <span style="font-size:0.7em;color:#888">({{ iteration.path }})</span></h1>
        <!-- Sprint Progress Section -->
        <div class="sprint-progress">
            <h3>Sprint Progress by User Story State</h3>
            <div class="progress-bar-container">
                <div class="progress-bar">
                    {% for state in state_progress %}
                    <div class="progress-segment" style="width:{{ state['percent'] }}%;background:{{ state['color'] }};"></div>
                    {% endfor %}
                </div>
                <span style="font-size:1.1em;font-weight:bold;">{{ total_stories }} stories</span>
            </div>
            <div class="progress-legend">
                {% for state in state_progress %}
                <span class="progress-legend-item"><span class="legend-dot" style="background:{{ state['color'] }}"></span>{{ state['state'] }}: {{ state['count'] }} ({{ state['percent']|round(1) }}%)</span>
                {% endfor %}
            </div>
        </div>
        <!-- Stories Without Test Cases Summary -->
        <div class="stories-without-tc">
            <h3>⚠️ User Stories Without Test Cases</h3>
            <div style="display:flex;align-items:center;gap:20px;">
                <span class="stories-without-tc-count">{{ stories_without_tc_count }}</span>
                <span style="font-size:1.1em;">out of {{ total_stories }} user stories have no test cases</span>
            </div>
            <div style="margin-top:12px;">
                {% if stories_without_tc %}
                <span class="label">Stories needing test cases:</span>
                <span class="chips" style="margin-top:8px;">
                    {% for sid in stories_without_tc %}<span class="chip" style="background:#fff3e0;color:#e65100;">#{{ sid }}</span>{% endfor %}
                </span>
                {% else %}
                <span style="color:#43a047;font-weight:bold;">✅ All user stories have test cases!</span>
                {% endif %}
            </div>
        </div>
        <div class="charts">
            <div>
                <div class="pie-chart" style="background: conic-gradient({% for d in story_chart_data %}{{ d['color'] }} 0 {{ d['percent'] }}%, {% endfor %}#eee 0 100%)"></div>
                <div class="pie-legend">
                    <b>User Story Allocation</b>
                    {% for d in story_chart_data %}
                    <span><span class="legend-color" style="background:{{ d['color'] }}"></span>{{ d['name'] }} ({{ d['count'] }})</span>
                    {% endfor %}
                </div>
            </div>
            <div>
                <div class="pie-chart" style="background: conic-gradient({% for d in tc_chart_data %}{{ d['color'] }} 0 {{ d['percent'] }}%, {% endfor %}#eee 0 100%)"></div>
                <div class="pie-legend">
                    <b>Test Case Allocation</b>
                    {% for d in tc_chart_data %}
                    <span><span class="legend-color" style="background:{{ d['color'] }}"></span>{{ d['name'] }} ({{ d['count'] }})</span>
                    {% endfor %}
                </div>
            </div>
        </div>
        <h2>User Stories</h2>
        {% for story in user_stories %}
        <div class="story">
            <div class="story-title">#{{ story['id'] }}: {{ story['fields']['System.Title'] }}
                <span class="assignee-badge">👤 {{ story['fields'].get('System.AssignedTo', {}).get('displayName', 'Unassigned') }}</span>
            </div>
            <div class="meta"><span class="label">State:</span> {{ story['fields']['System.State'] }}</div>
            <div><span class="label">Test Cases:</span>
                <span class="chips">{% for tc in story['test_cases'] %}<span class="chip">{{ tc['id'] }}</span>{% endfor %}{% if not story['test_cases'] %}<span style="color:#aaa">None</span>{% endif %}</span>
            </div>
            <div><span class="label">Bugs:</span>
                <span class="chips">{% for bug in story['bugs'] %}<span class="chip" style="background:#ffebee;color:#c62828">{{ bug }}</span>{% endfor %}{% if not story['bugs'] %}<span style="color:#aaa">None</span>{% endif %}</span>
            </div>
            {% if story['test_cases'] %}
            <div class="dropdown" id="dropdown-{{ story['id'] }}">
                <button class="dropdown-btn" onclick="toggleDropdown('dropdown-{{ story['id'] }}')">📝 Show/Hide Test Case Details</button>
                <div class="dropdown-content">
                    {% for tc in story['test_cases'] %}
                    <div class="tc-card">
                        <div class="tc-title">
                            <span>🧪 Test Case #{{ tc['id'] }}: {{ tc['title'] }}</span>
                            <span class="tc-assignee">👤 {{ tc['assignee'] }}</span>
                        </div>
                        <div class="tc-section"><span class="tc-label">Preconditions:</span>{{ tc['preconditions'] if tc['preconditions'] else '<span style="color:#bbb">N/A</span>' }}</div>
                        <div class="tc-section"><span class="tc-label">Steps:</span>{{ tc['steps']|safe if tc['steps'] else '<span style="color:#bbb">N/A</span>' }}</div>
                        <div class="tc-section"><span class="tc-label">Expected Output:</span>{{ tc['expected'] if tc['expected'] else '<span style="color:#bbb">N/A</span>' }}</div>
                        <div class="tc-section"><span class="tc-label">Postconditions:</span>{{ tc['postconditions'] if tc['postconditions'] else '<span style="color:#bbb">N/A</span>' }}</div>
                    </div>
                    {% if not loop.last %}<hr class="tc-divider">{% endif %}
                    {% endfor %}
                </div>
            </div>
            {% endif %}
            {% if story['suggested_test_cases'] %}
            <div class="dropdown" id="suggested-dropdown-{{ story['id'] }}">
                <button class="dropdown-btn suggested-btn" onclick="toggleDropdown('suggested-dropdown-{{ story['id'] }}')">💡 Show/Hide Suggested Test Cases ({{ story['suggested_test_cases']|length }})</button>
                <div class="dropdown-content suggested-content">
                    <div class="suggested-header">⚠️ No test cases found for this user story. Here are AI-suggested test cases:</div>
                    {% for stc in story['suggested_test_cases'] %}
                    <div class="tc-card suggested-tc-card">
                        <div class="tc-title suggested-tc-title">
                            <span>💡 Suggested: {{ stc['title'] }}</span>
                        </div>
                        <div class="tc-section"><span class="tc-label">Preconditions:</span>{{ stc['preconditions'] }}</div>
                        <div class="tc-section"><span class="tc-label">Steps:</span>{{ stc['steps']|safe }}</div>
                        <div class="tc-section"><span class="tc-label">Expected Output:</span>{{ stc['expected'] }}</div>
                        <div class="tc-section"><span class="tc-label">Postconditions:</span>{{ stc['postconditions'] }}</div>
                    </div>
                    {% if not loop.last %}<hr class="tc-divider">{% endif %}
                    {% endfor %}
                </div>
            </div>
            {% endif %}
        </div>
        {% endfor %}
        <h2>Resource-wise Allocation</h2>
        {% for resource, items in allocation.items() %}
        <div class="resource">
            <div class="label">Resource:</div> <span style="font-size:1.1em;">{{ resource }}</span><br>
            <div><span class="label">User Stories:</span>
                <span class="chips">{% for s in items['stories'] %}<span class="chip">{{ s }}</span>{% endfor %}{% if not items['stories'] %}<span style="color:#aaa">None</span>{% endif %}</span>
            </div>
            <div><span class="label">Test Cases:</span>
                <span class="chips">{% for tc in items['testcases'] %}<span class="chip">{{ tc }}</span>{% endfor %}{% if not items['testcases'] %}<span style="color:#aaa">None</span>{% endif %}</span>
            </div>
        </div>
        {% endfor %}
        </div>
    </body>
    </html>
    '''
    # Prepare data for charts
    story_counts = {k: len(v['stories']) for k, v in allocation.items()}
    tc_counts = {k: len(v['testcases']) for k, v in allocation.items()}
    total_stories = sum(story_counts.values())
    total_tcs = sum(tc_counts.values())
    story_chart_data = [
        {'name': k, 'count': v, 'percent': (v / total_stories * 100) if total_stories else 0}
        for k, v in story_counts.items()
    ]
    tc_chart_data = [
        {'name': k, 'count': v, 'percent': (v / total_tcs * 100) if total_tcs else 0}
        for k, v in tc_counts.items()
    ]
    # Assign colors for charts
    palette = ['#42a5f5', '#66bb6a', '#ffa726', '#ab47bc', '#ef5350', '#26a69a', '#d4e157', '#8d6e63', '#789262', '#ec407a']
    for i, d in enumerate(story_chart_data):
        d['color'] = palette[i % len(palette)]
    for i, d in enumerate(tc_chart_data):
        d['color'] = palette[i % len(palette)]
    # --- Sprint progress by user story state ---
    from collections import Counter
    state_counts = Counter(s['fields']['System.State'] for s in user_stories)
    state_palette = ['#43a047', '#1e88e5', '#fdd835', '#fb8c00', '#e53935', '#8e24aa', '#00acc1', '#6d4c41']
    state_progress = []
    for i, (state, count) in enumerate(state_counts.items()):
        state_progress.append({
            'state': state,
            'count': count,
            'percent': (count / total_stories * 100) if total_stories else 0,
            'color': state_palette[i % len(state_palette)]
        })
    # Prepare data for template
    stories_without_tc = []
    for story in user_stories:
        tc_ids = [tc['id'] for tc in get_test_cases_for_story(story['id'])]
        story['test_cases'] = []
        for tc_id in tc_ids:
            tc = get_test_case_details(tc_id)
            tc['preconditions'] = clean_html(tc['preconditions'])
            tc['steps'] = clean_html(tc['steps'])
            tc['expected'] = clean_html(tc['expected'])
            tc['postconditions'] = clean_html(tc['postconditions'])
            # Beautify steps: add bullet points for each step if possible
            steps = tc['steps'].strip().split('\n')
            if len(steps) > 1:
                tc['steps'] = '<ul>' + ''.join(f'<li>{step.strip()}</li>' for step in steps if step.strip()) + '</ul>'
            story['test_cases'].append(tc)
        story['bugs'] = [bug['id'] for bug in get_bugs_for_story(story['id'])]
        # Generate suggested test cases if no test cases exist
        if not story['test_cases']:
            stories_without_tc.append(story['id'])
            suggested = generate_suggested_test_cases(story)
            for stc in suggested:
                # Format steps as bullet list
                if isinstance(stc['steps'], list):
                    stc['steps'] = '<ul>' + ''.join(f'<li>{step}</li>' for step in stc['steps']) + '</ul>'
            story['suggested_test_cases'] = suggested
        else:
            story['suggested_test_cases'] = []
    stories_without_tc_count = len(stories_without_tc)
    for resource, items in allocation.items():
        items['stories'] = [s['id'] for s in items['stories']]
        items['testcases'] = [tc['id'] for tc in items['testcases']]
    from jinja2 import Template
    html = Template(html_template).render(
        iteration=iteration,
        user_stories=user_stories,
        allocation=allocation,
        story_chart_data=story_chart_data,
        tc_chart_data=tc_chart_data,
        state_progress=state_progress,
        total_stories=total_stories,
        stories_without_tc=stories_without_tc,
        stories_without_tc_count=stories_without_tc_count
    )
    with open("sprint_report.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("\nHTML report generated: sprint_report.html")

def print_sprint_report(export_pdf=False, export_html=False):
    iteration = get_current_iteration()
    if not iteration:
        print("No active sprint found.")
        return
    print(f"\nCurrent Sprint: {iteration['name']} ({iteration['path']})")
    user_stories = get_user_stories(iteration['path'])
    for story in user_stories:
        print(f"\nUser Story #{story['id']}: {story['fields']['System.Title']} [{story['fields']['System.State']}] - Assigned to: {story['fields'].get('System.AssignedTo', {}).get('displayName', 'Unassigned')}")
        tcs = get_test_cases_for_story(story['id'])
        print(f"  Test Cases: {[tc['id'] for tc in tcs]}")
        bugs = get_bugs_for_story(story['id'])
        print(f"  Bugs: {[bug['id'] for bug in bugs]}")
    # Resource allocation report
    allocation = generate_resource_report(user_stories)
    print("\n--- Resource-wise Allocation Report ---")
    for resource, items in allocation.items():
        print(f"\nResource: {resource}")
        print(f"  User Stories: {[s['id'] for s in items['stories']]}")
        print(f"  Test Cases: {[tc['id'] for tc in items['testcases']]}")
    if export_pdf:
        export_sprint_report_pdf(user_stories, allocation, iteration)
    if export_html:
        export_sprint_report_html(user_stories, allocation, iteration)

def generate_suggested_test_cases(story):
    """
    Generate suggested test cases for a user story using Rules.md logic.
    Wraps the rules-based engine for use in sprint reports.
    """
    work_item = get_work_item_full_details(story['id'])
    if not work_item:
        return []
    test_cases, _, _, _ = generate_test_cases_from_acceptance_criteria(work_item)
    # Convert to the format expected by sprint report
    suggestions = []
    for tc in test_cases:
        suggestions.append({
            'title': tc['title'],
            'preconditions': tc.get('preconditions', ''),
            'steps': tc['steps'] if isinstance(tc['steps'], list) else [tc['steps']],
            'expected': tc.get('expected', ''),
            'postconditions': tc.get('postconditions', 'N/A'),
        })
    return suggestions

def get_work_item_full_details(work_item_id):
    """Fetch full details of a work item including description and acceptance criteria."""
    org = urllib.parse.quote(ADO_ORG)
    url = f"https://dev.azure.com/{org}/_apis/wit/workitems/{work_item_id}?api-version=7.1"
    try:
        resp = requests.get(url, headers=headers, verify=False)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching work item {work_item_id}: {e}")
        return None

def generate_test_cases_from_acceptance_criteria(work_item, history=None):
    """
    Rules-based test case generator. Strictly follows Rules.md.
    Returns (test_cases_list, ac_clean, desc_clean, title).

    Each test case dict contains all RULE GEN 01 mandatory attributes:
      title, objective, preconditions, steps, expected (per step list),
      overall_expected, priority (1-4), test_type, test_category,
      review_status, automation_state, area_path, iteration_path,
      application_name, application_module, ac_ref

    Optional ``history`` parameter: dict returned by
    ``history_context.build_history_context`` — supplies prior-art
    test case titles / keywords from neighbouring User Stories in the
    same Area Path so the generator can suggest extra "neighbourhood"
    coverage that the team has historically tested.
    """
    if not work_item:
        return [], '', '', ''

    fields = work_item.get('fields', {})
    title = fields.get('System.Title', '')
    description = fields.get('System.Description', '')
    acceptance_criteria = fields.get('Microsoft.VSTS.Common.AcceptanceCriteria', '')
    area_path = fields.get('System.AreaPath', '')
    iteration_path = fields.get('System.IterationPath', '')

    ac_clean = clean_html(acceptance_criteria) if acceptance_criteria else ''
    desc_clean = clean_html(description) if description else ''
    combined = (title + ' ' + desc_clean + ' ' + ac_clean).lower()

    ac_blocks = _parse_ac_blocks(ac_clean)

    # ── EPP DOMAIN CONTEXT ─────────────────────────────────────────────────
    # Map this story to a concrete portal / screen / role using the business
    # documentation. This lets us generate domain-aware test cases instead of
    # generic "User does X" boilerplate.
    domain = build_domain_context(title, desc_clean, ac_clean)

    # ── Detect story characteristics for conditional rule application ─────
    has_roles = any(kw in combined for kw in [
        'admin', 'role', 'permission', 'manager', 'approver', 'unauthorized', 'authoriz'
    ])
    has_data_input = any(kw in combined for kw in [
        'input', 'enter', 'form', 'field', 'submit', 'upload', 'fill', 'dropdown'
    ])
    has_ui = any(kw in combined for kw in [
        'button', 'click', 'screen', 'page', 'modal', 'dialog', 'menu', 'tab',
        'display', 'ui', 'dropdown', 'tooltip', 'grid', 'table', 'view'
    ])
    has_api = any(kw in combined for kw in [
        'api', 'endpoint', 'webhook', 'service', 'request', 'response', 'http'
    ])

    # ── Roles ──────────────────────────────────────────────────────────────
    # Prefer roles identified from the EPP domain catalogue; fall back to
    # generic keyword extraction only when nothing matched.
    if domain.get('roles'):
        roles_found = list(domain['roles'])
        has_roles = True
    else:
        role_keywords = {
            'admin': 'Admin', 'administrator': 'Admin', 'manager': 'Manager',
            'approver': 'Approver', 'reviewer': 'Reviewer', 'operator': 'Operator',
            'editor': 'Editor', 'viewer': 'Viewer'
        }
        roles_found = []
        for kw, label in role_keywords.items():
            if kw in combined and label not in roles_found:
                roles_found.append(label)
        if not roles_found:
            roles_found = ['User']

    # Make sure the "primary" (action-driving) role is first in the list, so
    # downstream code that uses roles_found[0] picks the most realistic actor.
    primary_role = domain.get('primary_role')
    if primary_role and primary_role in roles_found:
        roles_found = [primary_role] + [r for r in roles_found if r != primary_role]

    # Detect best-fit Application Module from title/description (fall back to
    # the portal-resolved feature label when nothing else fits).
    module = _infer_application_module(combined)
    if (not module or module == 'EPP General') and domain.get('feature'):
        module = domain['feature']

    # Default category derivation
    default_category = 'API' if has_api else 'Functional'
    default_test_type = 'Smoke & Regression'

    # Common defaults applied to every test case (RULE GEN 01)
    base_defaults = {
        'review_status': 'NO',
        'automation_state': 'Non-Automatable',
        'area_path': area_path,
        'iteration_path': iteration_path,
        'application_name': 'EPP',
        'application_module': module,
        # EPP area tag (AP_Bulk / Resware_OB / Escrow_CEA / Escrow_IB /
        # Escrow_OB / STEPS_OB / AP_WD / AP_Portal) — surfaced as an ADO
        # tag at publish time. Empty string when the story doesn't match
        # any defined area.
        'epp_area': domain.get('epp_area') or '',
    }

    test_cases = []

    def add_tc(tc):
        """Merge defaults and append. Enforces RULE GEN 02 title format."""
        for k, v in base_defaults.items():
            tc.setdefault(k, v)
        tc['title'] = _normalize_title(tc['title'])
        # Ensure expected is a list aligned to steps for "expected per step" (RULE GEN 01.5)
        steps = tc.get('steps', [])
        exps = tc.get('expected', [])
        if isinstance(exps, str):
            exps = [''] * (len(steps) - 1) + [exps] if steps else [exps]
        if len(exps) < len(steps):
            exps += [''] * (len(steps) - len(exps))
        tc['expected'] = exps
        test_cases.append(tc)

    # Prefer the EPP-domain feature label (e.g., "Payment Monitoring",
    # "Bulk Payment Import") over a noisy substring of the story title.
    feature_label = domain.get('feature') or _short_feature(title)

    # ══════════════════════════════════════════════════════════════════════
    # RULE GEN 03: 1 test case per AC (the AC-coverage minimum)
    # ══════════════════════════════════════════════════════════════════════
    for i, ac_block in enumerate(ac_blocks, 1):
        given_match = re.search(r'GIVEN\s+(.+?)(?=WHEN|THEN|$)', ac_block, re.IGNORECASE | re.DOTALL)
        when_match = re.search(r'WHEN\s+(.+?)(?=THEN|$)', ac_block, re.IGNORECASE | re.DOTALL)
        then_match = re.search(r'THEN\s+(.+?)$', ac_block, re.IGNORECASE | re.DOTALL)

        given_text = _clean_clause(given_match.group(1)) if given_match else ''
        when_text = _clean_clause(when_match.group(1)) if when_match else ''
        then_text = _clean_clause(then_match.group(1)) if then_match else ''

        ac_summary = _clean_clause(ac_block[:200])
        if ac_summary.upper().startswith('AC'):
            ac_summary = ac_summary.split(':', 1)[-1].strip() if ':' in ac_summary else ac_summary[4:].strip()

        # ── Build steps & per-step expected — follow Rules.md sample format
        # (clear imperative actions, no "Ensure/Perform/Validate" prefixes).
        actor_label = roles_found[0] if has_roles else 'User'
        portal_label = domain.get('portal') or 'EPP'
        route_label = domain.get('route')

        steps = []
        exps = []

        # Step 1 — Login (always present, gives a concrete starting point)
        steps.append(f"Log in to the {portal_label} as a {actor_label}")
        exps.append(f"{actor_label} is signed in and lands on the role-based default page")

        # Step 2 — Navigate to the feature (use the real route if we know it)
        if route_label:
            steps.append(f"Navigate to {feature_label} ({route_label})")
            exps.append(f"The {feature_label} screen at {route_label} is displayed")
        else:
            steps.append(f"Navigate to the {feature_label} screen / functionality")
            exps.append(f"{feature_label} screen is displayed")

        # Step 3 — Set up preconditions from GIVEN (only if non-trivial)
        if given_text and len(given_text) > 5:
            steps.append(_imperative(given_text))
            exps.append("Precondition state is established successfully")

        # Step 4 — Trigger the action from WHEN (or fall back to AC summary)
        action_text = when_text or ac_summary
        if action_text:
            steps.append(_imperative(action_text))
            exps.append("Action is executed without errors")

        # Step 5 — Validate the outcome from THEN (do NOT mention "AC" in steps)
        if then_text:
            steps.append("Verify the system response against the expected business outcome")
            exps.append(then_text)
        else:
            steps.append("Verify the resulting behavior matches the objective of this test")
            exps.append("System behavior matches the objective stated in the test case")

        # Step 6 (optional) — If the screen has known API hints, validate them
        api_hints = domain.get('api_hints') or []
        if api_hints and (has_api or 'api' in combined or 'endpoint' in combined):
            steps.append("Verify the underlying API call and response")
            exps.append(" / ".join(api_hints[:2]))

        # ── RULE GEN 02 — clean, business-friendly title per AC ──────────
        condition = _build_condition_phrase(then_text or when_text or ac_summary)
        actor = roles_found[0] if has_roles else 'system'
        ac_title = f"{feature_label} {condition}" if condition else feature_label

        # ── Domain-aware preconditions: prefer the GIVEN clause from the
        #    AC, but always layer in the portal/role/route context so the
        #    tester can reproduce the exact starting state.
        precond_lines: list = []
        if domain.get('preconditions'):
            precond_lines.extend(domain['preconditions'])
        if given_text and given_text.strip():
            precond_lines.append(given_text.strip())
        if not precond_lines:
            precond_lines.append(
                f"{actor.capitalize()} is signed in to EPP with the appropriate role"
            )
        # Deduplicate while preserving order
        seen_pc, dedup_pc = set(), []
        for line in precond_lines:
            key = line.lower()
            if key not in seen_pc:
                seen_pc.add(key)
                dedup_pc.append(line)
        preconditions_text = "\n".join(f"• {line}" for line in dedup_pc)

        add_tc({
            'title': ac_title,
            'objective': _build_objective(feature_label, given_text, when_text,
                                          then_text, ac_summary, story_title=title),
            'preconditions': preconditions_text,
            'steps': steps,
            'expected': exps,
            'overall_expected': then_text if then_text else "The requirement is fully satisfied",
            'priority': 2,
            'test_type': default_test_type,
            'test_category': default_category,
            'ac_ref': f'AC{i}',  # internal mapping only — not shown anywhere user-visible
        })

    # ══════════════════════════════════════════════════════════════════════
    # RULE GEN 03: At least 1 Happy Path (positive) for authorized role
    # ══════════════════════════════════════════════════════════════════════
    if not any(tc['test_category'] == 'Functional' or tc['test_category'] == 'API' for tc in test_cases):
        actor = roles_found[0]
        portal_label = domain.get('portal') or 'EPP'
        route_label = domain.get('route')
        nav_step = (f"Navigate to {feature_label} ({route_label})"
                    if route_label else f"Navigate to the {feature_label} screen")
        nav_exp = (f"The {feature_label} screen at {route_label} is displayed"
                   if route_label else f"{feature_label} screen is displayed")
        add_tc({
            'title': f"{feature_label} works end-to-end with valid inputs",
            'objective': (f"Verify that the {feature_label} feature completes its primary "
                          f"end-to-end flow successfully when an authorised {actor} provides "
                          f"valid inputs."),
            'preconditions': (
                f"• User is signed in to the {portal_label} with the '{actor}' role\n"
                + (f"• User can reach the route {route_label}\n" if route_label else "")
                + "• All upstream services are available"
            ),
            'steps': [
                f"Log in to the {portal_label} as a {actor}",
                nav_step,
                "Provide all required inputs with valid data",
                "Trigger the primary action (e.g., Submit / Save / Send)",
                "Observe the system response and confirmation feedback",
            ],
            'expected': [
                f"{actor} is signed in and lands on the role-based default page",
                nav_exp,
                "Inputs are accepted without validation errors",
                "Action is processed successfully by the system",
                "Success message / confirmation is displayed and data is persisted",
            ],
            'overall_expected': "Happy path completes successfully and data is persisted",
            'priority': 1,
            'test_type': 'Smoke',
            'test_category': default_category,
            'ac_ref': 'Happy Path',
        })

    # ══════════════════════════════════════════════════════════════════════
    # RULE GEN 03: At least 1 Negative / Boundary / Unauthorized
    # ══════════════════════════════════════════════════════════════════════
    if not any(tc['test_category'] == 'Negative' for tc in test_cases):
        if has_roles:
            portal_label = domain.get('portal') or 'EPP'
            route_label = domain.get('route')
            wrong_role = domain.get('negative_role') or 'a role outside the allowed list'
            primary = domain.get('primary_role') or roles_found[0]
            nav_step = (f"Attempt to navigate to {feature_label} ({route_label})"
                        if route_label else f"Attempt to navigate to the {feature_label} screen")
            add_tc({
                'title': f"Unauthorized user is blocked from {feature_label}",
                'objective': (f"Verify that a user with the '{wrong_role}' role (not in the allowed "
                              f"list for {feature_label}) is prevented from accessing or performing "
                              f"the action, and that no data is altered."),
                'preconditions': (
                    f"• A user account exists with ONLY the '{wrong_role}' role\n"
                    f"• The {feature_label} screen is restricted to: {', '.join(roles_found)}"
                ),
                'steps': [
                    f"Log in to the {portal_label} as a '{wrong_role}'",
                    nav_step,
                    "Attempt to perform the primary action (or call the underlying API directly)",
                    "Observe the system response",
                ],
                'expected': [
                    f"'{wrong_role}' is signed in but is redirected to access-denied or their default page",
                    "Screen access is denied OR the action control is hidden / disabled",
                    "API returns HTTP 401 / 403 and no state changes occur",
                    "An appropriate access-denied message is shown to the user",
                ],
                'overall_expected': (
                    f"Only users with one of [{', '.join(roles_found)}] can use {feature_label}; "
                    f"'{wrong_role}' is blocked end-to-end."
                ),
                'priority': 1,
                'test_type': 'Regression',
                'test_category': 'Negative',
                'ac_ref': 'Security',
            })
        else:
            actor = roles_found[0]
            portal_label = domain.get('portal') or 'EPP'
            add_tc({
                'title': f"System rejects invalid inputs for {feature_label}",
                'objective': (f"Verify that the {feature_label} feature rejects invalid, "
                              f"empty or out-of-range inputs gracefully and shows clear "
                              f"validation messages without saving any data."),
                'preconditions': f"{actor} is signed in to the {portal_label}",
                'steps': [
                    f"Log in to the {portal_label} as a {actor}",
                    f"Navigate to the {feature_label} screen",
                    "Submit invalid / out-of-range / empty inputs",
                    "Observe the validation behavior",
                ],
                'expected': [
                    f"{actor} is successfully signed in",
                    f"{feature_label} screen is displayed",
                    "Submission is blocked",
                    "A clear, user-friendly error message is shown next to the offending field",
                ],
                'overall_expected': "Invalid inputs are rejected gracefully and no data is saved",
                'priority': 2,
                'test_type': 'Regression',
                'test_category': 'Negative',
                'ac_ref': 'Negative',
            })

    # ══════════════════════════════════════════════════════════════════════
    # RULE COV 07: Role-Based Test Generation
    # ══════════════════════════════════════════════════════════════════════
    if has_roles and len(roles_found) > 1:
        for role in roles_found[:3]:
            add_tc({
                'title': f"{role} can perform {feature_label} per role permissions",
                'objective': f"Verify that the {feature_label} feature behaves correctly and applies the role-specific permissions defined for a {role}.",
                'preconditions': f"A user account with the {role} role exists",
                'steps': [
                    f"Log in to EPP as a {role}",
                    f"Navigate to the {feature_label} screen",
                    f"Perform the primary action available to a {role}",
                    "Verify the resulting state and any role-specific UI/behavior",
                ],
                'expected': [
                    f"{role} is successfully logged in",
                    f"{feature_label} screen is displayed",
                    "Action completes successfully",
                    f"Outcome matches the business rules defined for the {role} role",
                ],
                'overall_expected': f"Behavior is correct for the {role} role",
                'priority': 2,
                'test_type': 'Regression',
                'test_category': 'Functional',
                'ac_ref': f'Role: {role}',
            })

    # ══════════════════════════════════════════════════════════════════════
    # RULE COV 08 + RULE DATA 09: Data-Driven Coverage (only if data input)
    # ══════════════════════════════════════════════════════════════════════
    if has_data_input:
        actor = roles_found[0]
        data_variants = [
            ('valid data', 'Functional', 2,
             'Submission succeeds; data is saved',
             'Enter valid values in all required fields'),
            ('invalid data', 'Negative', 2,
             'Validation error is displayed; no data is saved',
             'Enter invalid values (wrong format, out-of-range) in the form'),
            ('empty/null inputs', 'Negative', 2,
             'Required-field validation errors are displayed',
             'Leave all required fields empty'),
            ('special characters', 'Functional', 3,
             'Special characters are handled / sanitized correctly',
             'Enter special characters (!@#$%^&*<>) in text fields'),
            ('maximum-length values', 'Functional', 3,
             'Boundary-length value is accepted and saved correctly',
             'Enter values at the maximum allowed length in each text field'),
            ('minimum-length values', 'Functional', 3,
             'Boundary-length value is accepted and saved correctly',
             'Enter values at the minimum allowed length in each text field'),
        ]
        for label, cat, prio, expected, action_step in data_variants:
            add_tc({
                'title': f"{feature_label} submission with {label}",
                'objective': f"Verify that the {feature_label} feature handles {label} correctly and produces the expected outcome without data corruption.",
                'preconditions': (f"{actor} is logged in; the data entry form is accessible. "
                                  f"Test data source: CSV (header + valid + invalid + boundary rows + comment column)"),
                'steps': [
                    f"Log in to EPP as a {actor}",
                    f"Navigate to the {feature_label} data entry form",
                    action_step,
                    "Click the Submit button",
                    "Observe the system response",
                ],
                'expected': [
                    f"{actor} is successfully logged in",
                    "Data entry form is displayed",
                    "Inputs are entered into the fields as specified",
                    "Submit action is processed",
                    expected,
                ],
                'overall_expected': expected,
                'priority': prio,
                'test_type': 'Regression',
                'test_category': cat,
                'ac_ref': f'Data: {label}',
            })

    # ══════════════════════════════════════════════════════════════════════
    # RULE FUNC 10: UI & Field Validation (only if UI mentioned)
    # ══════════════════════════════════════════════════════════════════════
    if has_ui:
        actor = roles_found[0]
        add_tc({
            'title': f"UI elements render correctly on {feature_label} screen",
            'objective': (f"Verify that all UI elements on the {feature_label} screen "
                          f"render with the correct visibility, enable/disable state, "
                          f"mandatory-field markers and default values per the design spec."),
            'preconditions': f"{actor} is logged in; the {feature_label} screen is accessible",
            'steps': [
                f"Log in to EPP as a {actor}",
                f"Navigate to the {feature_label} screen",
                "Verify each UI element (buttons, dropdowns, fields, labels) is visible and labeled correctly",
                "Verify the enable/disable state of each control matches the business rule for the current context",
                "Verify mandatory-field markers (e.g., red asterisk) are present on required fields",
                "Verify default values pre-populated in the fields are correct",
            ],
            'expected': [
                f"{actor} is successfully logged in",
                f"{feature_label} screen is displayed",
                "All UI elements are visible and labeled per design specification",
                "Enable/disable state matches business rules",
                "Mandatory markers are displayed on required fields",
                "Default values match the specification",
            ],
            'overall_expected': "All UI elements meet design specifications",
            'priority': 3,
            'test_type': 'Smoke & Regression',
            'test_category': 'Functional',
            'ac_ref': 'UI',
        })

    # ══════════════════════════════════════════════════════════════════════
    # EPP DOMAIN: Canonical workflow walkthrough (only if we matched a
    # known screen and have explicit workflow steps for it).
    # This adds genuine business-value coverage like "Retry a transmission-
    # failed payment from /payments/monitoring" instead of a generic step.
    # ══════════════════════════════════════════════════════════════════════
    if domain.get('workflow_steps') and domain.get('confidence', 0) >= 0.4:
        wf_actor = domain.get('primary_role') or roles_found[0]
        wf_portal = domain.get('portal') or 'EPP'
        wf_route = domain.get('route')
        wf_steps = [f"Log in to the {wf_portal} as a {wf_actor}"] \
                   + list(domain['workflow_steps'])
        wf_exps = [f"{wf_actor} is signed in and lands on the role-based default page"] \
                  + ["Step completes successfully" for _ in domain['workflow_steps']]
        # Replace the last expected with the most meaningful outcome
        if wf_exps:
            wf_exps[-1] = "Workflow completes end-to-end and the business outcome is achieved"
        api_hint = (" / ".join(domain['api_hints'][:2])
                    if domain.get('api_hints') else "")
        if api_hint:
            wf_steps.append("Verify the underlying API call(s) and response status")
            wf_exps.append(api_hint)

        add_tc({
            'title': f"{feature_label} canonical workflow as {wf_actor}",
            'objective': (f"Verify the canonical end-to-end workflow for {feature_label} on "
                          f"the {wf_portal}, performed by an authorised '{wf_actor}'."),
            'preconditions': (
                f"• User is signed in to the {wf_portal} with the '{wf_actor}' role\n"
                + (f"• User can reach the route {wf_route}\n" if wf_route else "")
                + "• All upstream services (Epp.Api, SharedServices.Api, providers) are healthy"
            ),
            'steps': wf_steps,
            'expected': wf_exps,
            'overall_expected': f"The {feature_label} workflow completes successfully end-to-end",
            'priority': 1,
            'test_type': 'Smoke & Regression',
            'test_category': 'Functional',
            'ac_ref': 'Workflow',
        })

    # ══════════════════════════════════════════════════════════════════════
    # HISTORICAL CONTEXT (targeted enrichment, not addition)
    # --------------------------------------------------------------------
    # Use prior-art from neighbouring User Stories in the same Area Path
    # to subtly ENRICH the test cases we already have — never to create
    # new ones, and never as boilerplate added to every TC.
    #
    # Rules of engagement (kept tight on purpose):
    #   • Only EPP-vocab keywords (history_context._DOMAIN_VOCAB) are
    #     considered — generic words like "screen" never make it in.
    #   • Each keyword must be relevant to the CURRENT story (matches
    #     the title / description / AC / domain feature) OR sit on the
    #     same theme as the test case (negative, data, workflow, …).
    #   • At most ONE keyword is applied to each test case, and only
    #     ONE surface area is touched (objective OR a precondition
    #     bullet OR an extra step) — whichever fits best.
    #   • A keyword is never reused across multiple TCs in the same
    #     run, so each enrichment carries unique information.
    # ══════════════════════════════════════════════════════════════════════
    if history and history.get('neighbour_domain_keywords'):
        # Build the current story's "fingerprint" (lower-cased blob of
        # everything the generator already knows about it) so we can
        # filter out historical keywords that are either trivially
        # present already or have nothing to do with this story.
        feature_lower = (feature_label or '').lower()
        story_blob = " ".join([
            title or '', desc_clean or '', ac_clean or '',
            feature_lower,
            domain.get('matched_screen', '') or '',
            domain.get('route', '') or '',
            " ".join(domain.get('keywords', []) or []),
        ]).lower()

        # 1) Take only domain-vocab keywords (already filtered upstream).
        all_kws = [k for k in (history.get('neighbour_domain_keywords') or [])
                   if len(k) >= 3]

        # 2) Drop anything already obvious in this story's wording.
        candidates = [k for k in all_kws
                      if k.lower() not in feature_lower
                      and k.lower() not in story_blob]

        # 3) Rank by relevance: keywords that DO appear in the story
        #    blob via a related form (e.g., "retries" vs "retry") get
        #    boosted; the rest keep their natural order.
        def _related_in_story(kw: str) -> bool:
            stem = kw.rstrip('s')
            return stem in story_blob or kw[:5] in story_blob

        candidates.sort(key=lambda k: (0 if _related_in_story(k) else 1))

        # Themes a keyword belongs to — used so we apply the RIGHT
        # historical keyword to the RIGHT test case (e.g. a "retry"
        # keyword belongs on a Workflow/Functional TC, not a UI one).
        _THEME_MAP = {
            'negative':  {'unauthorized', 'forbidden', 'denied', 'rejected', 'reject',
                          'failed', 'invalid'},
            'security':  {'role', 'roles', 'permission', 'permissions', 'rbac',
                          'unauthorized', 'forbidden', 'denied',
                          'fielduser', 'accountinguser', 'support',
                          'administrator', 'ceafraudinvestigator',
                          'accountverificationadministrator'},
            'workflow':  {'retry', 'reverse', 'resolve', 'release', 'sync', 'post',
                          'consolidate', 'consolidation', 'aggregate',
                          'transmission', 'transmit', 'intent', 'intents',
                          'monitoring', 'monitor', 'overnight', 'pending',
                          'stuck', 'webhook', 'callback', 'integration',
                          'integrations', 'resware', 'ewis', 'transactee'},
            'data':      {'csv', 'import', 'bulk', 'amount', 'currency',
                          'threshold', 'thresholds', 'preference',
                          'preferences', 'etag', 'audit', 'log', 'event',
                          'events'},
            'banking':   {'bank', 'banks', 'iba', 'rails', 'ach', 'wire',
                          'rtp', 'sameday', 'samedayach', 'account',
                          'accounts', 'reveal'},
            'onboarding': {'counterparty', 'counterparties', 'onboard',
                           'onboarding', 'verification', 'ews', 'pnc'},
        }

        def _themes_for_kw(kw: str) -> set:
            kl = kw.lower()
            return {t for t, words in _THEME_MAP.items() if kl in words}

        def _themes_for_tc(tc: dict) -> set:
            themes = set()
            cat = (tc.get('test_category') or '').lower()
            ac_ref = (tc.get('ac_ref') or '').lower()
            if cat == 'negative':
                themes.add('negative')
            if cat == 'api' or 'workflow' in ac_ref:
                themes.add('workflow')
            if ac_ref.startswith('role:') or ac_ref == 'security':
                themes.add('security')
            if ac_ref.startswith('data:'):
                themes.add('data')
            if ac_ref == 'ui':
                themes.add('ui')   # nothing in the vocab matches UI — by design
            if not themes:
                themes.add('workflow')  # default for AC / Happy-Path TCs
            return themes

        def _pick_keyword_for(tc: dict, used: set) -> Optional[str]:
            tc_themes = _themes_for_tc(tc)
            # First pass: theme match
            for k in candidates:
                if k in used:
                    continue
                if _themes_for_kw(k) & tc_themes:
                    return k
            # Second pass: any remaining keyword (skip if TC is UI-only)
            if 'ui' in tc_themes and len(tc_themes) == 1:
                return None
            for k in candidates:
                if k in used:
                    continue
                return k
            return None

        used_keywords: set = set()
        neighbour_ids_sample = [
            str(n.get('id'))
            for n in (history.get('neighbour_stories') or [])[:3]
            if n.get('id')
        ]

        def _join_sentence(base: str, addendum: str) -> str:
            """Append ``addendum`` to ``base`` with a clean sentence break."""
            b = (base or '').rstrip()
            if not b:
                return addendum
            if b[-1] not in '.!?':
                b += '.'
            return f"{b} {addendum.lstrip()}"

        for tc in test_cases:
            if not candidates:
                break
            kw = _pick_keyword_for(tc, used_keywords)
            if not kw:
                continue
            used_keywords.add(kw)
            kw_disp = kw.capitalize()

            # Decide which single surface area to touch for this TC.
            ac_ref = (tc.get('ac_ref') or '').lower()
            cat = (tc.get('test_category') or '').lower()

            if ac_ref.startswith('ac'):
                # AC-driven TC → enrich its Objective with a domain hook
                obj = tc.get('objective', '') or ''
                if kw.lower() not in obj.lower() and obj:
                    tc['objective'] = _join_sentence(
                        obj,
                        f"Also exercises the '{kw_disp}' flow "
                        f"previously covered in this area."
                    )
            elif cat == 'negative' or ac_ref == 'security':
                # Negative / security TC → add a sharp precondition bullet
                bullet = (f"• Historical baseline: prior stories in this area "
                          f"have hardened '{kw_disp}' handling — the same "
                          f"safeguards must hold here.")
                existing = tc.get('preconditions', '') or ''
                if 'Historical baseline' not in existing:
                    tc['preconditions'] = (
                        existing.rstrip() + "\n" + bullet
                        if existing else bullet
                    )
            elif ac_ref == 'workflow' or cat == 'api':
                # Workflow / API TC → tack on a quick regression-anchor step
                extra_step = (f"Smoke-check the '{kw_disp}' regression path "
                              f"that neighbouring stories rely on")
                extra_exp = (f"Existing '{kw_disp}' behaviour is unchanged "
                             f"by this story")
                steps = tc.get('steps') or []
                exps = tc.get('expected') or []
                if extra_step not in steps:
                    steps.append(extra_step)
                    exps.append(extra_exp)
                    tc['steps'] = steps
                    tc['expected'] = exps
            elif ac_ref.startswith('data:'):
                # Data-driven TC → mention the historical data shape
                obj = tc.get('objective', '') or ''
                if kw.lower() not in obj.lower() and obj:
                    tc['objective'] = _join_sentence(
                        obj,
                        f"Data shapes should remain compatible with the "
                        f"'{kw_disp}' coverage already in place."
                    )
            else:
                # Happy-Path / Role / generic → light objective touch
                obj = tc.get('objective', '') or ''
                if kw.lower() not in obj.lower() and obj:
                    tc['objective'] = _join_sentence(
                        obj,
                        f"Keeps parity with the '{kw_disp}' baseline "
                        f"established by recent stories in this area."
                    )

        # Stash the enrichment summary on the FIRST TC only, as a
        # single audit-trail bullet — replaces the old per-TC boilerplate.
        if used_keywords and test_cases:
            anchor = test_cases[0]
            audit_bits = []
            if used_keywords:
                audit_bits.append(
                    "Historical enrichment applied: "
                    + ", ".join(sorted(k.capitalize() for k in used_keywords))
                )
            if neighbour_ids_sample:
                audit_bits.append(
                    "Reference prior stories: "
                    + ", ".join(f"#{i}" for i in neighbour_ids_sample)
                )
            audit_line = "• " + " — ".join(audit_bits)
            existing = anchor.get('preconditions', '') or ''
            if 'Historical enrichment applied' not in existing:
                anchor['preconditions'] = (
                    existing.rstrip() + "\n" + audit_line
                    if existing else audit_line
                )

    # ══════════════════════════════════════════════════════════════════════
    # RULE GEN 04 + RULE MAINT 12: Club / dedupe similar-outcome test cases
    # ══════════════════════════════════════════════════════════════════════
    seen_keys = set()
    deduped = []
    for tc in test_cases:
        key = (tc['title'].lower()[:60], tc['test_category'], tc.get('ac_ref', ''))
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(tc)
    test_cases = deduped

    return test_cases, ac_clean, desc_clean, title


def _short_feature(title):
    """Short, business-friendly feature label from a user story title."""
    t = re.sub(r'^(EPP[:\-]\s*)', '', title, flags=re.IGNORECASE).strip()
    # Strip trailing punctuation
    t = t.rstrip(' .:;-–—')
    return t[:80]


def _imperative(text):
    """Convert an AC clause into a clean imperative test step.

    - Strips leading "the user", "user", "system", "they"
    - Replaces "should", "shall", "will" with active verbs
    - Capitalises the first letter
    - Trims length to 200 chars
    """
    if not text:
        return ''
    t = re.sub(r'\s+', ' ', text).strip()
    # Drop leading subject if present
    t = re.sub(r'^(the\s+)?(user|system|they|application|app)\s+(can\s+|should\s+|shall\s+|will\s+|is\s+able\s+to\s+)?',
               '', t, flags=re.IGNORECASE)
    # Convert "should be / shall be / will be" to "Verify ..."
    t = re.sub(r'^should\s+', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^shall\s+', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^will\s+', '', t, flags=re.IGNORECASE)
    t = t.strip(' .:;-–—')
    if not t:
        return ''
    # Capitalise first letter
    t = t[0].upper() + t[1:]
    if len(t) > 200:
        t = t[:197] + '...'
    return t


def _clean_clause(text):
    """Sanitize a Given/When/Then clause: collapse whitespace, strip leading
    bullets/dashes/punctuation, drop trailing punctuation. Also strips any
    'AC<n>' or 'Acceptance Criteria' labels — those are internal references
    and must never appear in user-visible test step text."""
    if not text:
        return ''
    t = re.sub(r'\s+', ' ', text).strip()
    t = re.sub(r'^[\-\u2013\u2014\u2022\*\>\s]+', '', t)  # leading dashes/bullets
    t = re.sub(r'^(and|or|that)\b\s+', '', t, flags=re.IGNORECASE)
    # Strip AC labels anywhere in the clause
    t = re.sub(r'\bAC\s*\d+\b[:\-\.\)]?\s*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\bacceptance\s+criteri(?:on|a)\b[:\-]?\s*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s{2,}', ' ', t)
    t = t.rstrip(' .:;,-\u2013\u2014')
    return t


def _build_condition_phrase(text):
    """Turn a free-form GWT clause into a SHORT, business-readable
    phrase suitable for a test case title (e.g. "displays bank filter",
    "rejects invalid amount"). Returns at most ~45 chars.
    """
    t = _clean_clause(text)
    if not t:
        return ''
    # Drop common AC noise & filler
    t = re.sub(r'\bAC\s*\d+\b[:\-]?\s*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^(given|when|then|and|but)\s+', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^(the\s+)?(system|user|application|page|screen)\s+(should|will|must|shall)\s+',
               '', t, flags=re.IGNORECASE)
    t = re.sub(r'^(it\s+)?(should|will|must|shall)\s+(be\s+)?', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^(verify|validate|ensure|check|confirm)\s+(that\s+)?', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^(a|an|the)\s+', '', t, flags=re.IGNORECASE)
    # Cut at first sentence/clause boundary OR at a comma if line is long
    t = re.split(r'[.;:]\s+', t)[0]
    if len(t) > 45 and ',' in t:
        t = t.split(',', 1)[0]
    t = re.sub(r'\s+', ' ', t).strip().rstrip(',;:- ')
    # Hard cap ~45 chars at last word boundary
    if len(t) > 45:
        cut = t[:45].rsplit(' ', 1)[0]
        t = cut.rstrip(',;:- ')
    return t


def _build_objective(feature_label, given_text, when_text, then_text, ac_summary, story_title=''):
    """Synthesise a concise 1-2 line Objective for a test case from the
    parsed Given/When/Then of an Acceptance Criterion.

    Goal: state WHAT the test verifies and WHY it matters — without copy-
    pasting the entire AC. Output is plain English, max ~220 chars,
    starts with "Verify that ..." or "Confirm that ...".
    """
    def _norm(s):
        if not s:
            return ''
        s = _clean_clause(s)
        s = re.sub(r'\bAC\s*\d+\b[:\-]?\s*', '', s, flags=re.IGNORECASE)
        s = re.sub(r'^(given|when|then|and|but)\s+', '', s, flags=re.IGNORECASE)
        s = re.sub(r'^(the\s+)?(system|user|application)\s+(should|will|must|shall)\s+',
                   r'\1\2 ', s, flags=re.IGNORECASE)
        s = re.sub(r'\s+', ' ', s).strip().rstrip('.;,:-')
        # First sentence only
        s = re.split(r'(?<=[.!?])\s+', s)[0]
        return s

    when_n = _norm(when_text)
    then_n = _norm(then_text)
    given_n = _norm(given_text)

    # Trim each piece so the final sentence stays readable
    def _trim(s, n):
        if not s or len(s) <= n:
            return s
        cut = s[:n].rsplit(' ', 1)[0]
        return cut.rstrip(',;:- ')

    when_n = _trim(when_n, 110)
    then_n = _trim(then_n, 110)
    given_n = _trim(given_n, 80)

    # Prefer: "Verify that <when_action> <then_outcome>."
    if when_n and then_n:
        objective = f"Verify that when {when_n}, {then_n}."
    elif then_n:
        objective = f"Verify that {then_n} for {feature_label}."
    elif when_n:
        objective = f"Verify the behaviour of {feature_label} when {when_n}."
    else:
        # Last-resort fallback: a one-line summary of the AC, NOT the whole text
        summary = _trim(_norm(ac_summary), 160)
        if summary:
            objective = f"Verify that {feature_label} satisfies the requirement: {summary}."
        else:
            objective = f"Verify that {feature_label} behaves as defined by the acceptance criteria."

    # Optionally add a brief context clause from GIVEN if it adds value
    if given_n and given_n.lower() not in objective.lower() and len(objective) < 170:
        objective += f" (Context: {given_n}.)"

    # Final tidy-up
    objective = re.sub(r'\s+', ' ', objective)
    objective = re.sub(r'\bthat that\b', 'that', objective, flags=re.IGNORECASE)
    objective = re.sub(r'\bwhen when\b', 'when', objective, flags=re.IGNORECASE)
    # Hard cap at ~280 chars (≈ 1-2 lines)
    if len(objective) > 280:
        objective = objective[:280].rsplit(' ', 1)[0].rstrip(',;:- ') + '.'
    return objective.strip()


def _normalize_title(t):
    """RULE GEN 02 — start with 'Verify', no 'that', collapse whitespace,
    no trailing punctuation, max 90 chars (precise & to-the-point)."""
    t = re.sub(r'\s+', ' ', t or '').strip()
    t = re.sub(r'\bthat\b\s*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^[\-\u2013\u2014\s]+', '', t)
    t = t.rstrip(' .:;,-\u2013\u2014')
    if not t.lower().startswith('verify'):
        t = 'Verify ' + t
    t = re.sub(r'\s+', ' ', t).strip()
    if len(t) > 90:
        cut = t[:90].rsplit(' ', 1)[0]
        t = cut
    return t


def _infer_application_module(combined):
    """Best-effort Application Module mapping (RULE GEN 01.14)."""
    mapping = [
        ('wire', 'Wire Payments'),
        ('webhook', 'Integrations / Webhooks'),
        ('resware', 'ResWare Integration'),
        ('escrow', 'Escrow'),
        ('payment', 'Payments'),
        ('disburs', 'Disbursements'),
        ('approval', 'Approvals'),
        ('notification', 'Notifications'),
        ('email', 'Notifications'),
        ('report', 'Reporting'),
        ('dashboard', 'Dashboard'),
        ('login', 'Authentication'),
        ('user', 'User Management'),
    ]
    for kw, mod in mapping:
        if kw in combined:
            return mod
    return 'EPP Core'


def _parse_ac_blocks(ac_clean):
    """Parse acceptance criteria text into individual AC blocks."""
    ac_blocks = []
    if ac_clean:
        ac_pattern = re.split(r'(AC\d+:?)', ac_clean, flags=re.IGNORECASE)
        current_ac = ''
        for part in ac_pattern:
            if re.match(r'AC\d+:?', part, re.IGNORECASE):
                if current_ac.strip():
                    ac_blocks.append(current_ac.strip())
                current_ac = part
            else:
                current_ac += part
        if current_ac.strip():
            ac_blocks.append(current_ac.strip())
    if not ac_blocks:
        lines = ac_clean.replace('\r', '').split('\n')
        for line in lines:
            line = line.strip()
            line = re.sub(r'^[\d]+[.\)]\s*', '', line)
            line = re.sub(r'^[-•*]\s*', '', line)
            line = line.strip()
            if line and len(line) > 10:
                ac_blocks.append(line)
    return ac_blocks

def generate_test_cases_report_html(work_item_id):
    """Generate a beautiful HTML report with test cases for a specific user story."""
    work_item = get_work_item_full_details(work_item_id)
    if not work_item:
        print(f"Could not fetch work item {work_item_id}")
        return
    
    test_cases, ac_clean, desc_clean, title = generate_test_cases_from_acceptance_criteria(work_item)
    fields = work_item.get('fields', {})
    assignee = fields.get('System.AssignedTo', {}).get('displayName', 'Unassigned')
    state = fields.get('System.State', 'Unknown')
    
    html_template = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test Cases - US #{{ work_item_id }}</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://fonts.googleapis.com/css?family=Roboto:400,500,700&display=swap" rel="stylesheet">
        <style>
            * { box-sizing: border-box; }
            body { font-family: 'Roboto', Arial, sans-serif; margin: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 40px 20px; color: #222; }
            .container { max-width: 1100px; margin: 0 auto; }
            .header { background: #fff; border-radius: 16px; padding: 32px 40px; margin-bottom: 30px; box-shadow: 0 10px 40px rgba(0,0,0,0.15); }
            .header h1 { margin: 0 0 12px 0; color: #2c3e50; font-size: 1.8em; }
            .us-badge { background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); color: #fff; padding: 4px 16px; border-radius: 20px; font-size: 0.95em; display: inline-block; margin-right: 12px; }
            .state-badge { padding: 4px 14px; border-radius: 20px; font-size: 0.9em; display: inline-block; }
            .state-badge.ready { background: #e8f5e9; color: #2e7d32; }
            .state-badge.inprogress { background: #e3f2fd; color: #1565c0; }
            .state-badge.new { background: #fff3e0; color: #e65100; }
            .meta { color: #666; margin-top: 16px; font-size: 1em; }
            .meta strong { color: #333; }
            
            .section { background: #fff; border-radius: 16px; padding: 28px 36px; margin-bottom: 24px; box-shadow: 0 6px 24px rgba(0,0,0,0.08); }
            .section h2 { color: #764ba2; margin: 0 0 16px 0; font-size: 1.4em; border-bottom: 2px solid #f0e6ff; padding-bottom: 10px; }
            .section h3 { color: #667eea; margin: 20px 0 12px 0; font-size: 1.15em; }
            
            .ac-list { background: #f8f9ff; border-radius: 12px; padding: 20px 24px; margin-top: 12px; }
            .ac-item { padding: 12px 16px; background: #fff; border-radius: 8px; margin-bottom: 10px; border-left: 4px solid #667eea; box-shadow: 0 2px 6px rgba(102,126,234,0.1); }
            .ac-item:last-child { margin-bottom: 0; }
            .ac-number { background: #667eea; color: #fff; border-radius: 50%; width: 26px; height: 26px; display: inline-flex; align-items: center; justify-content: center; font-size: 0.85em; font-weight: bold; margin-right: 12px; }
            
            .tc-card { background: linear-gradient(135deg, #f8f9ff 0%, #fff 100%); border-radius: 14px; padding: 24px 28px; margin-bottom: 20px; border: 1px solid #e8ecff; box-shadow: 0 4px 16px rgba(102,126,234,0.08); transition: transform 0.2s, box-shadow 0.2s; }
            .tc-card:hover { transform: translateY(-2px); box-shadow: 0 8px 28px rgba(102,126,234,0.15); }
            .tc-header { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 16px; }
            .tc-number { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; border-radius: 10px; padding: 8px 14px; font-weight: bold; font-size: 0.95em; white-space: nowrap; }
            .tc-title { font-size: 1.1em; font-weight: 600; color: #2c3e50; line-height: 1.4; }
            
            .tc-section { margin-bottom: 16px; }
            .tc-section:last-child { margin-bottom: 0; }
            .tc-label { font-weight: 600; color: #764ba2; font-size: 0.95em; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
            .tc-label::before { content: ''; width: 8px; height: 8px; background: #667eea; border-radius: 2px; }
            .tc-content { background: #fff; border-radius: 10px; padding: 14px 18px; border: 1px solid #f0e6ff; }
            .tc-content ul { margin: 0; padding-left: 20px; }
            .tc-content li { margin-bottom: 8px; line-height: 1.5; color: #444; }
            .tc-content li:last-child { margin-bottom: 0; }
            
            .summary-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-top: 20px; }
            .stat-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; border-radius: 12px; padding: 20px; text-align: center; }
            .stat-number { font-size: 2.2em; font-weight: bold; }
            .stat-label { font-size: 0.95em; opacity: 0.9; margin-top: 4px; }
            
            .print-btn { background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); color: #fff; border: none; border-radius: 10px; padding: 12px 28px; font-size: 1em; cursor: pointer; margin-top: 20px; transition: transform 0.2s, box-shadow 0.2s; }
            .print-btn:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(102,126,234,0.4); }
            
            @media print {
                body { background: #fff; padding: 20px; }
                .tc-card { break-inside: avoid; }
                .print-btn { display: none; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>
                    <span class="us-badge">US #{{ work_item_id }}</span>
                    {{ title }}
                </h1>
                <div>
                    <span class="state-badge {% if 'progress' in state.lower() %}inprogress{% elif 'ready' in state.lower() %}ready{% else %}new{% endif %}">{{ state }}</span>
                </div>
                <div class="meta">
                    <strong>👤 Assigned to:</strong> {{ assignee }}
                </div>
                <div class="summary-stats">
                    <div class="stat-card">
                        <div class="stat-number">{{ ac_count }}</div>
                        <div class="stat-label">Acceptance Criteria</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{{ tc_count }}</div>
                        <div class="stat-label">Test Cases Generated</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{{ step_count }}</div>
                        <div class="stat-label">Total Test Steps</div>
                    </div>
                </div>
            </div>
            
            {% if description %}
            <div class="section">
                <h2>📋 Description</h2>
                <div class="tc-content">{{ description }}</div>
            </div>
            {% endif %}
            
            {% if acceptance_criteria %}
            <div class="section">
                <h2>✅ Acceptance Criteria</h2>
                <div class="ac-list">
                    {% for ac in ac_list %}
                    <div class="ac-item">
                        <span class="ac-number">{{ loop.index }}</span>
                        {{ ac }}
                    </div>
                    {% endfor %}
                </div>
            </div>
            {% endif %}
            
            <div class="section">
                <h2>🧪 Generated Test Cases</h2>
                {% for tc in test_cases %}
                <div class="tc-card">
                    <div class="tc-header">
                        <span class="tc-number">TC {{ loop.index }}</span>
                        <span class="tc-title">{{ tc['title'] }}</span>
                    </div>
                    
                    <div class="tc-section">
                        <div class="tc-label">Preconditions</div>
                        <div class="tc-content">{{ tc['preconditions']|safe }}</div>
                    </div>
                    
                    <div class="tc-section">
                        <div class="tc-label">Test Steps</div>
                        <div class="tc-content">
                            {{ tc['steps']|safe }}
                        </div>
                    </div>
                    
                    <div class="tc-section">
                        <div class="tc-label">Expected Result</div>
                        <div class="tc-content">{{ tc['expected'] }}</div>
                    </div>
                    
                    <div class="tc-section">
                        <div class="tc-label">Postconditions</div>
                        <div class="tc-content">{{ tc['postconditions'] }}</div>
                    </div>
                </div>
                {% endfor %}
            </div>
            
            <button class="print-btn" onclick="window.print()">🖨️ Print / Save as PDF</button>
        </div>
    </body>
    </html>
    '''
    
    # Parse acceptance criteria into list (same logic as generate function)
    ac_list = []
    if ac_clean:
        # Split by AC pattern (AC1:, AC2:, etc.)
        ac_pattern = re.split(r'(AC\d+:?)', ac_clean, flags=re.IGNORECASE)
        current_ac = ''
        for part in ac_pattern:
            if re.match(r'AC\d+:?', part, re.IGNORECASE):
                if current_ac.strip():
                    ac_list.append(current_ac.strip())
                current_ac = part
            else:
                current_ac += part
        if current_ac.strip():
            ac_list.append(current_ac.strip())
    
    # If no AC pattern found, try splitting by lines
    if not ac_list:
        lines = ac_clean.replace('\r', '').split('\n')
        for line in lines:
            line = line.strip()
            line = re.sub(r'^[\d]+[.\)]\s*', '', line)
            line = re.sub(r'^[-*]\s*', '', line)
            line = line.strip()
            if line and len(line) > 10:
                ac_list.append(line)
    
    # Format test case steps as HTML lists
    for tc in test_cases:
        if isinstance(tc['steps'], list):
            tc['steps'] = '<ul>' + ''.join(f'<li>{step}</li>' for step in tc['steps']) + '</ul>'
        tc['preconditions'] = tc['preconditions'].replace('\n', '<br>')
    
    # Calculate stats
    ac_count = len(ac_list)
    tc_count = len(test_cases)
    step_count = sum(len(tc.get('steps', '').split('<li>')) - 1 for tc in test_cases)
    
    from jinja2 import Template
    html = Template(html_template).render(
        work_item_id=work_item_id,
        title=title,
        state=state,
        assignee=assignee,
        description=desc_clean,
        acceptance_criteria=ac_clean,
        ac_list=ac_list,
        test_cases=test_cases,
        ac_count=ac_count,
        tc_count=tc_count,
        step_count=step_count
    )
    
    filename = f"test_cases_US{work_item_id}.html"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nTest cases report generated: {filename}")
    print(f"   {ac_count} Acceptance Criteria found")
    print(f"   {tc_count} Test Cases generated")
    print(f"   {step_count} Total Test Steps")
    
    return filename


# ── ADO Test Case Writer ──────────────────────────────────────────────────────

def format_steps_as_ado_xml(steps, expected=''):
    """
    Convert a list of step strings into the Azure DevOps TCM Steps XML format
    with per-step expected results (RULE GEN 01.5).

    Each parameterizedString is `isformatted="true"`, meaning ADO expects HTML.
    If the input already contains HTML (e.g. <b>, <br>), it is preserved.
    Otherwise the text is HTML-escaped and wrapped in a <DIV><P>…</P></DIV> block
    (the format the ADO Test Case form normally produces).
    """
    from xml.sax.saxutils import escape

    if isinstance(steps, str):
        items = re.findall(r'<li>(.*?)</li>', steps, re.DOTALL)
        if not items:
            items = [steps]
        steps = items

    if isinstance(expected, list):
        expected_list = expected
    else:
        expected_list = [''] * (len(steps) - 1) + [expected] if steps else [expected]
    while len(expected_list) < len(steps):
        expected_list.append('')

    def _to_html(text):
        text = (text or '').strip()
        if not text:
            return ''
        # If text already contains HTML tags, preserve them; only escape stray '&'
        if re.search(r'<[a-zA-Z/!][^>]*>', text):
            # Only fix bare ampersands that are not entities
            text = re.sub(r'&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)', '&amp;', text)
            return f'<DIV><P>{text}</P></DIV>'
        # Plain text — escape and wrap
        return f'<DIV><P>{escape(text)}</P></DIV>'

    xml_steps = []
    for idx, step_text in enumerate(steps, 1):
        step_html = _to_html(step_text)
        exp_html = _to_html(expected_list[idx - 1])
        # The two parameterizedString contents must be XML-escaped at the outer
        # level too (they are children of <parameterizedString>).
        xml_steps.append(
            f'<step id="{idx}" type="ActionStep">'
            f'<parameterizedString isformatted="true">{escape(step_html)}</parameterizedString>'
            f'<parameterizedString isformatted="true">{escape(exp_html)}</parameterizedString>'
            f'<description/>'
            f'</step>'
        )
    last_id = len(steps)
    return f'<steps id="0" last="{last_id}">{"".join(xml_steps)}</steps>'


# Cache of ADO field reference names known to be missing in this project's
# process template. Populated lazily after the first failed POST so that
# subsequent test case creations skip these fields up front and avoid
# triggering the noisy "Retry without optional fields" path on every call.
_KNOWN_MISSING_FIELDS = set()


def create_test_case_in_ado(tc_title, steps_xml, preconditions_html, area_path, iteration_path,
                            priority=2, automation_status='Not Automated', extra_fields=None,
                            objective_html=None, preconditions_field_html=None,
                            description_html=None):
    """
    Create a Test Case work item in Azure DevOps with all RULE GEN 01 attributes.

    Field mapping in ADO Test Case form:
      - "Summary" (top of form)              -> System.Description       (Objective)
      - "Preconditions" (Steps tab section)  -> Microsoft.VSTS.TCM.LocalDataSource is NOT it;
                                                the actual field is Microsoft.VSTS.TCM.Preconditions
      - "Steps"                              -> Microsoft.VSTS.TCM.Steps

    `extra_fields` is a dict of additional ADO field reference names to set
    (e.g., custom fields like Custom.TestCategory, Custom.ApplicationName).
    Unknown/custom fields that ADO rejects are retried without them, and the
    missing field names are cached in `_KNOWN_MISSING_FIELDS` so subsequent
    test case creations skip them up front (avoiding repeated retries).
    """
    org = urllib.parse.quote(ADO_ORG)
    project = urllib.parse.quote(ADO_PROJECT)
    url = f"https://dev.azure.com/{org}/{project}/_apis/wit/workitems/$Test%20Case?api-version=7.1"

    # ADO Priority field expects 1-4; map any string fallback
    if isinstance(priority, str):
        priority_map = {'High': 1, 'Medium': 2, 'Low': 3}
        priority = priority_map.get(priority, 2)

    # Build the tag list. Always include "Gen-AI" and the mandatory
    # "AI TestCase" tag, plus the test_type and test_category (from
    # extra_fields) and any EPP area tag (AP_Bulk / Resware_OB / etc.).
    # These are surfaced via System.Tags so they remain visible in ADO
    # even when the project's process template lacks the Custom.* fields.
    # Tags in ADO are semicolon-separated.
    tag_parts = ["Gen-AI", "AI TestCase"]
    if extra_fields:
        tt = (extra_fields.get('Custom.TestType') or '').strip()
        tc_cat = (extra_fields.get('Custom.TestCategory') or '').strip()
        epp_area = (extra_fields.get('X-Tag.EppArea') or '').strip()
        # "Smoke & Regression" -> two separate tags so both are filterable in ADO
        if tt:
            for piece in re.split(r'\s*&\s*|\s*,\s*|\s*/\s*', tt):
                piece = piece.strip()
                if piece and piece not in tag_parts:
                    tag_parts.append(piece)
        if tc_cat and tc_cat not in tag_parts:
            tag_parts.append(tc_cat)
        if epp_area and epp_area not in tag_parts:
            tag_parts.append(epp_area)
    tags_value = "; ".join(tag_parts)

    patch_doc = [
        {"op": "add", "path": "/fields/System.Title", "value": tc_title},
        {"op": "add", "path": "/fields/Microsoft.VSTS.TCM.Steps", "value": steps_xml},
        {"op": "add", "path": "/fields/System.AreaPath", "value": area_path},
        {"op": "add", "path": "/fields/System.IterationPath", "value": iteration_path},
        {"op": "add", "path": "/fields/Microsoft.VSTS.Common.Priority", "value": priority},
        {"op": "add", "path": "/fields/Microsoft.VSTS.TCM.AutomationStatus", "value": automation_status},
        # Tag with Gen-AI + the test type (Smoke / Regression / etc.) + category
        {"op": "add", "path": "/fields/System.Tags", "value": tags_value},
    ]

    # ── Objective → System.Description (the "Summary" area on the Test Case form)
    if objective_html:
        patch_doc.append({"op": "add", "path": "/fields/System.Description",
                          "value": objective_html})
    elif description_html:
        patch_doc.append({"op": "add", "path": "/fields/System.Description",
                          "value": description_html})
    elif preconditions_html:
        # Backward compat: legacy single-blob description
        patch_doc.append({"op": "add", "path": "/fields/System.Description",
                          "value": preconditions_html})

    # ── Objectives & Preconditions → custom field on this project's process
    #    template ("Objectives and Preconditions"). The standard
    #    Microsoft.VSTS.TCM.Preconditions field does NOT exist here, so we
    #    must use the custom reference name discovered via the field probe.
    if preconditions_field_html:
        patch_doc.append({"op": "add",
                          "path": "/fields/Custom.ObjectivesandPreconditions",
                          "value": preconditions_field_html})

    if extra_fields:
        for ref_name, value in extra_fields.items():
            if value is None or value == '':
                continue
            # Virtual "X-Tag.*" entries are folded into System.Tags above
            # and must NOT be sent as real ADO field operations.
            if ref_name.startswith('X-Tag.'):
                continue
            patch_doc.append({"op": "add", "path": f"/fields/{ref_name}", "value": value})

    patch_headers = {
        'Content-Type': 'application/json-patch+json',
        'Authorization': f'Basic {b64_pat}'
    }

    # Pre-filter: drop any fields we already know this project's template
    # rejects, so we don't waste a round-trip on the inevitable retry.
    if _KNOWN_MISSING_FIELDS:
        patch_doc = [p for p in patch_doc if not any(
            p['path'].endswith(f'/{ref}') for ref in _KNOWN_MISSING_FIELDS
        )]

    try:
        resp = requests.post(url, headers=patch_headers, json=patch_doc, verify=False, timeout=30)
        if resp.status_code >= 400:
            err_text = resp.text or ''

            # Detect any specific TF51535 "Cannot find field X" error and drop X.
            # Use a non-greedy capture that stops at the trailing sentence
            # period (don't swallow it into the field name).
            missing = re.findall(r"Cannot find field ([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*)", err_text)

            # Build the drop-set. PREFER the specifically-named missing
            # fields from the error — that way we only strip what ADO
            # actually objected to. Only fall back to the broad "drop
            # every custom/optional field" sweep when we can't parse a
            # specific field name from the error (very rare).
            optional_refs = set()
            if missing:
                for m in missing:
                    optional_refs.add(m)
                    # Remember it for future calls in this run.
                    _KNOWN_MISSING_FIELDS.add(m)
            else:
                # Generic fallback — couldn't isolate the offending field,
                # so retry without any "best-effort" custom fields.
                if extra_fields:
                    optional_refs.update(
                        k for k in extra_fields.keys() if not k.startswith('X-Tag.')
                    )
                optional_refs.add('Custom.ObjectivesandPreconditions')
                optional_refs.add('Microsoft.VSTS.TCM.Preconditions')

            print(f"  Retry without optional fields (ADO error: {err_text[:160]})")
            core_doc = [p for p in patch_doc if not any(
                p['path'].endswith(f'/{ref}') for ref in optional_refs
            )]
            resp = requests.post(url, headers=patch_headers, json=core_doc, verify=False, timeout=30)
            if resp.status_code >= 400:
                print(f"  API Response: {resp.text[:300]}")
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  ERROR creating test case '{tc_title[:60]}': {e}")
        return None


def link_test_case_to_story(test_case_id, story_id):
    """
    Add a 'Tests / Tested By' link between a test case and a user story.
    The link is created on the test case pointing TO the user story.
    """
    org = urllib.parse.quote(ADO_ORG)
    url = f"https://dev.azure.com/{org}/_apis/wit/workitems/{test_case_id}?api-version=7.1"

    # "Microsoft.VSTS.Common.TestedBy-Reverse" = Tests  (TC -> US)
    target_url = f"https://dev.azure.com/{ADO_ORG}/_apis/wit/workitems/{story_id}"
    patch_doc = [
        {
            "op": "add",
            "path": "/relations/-",
            "value": {
                "rel": "Microsoft.VSTS.Common.TestedBy-Reverse",
                "url": target_url,
                "attributes": {"comment": "Auto-generated test case"}
            }
        }
    ]

    patch_headers = {
        'Content-Type': 'application/json-patch+json',
        'Authorization': f'Basic {b64_pat}'
    }

    try:
        resp = requests.patch(url, headers=patch_headers, json=patch_doc, verify=False, timeout=30)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"  ERROR linking TC #{test_case_id} to US #{story_id}: {e}")
        return False


def generate_and_push_test_cases(story_id):
    """
    Given a User Story ID, fetch details, generate test cases,
    show them in a review HTML page with checkboxes, and let the user
    push selected ones to ADO via a button click.
    Launches a local server for the review workflow.
    """
    import json
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import webbrowser

    print(f"\n{'='*60}")
    print(f"  Generating Test Cases for User Story #{story_id}")
    print(f"{'='*60}")

    # 1. Fetch full user story details
    work_item = get_work_item_full_details(story_id)
    if not work_item:
        print("ERROR: Could not fetch user story. Check the ID and your PAT.")
        return

    fields = work_item.get('fields', {})
    title = fields.get('System.Title', '')
    state = fields.get('System.State', '')
    area_path = fields.get('System.AreaPath', ADO_PROJECT)
    iteration_path = fields.get('System.IterationPath', ADO_PROJECT)
    assignee = fields.get('System.AssignedTo', {}).get('displayName', 'Unassigned')
    description = fields.get('System.Description', '')
    ac_raw = fields.get('Microsoft.VSTS.Common.AcceptanceCriteria', '')

    print(f"  Title:    {title}")
    print(f"  State:    {state}")
    print(f"  Assigned: {assignee}")
    print(f"  AC found: {'Yes' if ac_raw else 'No'}")

    # 1.5 Build a historical context from neighbouring User Stories /
    #     Test Cases in the same Area Path. Best-effort: any failure
    #     here is non-fatal and just means we proceed without prior-art.
    history_ctx = None
    try:
        # Pre-classify the story so we can narrow the WIQL by EPP area-tag
        pre_domain = build_domain_context(
            title, clean_html(description) if description else '',
            clean_html(ac_raw) if ac_raw else '')
        epp_area_tag = pre_domain.get('epp_area')
        print(f"  Looking up neighbouring User Stories in area: {area_path}"
              + (f" (tag: {epp_area_tag})" if epp_area_tag else ""))
        history_ctx = build_history_context(
            current_story_id=int(story_id),
            current_area_path=area_path,
            ado_org=ADO_ORG,
            ado_project=ADO_PROJECT,
            headers=headers,
            epp_area=epp_area_tag,
        )
        if history_ctx and history_ctx.get('neighbour_stories'):
            print(f"  History: {history_ctx['summary']}")
        else:
            print("  History: no comparable prior User Stories found")
    except Exception as e:
        print(f"  History: lookup skipped ({e})")
        history_ctx = None

    # 2. Generate test cases (history is used as supplemental context)
    test_cases_raw, ac_clean, desc_clean, _ = \
        generate_test_cases_from_acceptance_criteria(work_item, history=history_ctx)
    if not test_cases_raw:
        print("WARNING: No test cases could be generated.")
        return

    print(f"  Generated {len(test_cases_raw)} test cases.")

    # Prepare test cases data for JSON serialization
    import uuid as _uuid
    session_id = _uuid.uuid4().hex
    tc_data_list = []
    for idx, tc in enumerate(test_cases_raw):
        steps_list = tc['steps'] if isinstance(tc['steps'], list) else [tc['steps']]
        expected_list = tc.get('expected', [])
        if isinstance(expected_list, str):
            expected_list = [expected_list]
        tc_data_list.append({
            'index': idx,
            'uid': f"{session_id}-{idx}",
            'title': tc['title'],
            'objective': tc.get('objective', ''),
            'preconditions': tc.get('preconditions', ''),
            'steps': steps_list,
            'expected': expected_list,
            'overall_expected': tc.get('overall_expected', ''),
            'priority': tc.get('priority', 2),
            'test_type': tc.get('test_type', 'Smoke & Regression'),
            'test_category': tc.get('test_category', 'Functional'),
            'review_status': tc.get('review_status', 'NO'),
            'automation_state': tc.get('automation_state', 'Non-Automatable'),
            'area_path': tc.get('area_path', ''),
            'iteration_path': tc.get('iteration_path', ''),
            'application_name': tc.get('application_name', 'EPP'),
            'application_module': tc.get('application_module', ''),
            'ac_ref': tc.get('ac_ref', ''),
            'epp_area': tc.get('epp_area', ''),
        })

    story_context = {
        'story_id': story_id,
        'session_id': session_id,
        'title': title,
        'state': state,
        'assignee': assignee,
        'area_path': area_path,
        'iteration_path': iteration_path,
        'description': desc_clean,
        'acceptance_criteria': ac_clean,
        'test_cases': tc_data_list,
        # Surface the historical context so the review page can show
        # which neighbouring stories / domain keywords shaped the
        # generated test cases (RULE HIST 15).
        'history': history_ctx or {},
    }

    # ── Build Review HTML ──────────────────────────────────────────────────
    review_html = _build_review_html(story_context)
    reports_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'reports')
    os.makedirs(reports_dir, exist_ok=True)
    review_file = os.path.join(reports_dir, f"review_test_cases_US{story_id}.html")
    with open(review_file, 'w', encoding='utf-8') as f:
        f.write(review_html)

    # ── Local server to handle the "Add to ADO" action ─────────────────────
    server_result = {'done': False}
    # Build a uid → tc lookup for stable identification (immune to re-orderings)
    tc_by_uid = {tc['uid']: tc for tc in tc_data_list}
    current_session_id = session_id

    class ReviewHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # suppress server logs

        def _send_no_cache_headers(self):
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')

        def do_GET(self):
            # Strip any querystring (e.g., cache-buster)
            path = self.path.split('?', 1)[0]
            if path == '/' or path == '/review':
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self._send_no_cache_headers()
                self.end_headers()
                with open(review_file, 'r', encoding='utf-8') as f:
                    self.wfile.write(f.read().encode('utf-8'))
            elif path == '/status':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self._send_no_cache_headers()
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'ready', 'session_id': current_session_id}).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path == '/add-to-ado':
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length).decode('utf-8')
                selected = json.loads(body)
                posted_session = selected.get('session_id', '')
                selected_uids = selected.get('uids', [])
                # Backward-compat: also accept indices, but only if session matches
                selected_indices = selected.get('indices', [])

                # ── Stale page guard: refuse to push if the page in the browser is
                #    from a previous run (different session id). This prevents the
                #    common pitfall where a cached/old review page submits indices
                #    that no longer correspond to the latest generated test cases.
                if posted_session and posted_session != current_session_id:
                    msg = (f"Stale review page detected (session mismatch). "
                           f"Please refresh the browser (Ctrl+F5) and try again.")
                    print(f"  REFUSED: {msg}")
                    self.send_response(409)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self._send_no_cache_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'error': 'stale_session',
                        'message': msg,
                        'results': []
                    }).encode())
                    return

                # Resolve selected test cases preferring uid (stable) over index
                selected_tcs = []
                if selected_uids:
                    for uid in selected_uids:
                        tc = tc_by_uid.get(uid)
                        if tc is not None:
                            selected_tcs.append(tc)
                elif selected_indices:
                    for idx in selected_indices:
                        if 0 <= idx < len(tc_data_list):
                            selected_tcs.append(tc_data_list[idx])

                print(f"\n  Received request to add {len(selected_tcs)} test cases to ADO...")

                results = []
                # Helper: scrub any leftover "AC<n>" / "AC Reference" / "Acceptance Criteria"
                # tokens from any user-visible string before pushing to ADO.
                def _scrub_ac(s):
                    if not s:
                        return s
                    s = re.sub(r'\bAC\s*Reference\b\s*[:\-]?\s*[^<\n\r]*', '', s, flags=re.IGNORECASE)
                    s = re.sub(r'\bAC\s*\d+\b[:\-\.\)]?\s*', '', s, flags=re.IGNORECASE)
                    s = re.sub(r'\bacceptance\s+criteri(?:on|a)\b[:\-]?\s*', '', s, flags=re.IGNORECASE)
                    # Strip internal rule-ID tags such as "(RULE FUNC 11)", "RULE GEN 01.5",
                    # "RULE COV 08 / RULE DATA 09" — these are authoring guidelines and
                    # should never appear in business-facing test case content.
                    s = re.sub(r'\(\s*RULE\s+[A-Z]+\s*\d+(?:\.\d+)?(?:\s*[/,]\s*RULE\s+[A-Z]+\s*\d+(?:\.\d+)?)*\s*\)',
                               '', s, flags=re.IGNORECASE)
                    s = re.sub(r'\bRULE\s+[A-Z]+\s*\d+(?:\.\d+)?\b', '', s, flags=re.IGNORECASE)
                    s = re.sub(r'[ \t]{2,}', ' ', s)
                    s = re.sub(r'\s+([.,;:])', r'\1', s)  # tidy stray space before punctuation
                    return s.strip()

                for tc in selected_tcs:
                    sel_idx = tc.get('index', -1)
                    tc_title = _scrub_ac(tc['title'])  # RULE GEN 02
                    preconditions = _scrub_ac(tc.get('preconditions', ''))
                    objective = _scrub_ac(tc.get('objective', ''))
                    overall_expected = _scrub_ac(tc.get('overall_expected', ''))
                    # Scrub each step / expected as well
                    tc_steps = [_scrub_ac(s) for s in (tc.get('steps') or [])]
                    tc_expected = [_scrub_ac(e) for e in (tc.get('expected') or [])]

                    # ── Build Steps tab content. Objective and Preconditions are
                    #    shown ONLY in their dedicated ADO fields (System.Description
                    #    / Custom.ObjectivesandPreconditions) — NOT in the Steps tab,
                    #    to avoid duplication.
                    full_steps = list(tc_steps)
                    full_expected = list(tc_expected or [])

                    if overall_expected:
                        full_steps.append("Verify the overall expected outcome of the test case")
                        full_expected.append(overall_expected)

                    steps_xml = format_steps_as_ado_xml(full_steps, full_expected)

                    # ── Objective HTML → goes into System.Description (the "Summary"
                    #    box on the Test Case form, top of the page).
                    objective_html = ''
                    if objective:
                        objective_html = (
                            f"<div><b>Objective:</b><br>{objective}</div>"
                        )
                        # Append useful context below the objective (no "AC" labels)
                        objective_html += (
                            f"<br><div><b>Application:</b> {tc.get('application_name', 'EPP')} &mdash; "
                            f"<b>Module:</b> {tc.get('application_module', '')}</div>"
                            f"<div><b>Test Type:</b> {tc.get('test_type', '')} &mdash; "
                            f"<b>Category:</b> {tc.get('test_category', '')}</div>"
                        )

                    # ── Preconditions HTML → goes into Custom.ObjectivesandPreconditions
                    #    (the "Objectives and Preconditions" panel on the Test Case
                    #    form in this project's process template).
                    #    We render BOTH the Objective and the Preconditions in this
                    #    field, since the field name is "Objectives and Preconditions".
                    from xml.sax.saxutils import escape as _xml_escape
                    raw_pre = (preconditions or '').strip()
                    if not raw_pre:
                        raw_pre = "User is logged in to EPP with the required permissions for this functionality."
                    # Split into list items (newline first, then '; ' separator)
                    if '\n' in raw_pre:
                        items = [s.strip(' -•\t') for s in raw_pre.split('\n') if s.strip()]
                    elif '; ' in raw_pre:
                        items = [s.strip() for s in raw_pre.split('; ') if s.strip()]
                    else:
                        items = [raw_pre]
                    if len(items) > 1:
                        pre_html_block = "<ul>" + ''.join(
                            f"<li>{_xml_escape(it)}</li>" for it in items) + "</ul>"
                    else:
                        pre_html_block = f"<div>{_xml_escape(items[0])}</div>"

                    obj_html_block = ""
                    if objective:
                        obj_html_block = f"<div>{_xml_escape(objective)}</div>"

                    preconditions_field_html = (
                        (f"<p><b>Objective:</b></p>{obj_html_block}" if obj_html_block else "")
                        + f"<p><b>Preconditions:</b></p>{pre_html_block}"
                    )

                    # Build a rich combined Description (legacy / fallback). No "AC" labels.
                    desc_parts = []
                    if objective:
                        desc_parts.append(f"<p><b>Objective:</b><br>{objective}</p>")
                    if preconditions:
                        desc_parts.append(f"<p><b>Preconditions:</b><br>{preconditions.replace(chr(10), '<br>')}</p>")
                    if overall_expected:
                        desc_parts.append(f"<p><b>Overall Expected Result:</b><br>{overall_expected}</p>")
                    desc_parts.append(f"<p><b>Application:</b> {tc.get('application_name', 'EPP')} &mdash; "
                                      f"<b>Module:</b> {tc.get('application_module', '')}</p>")
                    desc_parts.append(f"<p><b>Test Type:</b> {tc.get('test_type', '')} &mdash; "
                                      f"<b>Category:</b> {tc.get('test_category', '')}</p>")
                    desc_parts.append(f"<p><b>Review Status:</b> {tc.get('review_status', 'NO')} &mdash; "
                                      f"<b>Automation State:</b> {tc.get('automation_state', 'Non-Automatable')}</p>")
                    description_html = ''.join(desc_parts)

                    # Custom fields (best-effort; will be dropped if process template lacks them)
                    extra_fields = {
                        'Custom.TestType': tc.get('test_type', ''),
                        'Custom.TestCategory': tc.get('test_category', ''),
                        'Custom.ReviewStatus': tc.get('review_status', 'NO'),
                        'Custom.ApplicationName': tc.get('application_name', 'EPP'),
                        'Custom.ApplicationModule': tc.get('application_module', ''),
                        # EPP area tag (AP_Bulk / Resware_OB / Escrow_CEA / etc.)
                        # — surfaced into System.Tags by create_test_case_in_ado.
                        'X-Tag.EppArea': tc.get('epp_area', '') or '',
                    }

                    print(f"  Creating: {tc_title[:70]}...")
                    result = create_test_case_in_ado(
                        tc_title=tc_title,
                        steps_xml=steps_xml,
                        preconditions_html=description_html,
                        area_path=area_path,
                        iteration_path=iteration_path,
                        priority=tc.get('priority', 2),
                        automation_status='Not Automated',
                        extra_fields=extra_fields,
                        objective_html=objective_html or None,
                        preconditions_field_html=preconditions_field_html or None,
                        description_html=description_html,
                    )
                    if result:
                        tc_id = result['id']
                        link_test_case_to_story(tc_id, story_id)
                        print(f"  Created TC #{tc_id} and linked to US #{story_id}")
                        results.append({'index': sel_idx, 'tc_id': tc_id, 'title': tc_title, 'success': True})
                    else:
                        results.append({'index': sel_idx, 'tc_id': None, 'title': tc_title, 'success': False})

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'results': results}).encode())

                created = [r for r in results if r['success']]
                print(f"\n  Done: {len(created)}/{len(selected_tcs)} test cases created in ADO.")
                server_result['done'] = True

                # Auto-stop the server shortly after responding so the script exits
                # cleanly once the user has pushed test cases to ADO.
                def _shutdown_later():
                    import time as _t
                    _t.sleep(1.5)  # give the browser time to receive the response
                    print("  Auto-stopping review server...")
                    try:
                        server.shutdown()
                    except Exception:
                        pass
                threading.Thread(target=_shutdown_later, daemon=True).start()
            else:
                self.send_response(404)
                self.end_headers()

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()

    port = 8765
    server = HTTPServer(('127.0.0.1', port), ReviewHandler)

    print(f"\n  Review page: http://localhost:{port}/review?s={current_session_id[:8]}")
    print(f"  Opening in browser...")
    print(f"  (Select test cases, then click 'Add to ADO'. Press Ctrl+C to stop.)\n")

    webbrowser.open(f"http://localhost:{port}/review?s={current_session_id}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
    finally:
        server.server_close()


def _build_review_html(ctx):
    """Build the review HTML page with checkboxes and the Add to ADO button."""
    tc_cards_html = ''
    for tc in ctx['test_cases']:
        steps = tc['steps']
        expected_list = tc.get('expected') or []
        if isinstance(expected_list, str):
            expected_list = [expected_list]
        # Render Steps + Expected as a 2-column table (per-step expected — RULE GEN 01.5)
        rows = ''
        for i, step in enumerate(steps):
            exp = expected_list[i] if i < len(expected_list) else ''
            rows += (
                f'<tr><td style="width:40px;text-align:center;color:#888">{i+1}</td>'
                f'<td>{step}</td>'
                f'<td style="color:#1565c0">{exp or "&mdash;"}</td></tr>'
            )
        steps_table = (
            '<table style="width:100%;border-collapse:collapse;font-size:.95em">'
            '<thead><tr style="background:#f0e6ff;color:#764ba2">'
            '<th style="padding:6px 8px;text-align:center;width:40px">#</th>'
            '<th style="padding:6px 8px;text-align:left">Action</th>'
            '<th style="padding:6px 8px;text-align:left">Expected Result</th>'
            '</tr></thead><tbody>' + rows + '</tbody></table>'
        )

        priority = tc.get('priority', 2)
        test_type = tc.get('test_type', 'Smoke & Regression')
        test_category = tc.get('test_category', 'Functional')
        ac_ref = tc.get('ac_ref', '')
        objective = tc.get('objective', '')
        app_module = tc.get('application_module', '')
        epp_area = tc.get('epp_area', '')
        # Priority 1 = Highest (red)…4 = Lowest (green)
        pri_color = {1: '#e53935', 2: '#fb8c00', 3: '#fdd835', 4: '#43a047'}.get(priority, '#888')
        cat_color = {'API': '#1976d2', 'Functional': '#667eea', 'Negative': '#d32f2f'}.get(test_category, '#667eea')
        # EPP area badge colours — each domain area gets its own colour for fast visual filtering
        area_color = {
            'AP_Bulk':    '#00897b',  # teal
            'AP_WD':      '#5e35b1',  # purple
            'AP_Portal':  '#3949ab',  # indigo
            'STEPS_OB':   '#d81b60',  # pink
            'Resware_OB': '#c62828',  # red
            'Escrow_OB':  '#ef6c00',  # orange
            'Escrow_IB':  '#2e7d32',  # green
            'Escrow_CEA': '#1565c0',  # blue
        }.get(epp_area, '#616161')

        tc_cards_html += f'''
        <div class="tc-card" data-index="{tc['index']}" data-uid="{tc['uid']}">
            <div class="tc-header">
                <label class="tc-checkbox">
                    <input type="checkbox" checked data-idx="{tc['index']}" data-uid="{tc['uid']}">
                    <span class="checkmark"></span>
                </label>
                <span class="tc-number">TC {tc['index']+1}</span>
                <span class="tc-title">{tc['title']}</span>
                <span style="margin-left:auto;display:flex;gap:6px;align-items:center;flex-shrink:0;flex-wrap:wrap;justify-content:flex-end">
                    <span style="background:{pri_color};color:#fff;border-radius:8px;padding:2px 10px;font-size:.78em;font-weight:600">P{priority}</span>
                    <span style="background:#667eea;color:#fff;border-radius:8px;padding:2px 10px;font-size:.78em;font-weight:600">{test_type}</span>
                    <span style="background:{cat_color};color:#fff;border-radius:8px;padding:2px 10px;font-size:.78em;font-weight:600">{test_category}</span>
                    {"<span style='background:" + area_color + ";color:#fff;border-radius:8px;padding:2px 10px;font-size:.78em;font-weight:700;letter-spacing:.3px'>" + epp_area + "</span>" if epp_area else ""}
                    {"<span style='background:#f0e6ff;color:#764ba2;border-radius:8px;padding:2px 10px;font-size:.78em;font-weight:600'>" + ac_ref + "</span>" if ac_ref else ""}
                </span>
            </div>
            <div class="tc-body">
                <div class="tc-section">
                    <div class="tc-label">Objective</div>
                    <div class="tc-content">{objective if objective else '<span class="na">N/A</span>'}</div>
                </div>
                <div class="tc-section">
                    <div class="tc-label">Preconditions</div>
                    <div class="tc-content">{tc['preconditions'].replace(chr(10), '<br>') if tc['preconditions'] else '<span class="na">N/A</span>'}</div>
                </div>
                <div class="tc-section">
                    <div class="tc-label">Test Steps &amp; Expected Results</div>
                    <div class="tc-content" style="padding:8px">{steps_table}</div>
                </div>
                <div class="tc-section">
                    <div class="tc-label">Overall Expected Result</div>
                    <div class="tc-content">{tc.get('overall_expected', '') if tc.get('overall_expected') else '<span class="na">N/A</span>'}</div>
                </div>
                <div class="tc-section" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px">
                    <div><div class="tc-label">Application</div><div class="tc-content">{tc.get('application_name','EPP')}</div></div>
                    <div><div class="tc-label">Module</div><div class="tc-content">{app_module or '<span class="na">N/A</span>'}</div></div>
                    <div><div class="tc-label">Review Status</div><div class="tc-content">{tc.get('review_status','NO')}</div></div>
                    <div><div class="tc-label">Automation State</div><div class="tc-content">{tc.get('automation_state','Non-Automatable')}</div></div>
                </div>
            </div>
        </div>'''

    # Parse AC list for display
    ac_items_html = ''
    if ctx['acceptance_criteria']:
        ac_blocks = []
        ac_pattern = re.split(r'(AC\d+:?)', ctx['acceptance_criteria'], flags=re.IGNORECASE)
        current = ''
        for part in ac_pattern:
            if re.match(r'AC\d+:?', part, re.IGNORECASE):
                if current.strip():
                    ac_blocks.append(current.strip())
                current = part
            else:
                current += part
        if current.strip():
            ac_blocks.append(current.strip())
        for i, ac in enumerate(ac_blocks, 1):
            ac_items_html += f'<div class="ac-item"><span class="ac-num">{i}</span>{ac}</div>'

    # ── Historical context panel (RULE HIST 15) ──────────────────────────
    # Renders ONCE at the top of the page so testers can see which
    # neighbouring User Stories and EPP domain keywords influenced the
    # generated test cases — instead of repeating that info on every TC.
    history = ctx.get('history') or {}
    history_panel_html = ''
    h_neighbours = history.get('neighbour_stories') or []
    h_kws = history.get('neighbour_domain_keywords') or []
    if h_neighbours or h_kws:
        kw_chips = ''.join(
            f'<span class="hk-chip">{k.capitalize()}</span>'
            for k in h_kws[:12]
        )
        neighbour_rows = ''
        for n in h_neighbours[:6]:
            nid = n.get('id')
            ntitle = (n.get('title') or '').replace('<', '&lt;').replace('>', '&gt;')
            nstate = n.get('state') or ''
            ntags = (n.get('tags') or '').replace(';', ' · ')
            if not nid:
                continue
            neighbour_rows += (
                f'<div class="hn-row">'
                f'<span class="hn-id">#{nid}</span>'
                f'<span class="hn-title">{ntitle}</span>'
                f'<span class="hn-state">{nstate}</span>'
                f'<span class="hn-tags">{ntags}</span>'
                f'</div>'
            )
        summary_text = history.get('summary') or ''
        history_panel_html = (
            '<div class="info-panel history-panel">'
            '<h2>Historical Context Used</h2>'
            '<p class="hp-sub">Prior-art from neighbouring User Stories in the same Area Path '
            'was used to <strong>enrich</strong> (not duplicate) the test cases below.</p>'
            + (f'<div class="hp-summary">{summary_text}</div>' if summary_text else '')
            + (f'<div class="hp-section-label">Domain keywords inherited</div>'
               f'<div class="hk-list">{kw_chips}</div>' if kw_chips else '')
            + (f'<div class="hp-section-label">Neighbouring User Stories</div>'
               f'<div class="hn-list">{neighbour_rows}</div>' if neighbour_rows else '')
            + '</div>'
        )

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate, max-age=0">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<title>Review Test Cases - US #{ctx['story_id']}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',sans-serif;background:#f0f2f5;color:#1a1a2e;min-height:100vh}}
.top-bar{{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;padding:28px 0;text-align:center}}
.top-bar h1{{font-size:1.7em;font-weight:700}}
.top-bar .sub{{opacity:.8;margin-top:6px;font-size:1em}}
.container{{max-width:1060px;margin:-20px auto 40px;padding:0 20px}}

.info-panel{{background:#fff;border-radius:14px;padding:24px 28px;margin-bottom:22px;box-shadow:0 4px 16px rgba(0,0,0,.06)}}
.info-panel h2{{font-size:1.15em;color:#764ba2;margin-bottom:12px;border-bottom:2px solid #f0e6ff;padding-bottom:8px}}
.info-row{{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:8px}}
.info-row .lbl{{font-weight:600;color:#555;min-width:100px}}
.info-row .val{{color:#222}}

.ac-item{{background:#f8f9ff;border-left:4px solid #667eea;border-radius:6px;padding:10px 14px;margin-bottom:8px;font-size:.95em}}
.ac-num{{background:#667eea;color:#fff;border-radius:50%;width:22px;height:22px;display:inline-flex;align-items:center;justify-content:center;font-size:.8em;font-weight:700;margin-right:10px}}

.toolbar{{background:#fff;border-radius:14px;padding:18px 28px;margin-bottom:22px;box-shadow:0 4px 16px rgba(0,0,0,.06);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}}
.toolbar .left{{display:flex;gap:14px;align-items:center}}
.toolbar .count{{font-size:.95em;color:#666}}
.select-btns button{{background:#f0f2f5;border:1px solid #ddd;border-radius:8px;padding:6px 14px;cursor:pointer;font-size:.9em;transition:background .2s}}
.select-btns button:hover{{background:#e8eaf0}}

.add-btn{{background:linear-gradient(135deg,#43a047,#2e7d32);color:#fff;border:none;border-radius:12px;padding:14px 36px;font-size:1.1em;font-weight:600;cursor:pointer;transition:transform .2s,box-shadow .2s;box-shadow:0 4px 16px rgba(46,125,50,.3)}}
.add-btn:hover{{transform:translateY(-2px);box-shadow:0 8px 28px rgba(46,125,50,.4)}}
.add-btn:disabled{{opacity:.5;cursor:not-allowed;transform:none;box-shadow:none}}

.tc-card{{background:#fff;border-radius:14px;padding:0;margin-bottom:18px;box-shadow:0 4px 16px rgba(0,0,0,.06);overflow:hidden;transition:box-shadow .2s;border:2px solid transparent}}
.tc-card.checked{{border-color:#667eea}}
.tc-card.unchecked{{opacity:.55}}
.tc-header{{display:flex;align-items:center;gap:14px;padding:18px 24px;background:#f8f9ff;border-bottom:1px solid #f0f1f5;cursor:pointer}}
.tc-checkbox{{position:relative;display:flex;align-items:center}}
.tc-checkbox input{{width:20px;height:20px;accent-color:#667eea;cursor:pointer}}
.tc-number{{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border-radius:8px;padding:5px 12px;font-weight:700;font-size:.9em;white-space:nowrap}}
.tc-title{{font-size:1.05em;font-weight:600;color:#2c3e50}}
.tc-body{{padding:20px 24px}}
.tc-section{{margin-bottom:14px}}
.tc-section:last-child{{margin-bottom:0}}
.tc-label{{font-weight:600;color:#764ba2;font-size:.92em;margin-bottom:6px}}
.tc-content{{background:#f8f9ff;border-radius:8px;padding:12px 16px;border:1px solid #f0e6ff;font-size:.95em;line-height:1.6}}
.tc-content ul{{margin:0;padding-left:20px}}
.tc-content li{{margin-bottom:6px}}
.na{{color:#bbb}}

.result-overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:1000;align-items:center;justify-content:center}}
.result-overlay.show{{display:flex}}
.result-box{{background:#fff;border-radius:16px;padding:36px 44px;max-width:600px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,.2);text-align:center}}
.result-box h2{{color:#2e7d32;margin-bottom:16px}}
.result-list{{text-align:left;margin:16px 0}}
.result-item{{padding:8px 12px;border-radius:8px;margin-bottom:6px;display:flex;align-items:center;gap:10px}}
.result-item.ok{{background:#e8f5e9}}
.result-item.fail{{background:#ffebee}}
.close-btn{{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border:none;border-radius:10px;padding:10px 28px;font-size:1em;cursor:pointer;margin-top:14px}}

.spinner{{display:none;width:24px;height:24px;border:3px solid #ccc;border-top-color:#2e7d32;border-radius:50%;animation:spin .8s linear infinite;margin-left:12px}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}

/* ── Historical context panel (RULE HIST 15) ───────────────────────── */
.history-panel{{border-left:4px solid #764ba2;background:linear-gradient(180deg,#fff,#faf7ff)}}
.history-panel h2{{color:#764ba2}}
.hp-sub{{color:#555;font-size:.92em;margin-bottom:10px}}
.hp-summary{{display:inline-block;background:#f0e6ff;color:#4527a0;border-radius:8px;padding:4px 12px;font-size:.85em;font-weight:600;margin-bottom:12px}}
.hp-section-label{{font-weight:600;color:#764ba2;font-size:.9em;margin:14px 0 6px}}
.hk-list{{display:flex;flex-wrap:wrap;gap:6px}}
.hk-chip{{background:#fff;color:#4527a0;border:1px solid #d1c4e9;border-radius:14px;padding:3px 10px;font-size:.82em;font-weight:600}}
.hn-list{{display:flex;flex-direction:column;gap:6px}}
.hn-row{{display:grid;grid-template-columns:70px 1fr auto auto;gap:10px;align-items:center;background:#fff;border:1px solid #ede7f6;border-radius:8px;padding:6px 12px;font-size:.9em}}
.hn-id{{color:#764ba2;font-weight:700}}
.hn-title{{color:#222;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.hn-state{{background:#e8f5e9;color:#2e7d32;border-radius:6px;padding:2px 8px;font-size:.78em;font-weight:600}}
.hn-tags{{color:#999;font-size:.78em}}
</style>
</head>
<body>
<div class="top-bar">
    <h1>Review Generated Test Cases</h1>
    <div class="sub">User Story #{ctx['story_id']}: {ctx['title']}</div>
</div>
<div class="container">

    <div class="info-panel">
        <h2>User Story Details</h2>
        <div class="info-row"><span class="lbl">ID:</span><span class="val">#{ctx['story_id']}</span></div>
        <div class="info-row"><span class="lbl">Title:</span><span class="val">{ctx['title']}</span></div>
        <div class="info-row"><span class="lbl">State:</span><span class="val">{ctx['state']}</span></div>
        <div class="info-row"><span class="lbl">Assigned To:</span><span class="val">{ctx['assignee']}</span></div>
        {f'<div class="info-row"><span class="lbl">Description:</span><span class="val">{ctx["description"][:300]}</span></div>' if ctx['description'] else ''}
    </div>

    {history_panel_html}

    {f'<div class="info-panel"><h2>Acceptance Criteria</h2>{ac_items_html}</div>' if ac_items_html else ''}

    <div class="toolbar">
        <div class="left">
            <span class="count"><strong id="checkedCount">{len(ctx['test_cases'])}</strong> / {len(ctx['test_cases'])} test cases selected</span>
            <span class="select-btns">
                <button onclick="selectAll()">Select All</button>
                <button onclick="deselectAll()">Deselect All</button>
            </span>
        </div>
        <div>
            <button class="add-btn" id="addBtn" onclick="addToADO()">Add to ADO</button>
            <span class="spinner" id="spinner"></span>
        </div>
    </div>

    {tc_cards_html}

</div>

<div class="result-overlay" id="resultOverlay">
    <div class="result-box">
        <h2 id="resultTitle">Results</h2>
        <div class="result-list" id="resultList"></div>
        <button class="close-btn" onclick="document.getElementById('resultOverlay').classList.remove('show')">Close</button>
    </div>
</div>

<script>
function updateCount(){{
    const boxes=document.querySelectorAll('.tc-card input[type=checkbox]');
    let c=0;
    boxes.forEach(b=>{{
        const card=b.closest('.tc-card');
        if(b.checked){{c++;card.classList.add('checked');card.classList.remove('unchecked')}}
        else{{card.classList.remove('checked');card.classList.add('unchecked')}}
    }});
    document.getElementById('checkedCount').textContent=c;
    document.getElementById('addBtn').disabled=c===0;
}}
function selectAll(){{document.querySelectorAll('.tc-card input[type=checkbox]').forEach(b=>b.checked=true);updateCount()}}
function deselectAll(){{document.querySelectorAll('.tc-card input[type=checkbox]').forEach(b=>b.checked=false);updateCount()}}
document.querySelectorAll('.tc-card input[type=checkbox]').forEach(b=>b.addEventListener('change',updateCount));
updateCount();

function addToADO(){{
    const boxes=document.querySelectorAll('.tc-card input[type=checkbox]:checked');
    const indices=Array.from(boxes).map(b=>parseInt(b.dataset.idx));
    const uids=Array.from(boxes).map(b=>b.dataset.uid);
    if(indices.length===0)return;

    const btn=document.getElementById('addBtn');
    const spinner=document.getElementById('spinner');
    btn.disabled=true;btn.textContent='Adding to ADO...';spinner.style.display='inline-block';

    fetch('/add-to-ado',{{
        method:'POST',
        headers:{{'Content-Type':'application/json','Cache-Control':'no-cache'}},
        cache:'no-store',
        body:JSON.stringify({{indices:indices,uids:uids,session_id:'{ctx['session_id']}'}})
    }})
    .then(r=>{{
        if(r.status===409){{
            return r.json().then(d=>{{
                alert(d.message||'This review page is stale. Please reload (Ctrl+F5) and try again.');
                location.reload(true);
                return null;
            }});
        }}
        return r.json();
    }})
    .then(data=>{{
        if(!data)return;
        spinner.style.display='none';btn.textContent='Add to ADO';btn.disabled=false;
        const overlay=document.getElementById('resultOverlay');
        const list=document.getElementById('resultList');
        const title=document.getElementById('resultTitle');
        const ok=data.results.filter(r=>r.success).length;
        title.textContent=ok+' / '+data.results.length+' Test Cases Added to ADO';
        list.innerHTML=data.results.map(r=>
            '<div class="result-item '+(r.success?'ok':'fail')+'">'
            +(r.success?'&#9989;':'&#10060;')+' '
            +(r.success?'TC #'+r.tc_id+' - ':'')+r.title
            +'</div>'
        ).join('');
        overlay.classList.add('show');
    }})
    .catch(err=>{{
        spinner.style.display='none';btn.textContent='Add to ADO';btn.disabled=false;
        alert('Error: '+err.message);
    }});
}}
</script>
</body>
</html>'''


# ── Debug ─────────────────────────────────────────────────────────────────────

def debug_work_item(work_item_id):
    """Debug function to see all fields of a work item."""
    work_item = get_work_item_full_details(work_item_id)
    if work_item:
        print("\n=== DEBUG: Work Item Fields ===")
        fields = work_item.get('fields', {})
        for key, value in fields.items():
            if value and isinstance(value, str) and len(value) > 0:
                print(f"\n{key}:")
                print(f"  {value[:500]}..." if len(str(value)) > 500 else f"  {value}")
    return work_item


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    try:
        # If a user story ID is passed as argument, generate and push test cases
        if len(sys.argv) > 1 and sys.argv[1].isdigit():
            story_id = int(sys.argv[1])
            generate_and_push_test_cases(story_id)
            return

        print(f"Checking project: {ADO_PROJECT}")
        project_info = get_project_info()
        pools = get_agent_pools()
        builds = get_pipeline_stats()
        print("\n--- Azure DevOps Advisor Recommendations ---")
        for rec in analyze_and_recommend(project_info, pools, builds):
            print(f"- {rec}")
        print_sprint_report(export_pdf=False, export_html=True)
    except Exception as e:
        print("Error:", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
