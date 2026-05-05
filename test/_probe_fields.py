"""Probe an existing Test Case in ADO to discover the correct field reference
names used by the project's process template (esp. the Preconditions field)."""
import os, base64, json, sys
import requests, urllib3
urllib3.disable_warnings()

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

org = os.environ['ADO_ORG']
pat = os.environ['ADO_PAT']
proj = os.environ['ADO_PROJECT']
b = base64.b64encode(f':{pat}'.encode()).decode()
h = {'Authorization': f'Basic {b}'}

# 1. Find the most recent existing Test Case
wiql = {
    "query": ("SELECT [System.Id] FROM WorkItems "
              "WHERE [System.WorkItemType]='Test Case' "
              "AND [System.TeamProject]=@project "
              "ORDER BY [System.Id] DESC")
}
r = requests.post(
    f"https://dev.azure.com/{org}/{proj}/_apis/wit/wiql?api-version=7.1",
    headers={**h, 'Content-Type': 'application/json'},
    json=wiql, verify=False, timeout=30,
)
items = r.json().get('workItems', [])
if not items:
    print("No Test Cases found in this project.")
    sys.exit(1)
tc_id = items[0]['id']
print(f"Sample Test Case: #{tc_id}")

# 2. Get its full fields
r2 = requests.get(
    f"https://dev.azure.com/{org}/_apis/wit/workitems/{tc_id}?$expand=all&api-version=7.1",
    headers=h, verify=False, timeout=30,
)
fields = r2.json().get('fields', {})

print("\nFields possibly related to Preconditions / TCM:")
for k, v in fields.items():
    kl = k.lower()
    if 'pre' in kl or 'condition' in kl or 'tcm' in kl or 'objective' in kl or 'summary' in kl:
        sample = str(v)[:120].replace('\n', ' ')
        print(f"  {k} = {sample}")

# 3. Also list all field reference names available on Test Case work item type
print("\nQuerying Test Case work item type definition...")
r3 = requests.get(
    f"https://dev.azure.com/{org}/{proj}/_apis/wit/workitemtypes/Test%20Case/fields?api-version=7.1",
    headers=h, verify=False, timeout=30,
)
defs = r3.json().get('value', [])
print(f"\nAll fields on Test Case ({len(defs)}):")
for d in defs:
    ref = d.get('referenceName', '')
    name = d.get('name', '')
    if any(t in ref.lower() or t in name.lower() for t in ['pre', 'condition', 'objective', 'summary', 'description']):
        print(f"  {ref}  ({name})")
