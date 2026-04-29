# Test Case Generation Rules

These rules **must** be followed for every test case generated against any user story.

---

## RULE-GEN — General Test Case Structure

### RULE-GEN-01: Required Fields
Every test case must have:
- **Title** (clear, action-based)
- **Preconditions**
- **Test Steps** (numbered)
- **Expected Result** per step
- **Overall Expected Result**
- **Priority** (High / Medium / Low)
- **Test Type** (Functional / Negative / Boundary / UI / API / Regression)

### RULE-GEN-02: Title Format
```
[TC-NNN] <Action> <Feature> <Condition/Business Statement>
```
**Example:** `[TC-001] Verify that Login with Valid Credentials`

### RULE-GEN-03: Minimum Test Cases per User Story
Each user story must produce at minimum:
- **2** Happy Path (positive) test cases with authorized role
- **1** Negative / Boundary / Edge case / Unauthorized role test case
- **2** test cases against each Acceptance Criterion

### RULE-GEN-04: Clubbing
Club test cases with similar outcomes to avoid redundancy.

---

## RULE-COV — Coverage Rules

### RULE-COV-01: AC Mapping
Map every Acceptance Criterion (AC) in the user story to **at least 1** and **at most 4** test cases.

### RULE-COV-02: Given/When/Then Validation
Each "Given / When / Then" clause in the AC must be validated by at least one step.  
**Do NOT** use the prefixes "Given", "When", "Then" in test step text.

### RULE-COV-03: Role-Based Test Cases
If the user story has role-based behavior (e.g., Admin vs User), generate **separate** test cases per role.

### RULE-COV-04: Data Input Test Cases
If the user story involves data input, generate:
- Valid data test
- Invalid data test
- Empty / null input test
- Special characters test
- Max length / Min length test
- CSV file for test data

---

## RULE-FUNC — Functional Validation Rules

### RULE-FUNC-01: UI Elements
Validate all UI elements mentioned in the story (buttons, dropdowns, forms, modals).

### RULE-FUNC-02: Navigation Flow
Validate navigation flow — entry point to exit point.

### RULE-FUNC-03: Messages
Validate success messages, error messages, and toast notifications explicitly.

### RULE-FUNC-04: Data Persistence
Validate that data persists correctly after save/submit actions.

### RULE-FUNC-05: Cancel/Back
Validate that cancel/back actions do **NOT** save unintended data.

### RULE-FUNC-06: Mockups/Images
Attach the related mockup/image from the US to the test case step where required, if present in the US.

### RULE-FUNC-07: Tagging
Add the tag **`Gen-AI`** in ADO for all test cases generated through the AI agent.

### RULE-FUNC-08: Pre/Post Steps
Within a US, create Pre/Post step references for test cases that are sequential.  
Mention the link of the prerequisite test case at the start (for Pre) or vice versa (for Post).
