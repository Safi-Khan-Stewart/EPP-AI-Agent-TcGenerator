# ✅ Final Rules for AI-Based Test Case Generation (Azure DevOps)

These rules are the **single source of truth** for every test case generated against any user story.

---

## 🧱 SECTION 1: Test Case Structure & Standards

### RULE GEN 01: Mandatory Test Case Attributes
Every generated test case must include the following fields:

1. **Title** (clear, action-oriented, business-focused)
2. **Objective** (what business behavior is being validated)
3. **Preconditions**
4. **Test Steps**
5. **Expected Result** (for each step)
6. **Test Priority** (1, 2, 3, 4)
7. **Test Type** — one of:
   - Integration
   - Master
   - One-time validation
   - Performance
   - Regression
   - Smoke
   - Smoke & Regression
8. **Test Category** — one of:
   - API
   - Functional
   - Negative
9. **Test Case Review Status:** `NO`
10. **Automation State:** `Non-Automatable`
11. **Area Path** (ADO compatible)
12. **Iteration Path** (ADO compatible — auto-pick from US)
13. **ApplicationName:** `EPP`
14. **Application Module** (best match)

---

### RULE GEN 02: Test Case Title Standard
Test case titles must follow this format:

```
<Verify> <Actor> <Action> <Feature> <Condition / Business Rule>
```

✅ **Guidelines:**
- Start with **"Verify"**
- Use imperative language
- Avoid the word **"that"**
- Mention the role if role-based

✅ **Examples:**
- Verify users can login using valid credentials
- Verify Admin can approve invoices successfully
- Verify system blocks login for invalid password

---

## 📊 SECTION 2: Test Case Quantity & Distribution

### RULE GEN 03: Minimum Test Case Coverage per User Story
Each user story must generate at least:

1. **1 Happy Path** (positive) test case for authorized roles — *if applicable*
2. **1 Negative / Boundary / Edge case** (or unauthorized role) — *if applicable*
3. **1 test case per Acceptance Criterion (AC)**

✅ **Formula:**
```
Minimum Test Cases = max(X, Number of ACs + 1)
```

---

### RULE GEN 04: Test Case Clubbing
Test cases may be clubbed only if:

✅ **Allowed when:**
- Same role
- Same preconditions
- Same expected outcome
- Difference is data variation only

❌ **Not allowed when:**
- Different roles
- Different business rules
- Different ACs
- Different error handling

---

## 👥 SECTION 4: Role-Based Behavior

### RULE COV 07: Role-Based Test Generation
If a user story has role-based behavior:

- Generate **separate test cases per role** if actions are different; otherwise club the roles if possible.
- For every privileged role action:
  - Generate at least **one unauthorized role test** (if role applicable).

---

## 🧪 SECTION 5: Data & Input Validation

### RULE COV 08: Data-Driven Test Coverage
If a user story involves data input, generate tests based on field type and validation rules, including:

1. Valid data
2. Invalid data
3. Empty / Null input
4. Special characters
5. Maximum length
6. Minimum length

✅ Data generation must be **conditional, not blind**.

---

### RULE DATA 09: Test Data Management
Clearly specify the test data source:

- Static
- Generated
- API-created
- CSV-based

✅ **CSV files must include:**
- Header row
- Valid & invalid records
- Boundary values
- Comment/description column explaining intent

---

## 🖥️ SECTION 6: UI, API & Functional Validation

### RULE FUNC 10: UI & Field Validation
- Validate all UI elements mentioned in the user story.
- Validate:
  - Visibility
  - Enable/Disable state
  - Mandatory fields
  - Default values
- Ensure field mapping for all newly created test cases.

---

### RULE FUNC 11: Error Handling Validation
For every negative test, validate:

- Error message text
- Error placement
- Consistency with UX standards

---

## 🤖 SECTION 7: Automation & Maintainability

### RULE MAINT 12: Test Maintainability
AI must:

- Avoid hard-coded values unless explicitly required
- Use business terminology / UI labels / objectives
- Avoid redundant or repeated steps across test cases

---

### RULE HIST 15: Historical Context Awareness
Before generating test cases for a new User Story, the AI must:

1. Query ADO for **other recent User Stories under the same Area Path** (excluding the current one) using a WIQL query restricted to states like `QA Passed`, `Closed`, `Done`, `Dev Complete`, `Resolved`, and `QA In Progress`.
2. Prefer neighbours whose `System.Tags` contain the **same EPP area tag** (see RULE TAG 14) so the prior-art is in the same business domain.
3. Pull the `Tested By` Test Cases of those neighbours and extract their titles, steps, and most distinctive domain keywords (stop-words filtered).
4. **Filter** the extracted keywords through a curated EPP business vocabulary (`history_context._DOMAIN_VOCAB`) so only high-signal domain terms (e.g. `retry`, `reverse`, `consolidation`, `webhook`, `rbac`) are considered for enrichment.
5. Use that prior-art to **enrich the test cases that are already being generated** for the current story — never to produce standalone "historical" test cases, and never as boilerplate added to every TC. Specifically:
   - For each test case, at most **one** historical keyword is applied, and only **one** surface area is touched:
     - **AC-driven TC** → a short "(Also exercises the '<Keyword>' flow …)" hook is appended to its Objective.
     - **Negative / Security TC** → a "Historical baseline: prior stories in this area have hardened '<Keyword>' handling …" bullet is added to its Preconditions.
     - **Workflow / API TC** → an extra regression-anchor step ("Smoke-check the '<Keyword>' regression path …") is appended.
     - **Data-driven TC** → a "Data shapes should remain compatible with the '<Keyword>' coverage …" clause is appended to its Objective.
     - **Happy-Path / Role / generic TC** → a light "Keeps parity with the '<Keyword>' baseline …" clause is appended to its Objective.
     - **UI-only TC** → left untouched (no vocab term applies).
   - Keywords are chosen by **theme match** (negative / security / workflow / data / banking / onboarding) so the right keyword lands on the right TC.
   - Each keyword is used **at most once per generation run** so every enrichment carries unique information.
   - A single audit-trail bullet — "Historical enrichment applied: <keywords> — Reference prior stories: #<id>, #<id>" — is added to the **first** test case only, never repeated across the rest.
6. The number of generated test cases must **not increase** because of this rule — coverage stays determined by the AC, RULE GEN 03, RULE COV 07, and RULE COV 08.
7. The review HTML page renders a single **"Historical Context Used"** panel at the top, listing the neighbouring User Stories and the EPP domain keywords that shaped the generation — instead of repeating that information on every test case card.

✅ **Implementation reference:** `test/history_context.py → build_history_context()` (returns `neighbour_domain_keywords` filtered against `_DOMAIN_VOCAB`) plus the `# HISTORICAL CONTEXT (targeted enrichment, not addition)` block in `test/ado_advisor.py → generate_test_cases_from_acceptance_criteria()`. The story-level panel is built in `_build_review_html()` under the `# Historical context panel (RULE HIST 15)` comment.

✅ **Failure mode:** if the WIQL or batch fetch fails (transient network / auth issue), generation continues **without** historical context — never blocks the run.

---

## 🏷️ SECTION 8: ADO Tagging Convention (EPP)

### RULE TAG 13: Mandatory Test Case Tags
Every test case pushed to ADO **must** carry the following tags in `System.Tags` (semicolon-separated):

1. `Gen-AI` — origin marker for AI-generated content.
2. `AI TestCase` — mandatory generator tag (replaces the older `AI Test Case Generator`).
3. The `Test Type` value (split into one tag per word when combined, e.g. `Smoke & Regression` → `Smoke` + `Regression`).
4. The `Test Category` value (`Functional`, `API`, or `Negative`).
5. **Exactly one EPP area tag** from RULE TAG 14 below.

✅ Example:
```
Gen-AI; AI TestCase; Smoke; Regression; Functional; Resware_OB
```

---

### RULE TAG 14: EPP Area Tag (single tag, story-driven)
Pick exactly **one** tag based on the User Story's portal and feature area. Rules are evaluated **top-down — the first match wins** so the most specific rule is checked first.

| # | Tag         | Pick when the User Story is about… |
|---|-------------|------------------------------------|
| 1 | `STEPS_OB`  | **STEPS integration** combined with **outbound** payments |
| 2 | `AP_WD`     | **Admin Portal** + **Workday integration**, vendor onboarding, or vendor payments |
| 3 | `AP_Bulk`   | **Admin Portal Bulk Payments** (import, pending approvals, approved, rejected, approval history) |
| 4 | `AP_Portal` | **Admin Portal UI changes** — edit vendor profile, party user, party info display, vendor screens |
| 5 | `Escrow_IB` | **Escrow Inbound payments** — EMD via "New Payment Request" button or the public EMD form |
| 6 | `Escrow_OB` | **Escrow Outbound payments UI changes** — UI/UX work on outbound payment screens (ACH OB / Legacy TPS Wire / Intercompany / Consolidated / Overnight) |
| 7 | `Resware_OB`| **Escrow Outbound payments** (non-UI) — backend/workflow work on the same outbound family above |
| 8 | `Escrow_CEA`| **Escrow Dashboard main-screen enhancements** — Banks, Bank Accounts, Counterparty, Monitoring, History, My Payments, Profile (and any Escrow story that doesn't match a more specific rule) |

✅ **Implementation reference:** `test/domain_context.py → classify_epp_area()` performs this classification automatically from the User Story's title, description, and acceptance criteria.

✅ **Filtering tip in ADO:** because the tag is on `System.Tags`, you can run queries like  
`Tags Contains "Resware_OB" AND Tags Contains "AI TestCase"` to see all AI-generated outbound-Escrow test cases.

---

## 📄 SAMPLE Test Case: Export Button Functionality in Payments Monitoring View

**Reference:**  
[ADO Work Item – 347621](http://dev.azure.com/StewartTitle/Enterprise%20Payments/_workitems/edit/347621)

---

### 📌 Objective
Verify that the user is able to export payment data into a CSV report from the Payments Monitoring view.

### ✅ Preconditions
- User must have access to the **Escrow Dashboard**
- User must have access to the **Payments Monitoring** screen

### 🌐 URL / Navigation
**History → Payments → Escrow Payment Dashboard**

---

### 🧪 Test Steps

| # | Action | Expected Result |
|---|--------|-----------------|
| 1 | Log in to the Escrow Dashboard | User is successfully logged in |
| 2 | Navigate to the **Payments Monitoring** view | User is on the Payments Monitoring view |
| 3 | Locate the **Export** button in the top-right corner | Export button is visible and accessible |
| 4 | Click the **Export** button | A confirmation pop-up is displayed |
| 5 | Verify pop-up content | Pop-up shows text: *"Are you sure you want to export the data?"* with **Yes** and **No** buttons |
| 6 | Click **Yes** | CSV file is successfully downloaded |
| 7 | Click **No** | Pop-up is closed without downloading a file |

---

### 📝 Expected Outcome
- User is prompted for confirmation before export
- CSV file is downloaded only when **Yes** is selected
- No action is taken when **No** is selected
