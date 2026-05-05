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
