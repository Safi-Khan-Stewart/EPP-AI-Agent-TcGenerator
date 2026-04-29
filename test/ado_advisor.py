import requests
import sys
import os
import base64
import urllib.parse
from datetime import datetime
import re
from fpdf import FPDF
from io import BytesIO
from jinja2 import Template
import urllib3

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

def generate_test_cases_from_acceptance_criteria(work_item):
    """
    Rules-based test case generator.  Follows every rule in Rules.md.
    Returns (test_cases_list, ac_clean, desc_clean, title).
    """
    if not work_item:
        return [], '', '', ''

    fields = work_item.get('fields', {})
    title = fields.get('System.Title', '')
    description = fields.get('System.Description', '')
    acceptance_criteria = fields.get('Microsoft.VSTS.Common.AcceptanceCriteria', '')

    ac_clean = clean_html(acceptance_criteria) if acceptance_criteria else ''
    desc_clean = clean_html(description) if description else ''
    combined = (title + ' ' + desc_clean + ' ' + ac_clean).lower()

    # ── Parse acceptance criteria blocks ───────────────────────────────────
    ac_blocks = _parse_ac_blocks(ac_clean)

    # ── Detect story characteristics for rule application ─────────────────
    has_roles = any(kw in combined for kw in ['admin', 'role', 'permission', 'user role', 'manager', 'approver', 'unauthorized'])
    has_data_input = any(kw in combined for kw in ['input', 'enter', 'form', 'field', 'submit', 'upload', 'fill', 'type', 'select', 'dropdown'])
    has_ui = any(kw in combined for kw in ['button', 'click', 'screen', 'page', 'modal', 'dialog', 'menu', 'tab', 'display', 'ui', 'dropdown', 'tooltip', 'grid', 'table'])
    has_save = any(kw in combined for kw in ['save', 'submit', 'create', 'update', 'edit', 'add', 'post', 'put'])
    has_cancel = any(kw in combined for kw in ['cancel', 'back', 'discard', 'close', 'reset'])
    has_messages = any(kw in combined for kw in ['message', 'toast', 'notification', 'alert', 'error', 'success', 'warning', 'confirm'])
    has_navigation = any(kw in combined for kw in ['navigate', 'redirect', 'route', 'link', 'menu', 'breadcrumb', 'tab'])

    # Detect roles mentioned
    roles_found = []
    for role_kw in ['admin', 'administrator', 'manager', 'approver', 'reviewer', 'user', 'operator', 'viewer', 'editor']:
        if role_kw in combined:
            roles_found.append(role_kw.capitalize())
    if not roles_found:
        roles_found = ['Authorized User']

    test_cases = []
    tc_counter = [0]  # mutable counter

    def next_tc_id():
        tc_counter[0] += 1
        return f"TC-{tc_counter[0]:03d}"

    # ══════════════════════════════════════════════════════════════════════
    # RULE-COV-01 / RULE-GEN-03: 2 test cases per AC (min 1, max 4)
    # RULE-COV-02: Validate Given/When/Then without prefixes
    # ══════════════════════════════════════════════════════════════════════
    for i, ac_block in enumerate(ac_blocks, 1):
        given_match = re.search(r'GIVEN\s+(.+?)(?=WHEN|THEN|$)', ac_block, re.IGNORECASE | re.DOTALL)
        when_match = re.search(r'WHEN\s+(.+?)(?=THEN|$)', ac_block, re.IGNORECASE | re.DOTALL)
        then_match = re.search(r'THEN\s+(.+?)$', ac_block, re.IGNORECASE | re.DOTALL)

        given_text = given_match.group(1).strip() if given_match else ''
        when_text = when_match.group(1).strip() if when_match else ''
        then_text = then_match.group(1).strip() if then_match else ''

        ac_summary = ac_block[:100].replace('\n', ' ').strip()
        if ac_summary.upper().startswith('AC'):
            ac_summary = ac_summary.split(':', 1)[-1].strip() if ':' in ac_summary else ac_summary[4:].strip()

        # ── TC 1: Positive / happy path per AC ────────────────────────────
        steps_pos = []
        if given_text:
            steps_pos.append(f"Ensure {given_text}")
        if when_text:
            steps_pos.append(f"Perform action: {when_text}")
        if then_text:
            steps_pos.append(f"Verify {then_text}")
        if not steps_pos:
            steps_pos = [
                "Navigate to the relevant feature",
                f"Execute the scenario: {ac_summary[:120]}",
                "Verify the expected outcome is achieved"
            ]
        test_cases.append({
            'title': f"[{next_tc_id()}] Verify {ac_summary[:80]}",
            'preconditions': given_text if given_text else "User is logged in with appropriate permissions",
            'steps': steps_pos,
            'expected': then_text if then_text else f"System behaves as specified in AC{i}",
            'overall_expected': f"AC{i} is fully satisfied",
            'postconditions': "System state is updated correctly",
            'priority': 'High',
            'test_type': 'Functional',
            'ac_ref': f'AC{i}',
        })

        # ── TC 2: Negative / boundary per AC ──────────────────────────────
        steps_neg = []
        if given_text:
            steps_neg.append(f"Ensure {given_text}")
        steps_neg.append(f"Attempt the action with invalid or missing data related to: {ac_summary[:80]}")
        steps_neg.append("Verify an appropriate error message is displayed")
        steps_neg.append("Verify the system does not save invalid data")
        test_cases.append({
            'title': f"[{next_tc_id()}] Verify error handling for {ac_summary[:70]}",
            'preconditions': given_text if given_text else "User is logged in",
            'steps': steps_neg,
            'expected': "System rejects invalid input and shows a clear error message",
            'overall_expected': f"AC{i} negative path is validated",
            'postconditions': "No unintended data is persisted",
            'priority': 'High',
            'test_type': 'Negative',
            'ac_ref': f'AC{i}',
        })

    # ══════════════════════════════════════════════════════════════════════
    # RULE-GEN-03: 2 happy-path positives (if not already covered by ACs)
    # ══════════════════════════════════════════════════════════════════════
    happy_count = sum(1 for tc in test_cases if tc['test_type'] == 'Functional')
    if happy_count < 2:
        for _ in range(2 - happy_count):
            test_cases.append({
                'title': f"[{next_tc_id()}] Verify {title[:70]} completes successfully",
                'preconditions': "User is logged in with authorized role",
                'steps': [
                    "Navigate to the feature described in the user story",
                    "Perform the primary action with valid data",
                    "Verify the operation completes successfully",
                    "Verify confirmation/success feedback is shown"
                ],
                'expected': "Feature works as described in the user story",
                'overall_expected': "Happy path is validated end-to-end",
                'postconditions': "System state is updated accordingly",
                'priority': 'High',
                'test_type': 'Functional',
                'ac_ref': 'All ACs',
            })

    # ══════════════════════════════════════════════════════════════════════
    # RULE-GEN-03: At least 1 negative/boundary/edge/unauthorized test
    # ══════════════════════════════════════════════════════════════════════
    neg_count = sum(1 for tc in test_cases if tc['test_type'] in ('Negative', 'Boundary'))
    if neg_count < 1:
        test_cases.append({
            'title': f"[{next_tc_id()}] Verify unauthorized access is denied for {title[:60]}",
            'preconditions': "User is logged in with an unauthorized role",
            'steps': [
                "Log in with a user that does NOT have the required permissions",
                "Attempt to access or perform the feature action",
                "Verify access is denied with an appropriate message",
                "Verify no data changes occur"
            ],
            'expected': "Unauthorized users cannot access the feature",
            'overall_expected': "Security boundary is enforced",
            'postconditions': "No data corruption; access attempt is logged",
            'priority': 'High',
            'test_type': 'Negative',
            'ac_ref': 'Security',
        })

    # ══════════════════════════════════════════════════════════════════════
    # RULE-COV-03: Role-based test cases
    # ══════════════════════════════════════════════════════════════════════
    if has_roles and len(roles_found) > 1:
        for role in roles_found[:3]:
            test_cases.append({
                'title': f"[{next_tc_id()}] Verify {title[:50]} as {role}",
                'preconditions': f"User is logged in with the {role} role",
                'steps': [
                    f"Log in as a user with {role} role",
                    "Navigate to the feature",
                    f"Perform the action as {role}",
                    f"Verify the behavior matches what is expected for the {role} role"
                ],
                'expected': f"Feature behaves correctly for the {role} role",
                'overall_expected': f"Role-specific behavior for {role} is validated",
                'postconditions': "N/A",
                'priority': 'Medium',
                'test_type': 'Functional',
                'ac_ref': 'Role-based',
            })

    # ══════════════════════════════════════════════════════════════════════
    # RULE-COV-04: Data input test cases
    # ══════════════════════════════════════════════════════════════════════
    if has_data_input:
        data_tests = [
            ("valid data", "Enter all fields with valid data and submit", "Data is accepted and saved", "Functional"),
            ("invalid data", "Enter fields with invalid data (wrong format, out-of-range) and submit", "Validation errors are displayed; data is not saved", "Negative"),
            ("empty/null input", "Leave all required fields empty and submit", "Required-field validation errors are displayed", "Boundary"),
            ("special characters", "Enter special characters (!@#$%^&*) in text fields and submit", "System handles special characters correctly (sanitize or accept)", "Boundary"),
            ("max/min length", "Enter values at maximum and minimum allowed lengths and submit", "System accepts boundary-length values correctly", "Boundary"),
        ]
        for label, action, expected, ttype in data_tests:
            test_cases.append({
                'title': f"[{next_tc_id()}] Verify {title[:50]} with {label}",
                'preconditions': "User is logged in; data entry form is accessible",
                'steps': [
                    "Navigate to the data entry form/screen",
                    action,
                    f"Verify: {expected}"
                ],
                'expected': expected,
                'overall_expected': f"Data input {label} scenario is validated",
                'postconditions': "System state reflects the correct outcome",
                'priority': 'Medium',
                'test_type': ttype,
                'ac_ref': 'Data Input',
            })

    # ══════════════════════════════════════════════════════════════════════
    # RULE-FUNC-01: UI elements validation
    # ══════════════════════════════════════════════════════════════════════
    if has_ui:
        test_cases.append({
            'title': f"[{next_tc_id()}] Verify UI elements for {title[:60]}",
            'preconditions': "User is logged in; feature screen is accessible",
            'steps': [
                "Navigate to the feature screen",
                "Verify all buttons, dropdowns, forms, and modals are present and correctly labeled",
                "Verify enabled/disabled states match the current context",
                "Verify tooltips and placeholder text are correct",
                "Verify keyboard navigation and tab order"
            ],
            'expected': "All UI elements are present, correctly styled, and functional",
            'overall_expected': "UI elements comply with design specifications",
            'postconditions': "N/A",
            'priority': 'Medium',
            'test_type': 'UI',
            'ac_ref': 'UI',
        })

    # ══════════════════════════════════════════════════════════════════════
    # RULE-FUNC-02: Navigation flow
    # ══════════════════════════════════════════════════════════════════════
    if has_navigation:
        test_cases.append({
            'title': f"[{next_tc_id()}] Verify navigation flow for {title[:60]}",
            'preconditions': "User is logged in",
            'steps': [
                "Start from the application entry point (dashboard/home)",
                "Navigate to the feature using the expected path (menu/link/button)",
                "Complete the feature workflow",
                "Verify the user is redirected to the correct exit point",
                "Verify browser back/forward buttons work correctly"
            ],
            'expected': "Navigation flow from entry to exit point works as expected",
            'overall_expected': "Complete navigation path is validated",
            'postconditions': "N/A",
            'priority': 'Medium',
            'test_type': 'Functional',
            'ac_ref': 'Navigation',
        })

    # ══════════════════════════════════════════════════════════════════════
    # RULE-FUNC-03: Messages validation
    # ══════════════════════════════════════════════════════════════════════
    if has_messages:
        test_cases.append({
            'title': f"[{next_tc_id()}] Verify messages and notifications for {title[:55]}",
            'preconditions': "User is logged in; feature is accessible",
            'steps': [
                "Perform a successful action and verify the success message/toast appears",
                "Perform an invalid action and verify the error message appears",
                "Verify messages auto-dismiss or can be dismissed manually",
                "Verify message text is clear and user-friendly"
            ],
            'expected': "All success, error, and informational messages display correctly",
            'overall_expected': "Messaging behavior is validated",
            'postconditions': "N/A",
            'priority': 'Medium',
            'test_type': 'Functional',
            'ac_ref': 'Messages',
        })

    # ══════════════════════════════════════════════════════════════════════
    # RULE-FUNC-04: Data persistence
    # ══════════════════════════════════════════════════════════════════════
    if has_save:
        test_cases.append({
            'title': f"[{next_tc_id()}] Verify data persists after save/submit for {title[:50]}",
            'preconditions': "User is logged in; data entry form is accessible",
            'steps': [
                "Enter valid data in all fields",
                "Click Save/Submit",
                "Navigate away from the page",
                "Return to the same page/record",
                "Verify all previously entered data is correctly persisted"
            ],
            'expected': "Data is saved correctly and persists after navigation",
            'overall_expected': "Data persistence is validated",
            'postconditions': "Data is stored in the system",
            'priority': 'High',
            'test_type': 'Functional',
            'ac_ref': 'Persistence',
        })

    # ══════════════════════════════════════════════════════════════════════
    # RULE-FUNC-05: Cancel/back does NOT save
    # ══════════════════════════════════════════════════════════════════════
    if has_cancel or has_save:
        test_cases.append({
            'title': f"[{next_tc_id()}] Verify cancel/back does not save data for {title[:50]}",
            'preconditions': "User is logged in; data entry form is accessible",
            'steps': [
                "Enter data in the form fields",
                "Click Cancel or navigate back without saving",
                "Return to the same page/record",
                "Verify that the unsaved data was NOT persisted"
            ],
            'expected': "No data is saved when user cancels or navigates back",
            'overall_expected': "Cancel/back behavior is validated",
            'postconditions': "No unintended data in the system",
            'priority': 'Medium',
            'test_type': 'Functional',
            'ac_ref': 'Cancel/Back',
        })

    # ══════════════════════════════════════════════════════════════════════
    # RULE-GEN-04: Club similar-outcome test cases  (deduplicate by title prefix)
    # ══════════════════════════════════════════════════════════════════════
    seen_keys = set()
    deduped = []
    for tc in test_cases:
        key = tc['title'][10:50]  # ignore [TC-NNN] prefix, compare core
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(tc)
    test_cases = deduped

    return test_cases, ac_clean, desc_clean, title


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
    Convert a list of step strings into the Azure DevOps TCM Steps XML format.
    ADO stores steps in Microsoft.VSTS.TCM.Steps as XML like:
      <steps id="0" last="N">
        <step id="1" type="ActionStep"><parameterizedString isformatted="true">...</parameterizedString>
          <parameterizedString isformatted="true">expected</parameterizedString></step>
        ...
      </steps>
    """
    if isinstance(steps, str):
        # If steps is an HTML string, extract text from <li> tags
        items = re.findall(r'<li>(.*?)</li>', steps, re.DOTALL)
        if not items:
            items = [steps]
        steps = items

    xml_steps = []
    for idx, step_text in enumerate(steps, 1):
        step_text_clean = step_text.strip()
        # Last step gets the expected result
        exp = expected if idx == len(steps) else ''
        xml_steps.append(
            f'<step id="{idx}" type="ActionStep">'
            f'<parameterizedString isformatted="true">{step_text_clean}</parameterizedString>'
            f'<parameterizedString isformatted="true">{exp}</parameterizedString>'
            f'</step>'
        )
    last_id = len(steps)
    return f'<steps id="0" last="{last_id}">{"".join(xml_steps)}</steps>'


def create_test_case_in_ado(tc_title, steps_xml, preconditions_html, area_path, iteration_path):
    """
    Create a Test Case work item in Azure DevOps.
    Returns the created work item JSON, or None on failure.
    """
    org = urllib.parse.quote(ADO_ORG)
    project = urllib.parse.quote(ADO_PROJECT)
    url = f"https://dev.azure.com/{org}/{project}/_apis/wit/workitems/$Test%20Case?api-version=7.1"

    patch_doc = [
        {"op": "add", "path": "/fields/System.Title", "value": tc_title},
        {"op": "add", "path": "/fields/Microsoft.VSTS.TCM.Steps", "value": steps_xml},
        {"op": "add", "path": "/fields/System.AreaPath", "value": area_path},
        {"op": "add", "path": "/fields/System.IterationPath", "value": iteration_path},
        # RULE-FUNC-07: Tag every AI-generated test case with Gen-AI
        {"op": "add", "path": "/fields/System.Tags", "value": "Gen-AI"},
    ]

    patch_headers = {
        'Content-Type': 'application/json-patch+json',
        'Authorization': f'Basic {b64_pat}'
    }

    try:
        resp = requests.post(url, headers=patch_headers, json=patch_doc, verify=False, timeout=30)
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

    # 2. Generate test cases
    test_cases_raw, ac_clean, desc_clean, _ = generate_test_cases_from_acceptance_criteria(work_item)
    if not test_cases_raw:
        print("WARNING: No test cases could be generated.")
        return

    print(f"  Generated {len(test_cases_raw)} test cases.")

    # Prepare test cases data for JSON serialization
    tc_data_list = []
    for idx, tc in enumerate(test_cases_raw):
        steps_list = tc['steps'] if isinstance(tc['steps'], list) else [tc['steps']]
        tc_data_list.append({
            'index': idx,
            'title': tc['title'],
            'preconditions': tc.get('preconditions', ''),
            'steps': steps_list,
            'expected': tc.get('expected', ''),
            'overall_expected': tc.get('overall_expected', ''),
            'postconditions': tc.get('postconditions', ''),
            'priority': tc.get('priority', 'Medium'),
            'test_type': tc.get('test_type', 'Functional'),
            'ac_ref': tc.get('ac_ref', ''),
        })

    story_context = {
        'story_id': story_id,
        'title': title,
        'state': state,
        'assignee': assignee,
        'area_path': area_path,
        'iteration_path': iteration_path,
        'description': desc_clean,
        'acceptance_criteria': ac_clean,
        'test_cases': tc_data_list,
    }

    # ── Build Review HTML ──────────────────────────────────────────────────
    review_html = _build_review_html(story_context)
    review_file = f"review_test_cases_US{story_id}.html"
    with open(review_file, 'w', encoding='utf-8') as f:
        f.write(review_html)

    # ── Local server to handle the "Add to ADO" action ─────────────────────
    server_result = {'done': False}

    class ReviewHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # suppress server logs

        def do_GET(self):
            if self.path == '/' or self.path == '/review':
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                with open(review_file, 'r', encoding='utf-8') as f:
                    self.wfile.write(f.read().encode('utf-8'))
            elif self.path == '/status':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'ready'}).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path == '/add-to-ado':
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length).decode('utf-8')
                selected = json.loads(body)
                selected_indices = selected.get('indices', [])

                print(f"\n  Received request to add {len(selected_indices)} test cases to ADO...")

                results = []
                for sel_idx in selected_indices:
                    tc = tc_data_list[sel_idx]
                    tc_title = f"[Auto] US#{story_id} - {tc['title']}"
                    preconditions = tc.get('preconditions', '')
                    full_steps = []
                    if preconditions:
                        full_steps.append(f"[Precondition] {preconditions.replace(chr(10), ' | ')}")
                    full_steps.extend(tc['steps'])
                    steps_xml = format_steps_as_ado_xml(full_steps, tc.get('expected', ''))
                    preconditions_html = f"<div>{preconditions.replace(chr(10), '<br>')}</div>" if preconditions else ''

                    print(f"  Creating: {tc_title[:70]}...")
                    result = create_test_case_in_ado(tc_title, steps_xml, preconditions_html, area_path, iteration_path)
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
                print(f"\n  Done: {len(created)}/{len(selected_indices)} test cases created in ADO.")
                server_result['done'] = True
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

    print(f"\n  Review page: http://localhost:{port}/review")
    print(f"  Opening in browser...")
    print(f"  (Select test cases, then click 'Add to ADO'. Press Ctrl+C to stop.)\n")

    webbrowser.open(f"http://localhost:{port}/review")

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
        steps_html = ''.join(f'<li>{s}</li>' for s in tc['steps'])
        priority = tc.get('priority', 'Medium')
        test_type = tc.get('test_type', 'Functional')
        ac_ref = tc.get('ac_ref', '')
        pri_color = {'High': '#e53935', 'Medium': '#fb8c00', 'Low': '#43a047'}.get(priority, '#888')
        tc_cards_html += f'''
        <div class="tc-card" data-index="{tc['index']}">
            <div class="tc-header">
                <label class="tc-checkbox">
                    <input type="checkbox" checked data-idx="{tc['index']}">
                    <span class="checkmark"></span>
                </label>
                <span class="tc-number">TC {tc['index']+1}</span>
                <span class="tc-title">{tc['title']}</span>
                <span style="margin-left:auto;display:flex;gap:8px;align-items:center;flex-shrink:0">
                    <span style="background:{pri_color};color:#fff;border-radius:8px;padding:2px 10px;font-size:.8em;font-weight:600">{priority}</span>
                    <span style="background:#667eea;color:#fff;border-radius:8px;padding:2px 10px;font-size:.8em;font-weight:600">{test_type}</span>
                    {"<span style='background:#f0e6ff;color:#764ba2;border-radius:8px;padding:2px 10px;font-size:.8em;font-weight:600'>" + ac_ref + "</span>" if ac_ref else ""}
                </span>
            </div>
            <div class="tc-body">
                <div class="tc-section">
                    <div class="tc-label">Preconditions</div>
                    <div class="tc-content">{tc['preconditions'].replace(chr(10), '<br>') if tc['preconditions'] else '<span class="na">N/A</span>'}</div>
                </div>
                <div class="tc-section">
                    <div class="tc-label">Test Steps</div>
                    <div class="tc-content"><ul>{steps_html}</ul></div>
                </div>
                <div class="tc-section">
                    <div class="tc-label">Expected Result</div>
                    <div class="tc-content">{tc['expected'] if tc['expected'] else '<span class="na">N/A</span>'}</div>
                </div>
                <div class="tc-section">
                    <div class="tc-label">Overall Expected Result</div>
                    <div class="tc-content">{tc.get('overall_expected', '') if tc.get('overall_expected') else '<span class="na">N/A</span>'}</div>
                </div>
                <div class="tc-section">
                    <div class="tc-label">Postconditions</div>
                    <div class="tc-content">{tc['postconditions'] if tc['postconditions'] else '<span class="na">N/A</span>'}</div>
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

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
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
    if(indices.length===0)return;

    const btn=document.getElementById('addBtn');
    const spinner=document.getElementById('spinner');
    btn.disabled=true;btn.textContent='Adding to ADO...';spinner.style.display='inline-block';

    fetch('/add-to-ado',{{
        method:'POST',
        headers:{{'Content-Type':'application/json'}},
        body:JSON.stringify({{indices:indices}})
    }})
    .then(r=>r.json())
    .then(data=>{{
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
