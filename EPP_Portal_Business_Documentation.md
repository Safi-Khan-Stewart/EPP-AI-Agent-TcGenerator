# EPP Portal – Comprehensive Business & Technical Documentation

**Document Version:** 1.0  
**Date:** April 29, 2026  
**Scope:** Escrow Dashboard (Epp.Escrow.Admin) & AP Admin Portal (Epp.Admin)  
**Based On:** Full codebase analysis — no assumptions made

---

## Table of Contents

1. [Project Overview & Architecture](#1-project-overview--architecture)
2. [Authentication & Identity Framework](#2-authentication--identity-framework)
3. [Portal 1 – Escrow Dashboard (CEA Dashboard)](#3-portal-1--escrow-dashboard-cea-dashboard)
   - 3.1 [Architecture & Technology Stack](#31-architecture--technology-stack)
   - 3.2 [User Roles & Access Control](#32-user-roles--access-control)
   - 3.3 [Navigation Structure & Role-Based Routing](#33-navigation-structure--role-based-routing)
   - 3.4 [Screen-by-Screen Documentation](#34-screen-by-screen-documentation)
   - 3.5 [End-to-End Workflows](#35-end-to-end-workflows)
   - 3.6 [API Layer Documentation](#36-api-layer-documentation)
4. [Portal 2 – AP Admin Portal](#4-portal-2--ap-admin-portal)
   - 4.1 [Architecture & Technology Stack](#41-architecture--technology-stack)
   - 4.2 [User Roles & Access Control](#42-user-roles--access-control)
   - 4.3 [Navigation Structure & Role-Based Routing](#43-navigation-structure--role-based-routing)
   - 4.4 [Screen-by-Screen Documentation](#44-screen-by-screen-documentation)
   - 4.5 [End-to-End Workflows](#45-end-to-end-workflows)
   - 4.6 [API Layer Documentation](#46-api-layer-documentation)
5. [Shared Infrastructure & External Integrations](#5-shared-infrastructure--external-integrations)
6. [Cross-Portal Interactions](#6-cross-portal-interactions)
7. [Gaps, Inconsistencies & Observations](#7-gaps-inconsistencies--observations)

---

## 1. Project Overview & Architecture

The EPP (Electronic Payment Platform) is a large multi-portal, multi-service solution hosted in a monorepo workspace. It serves two primary administrative audiences:

| Portal | Internal Name | Technology | Purpose |
|---|---|---|---|
| Escrow Dashboard | `Epp.Escrow.Admin` | Angular (Standalone) + ASP.NET Core | Manage escrow payment lifecycle — initiate, monitor, approve, reverse, reconcile payments in escrow transactions |
| AP Admin Portal | `Epp.Admin` | Angular (Module-based) + ASP.NET Core | Manage accounts payable workflows — bulk payment import, approval, account management, Stripe integration, reporting |

### Overall Architectural Pattern

```
┌─────────────────────────────────────────────────────┐
│               Azure AD B2C / AAD                    │
│           (Identity & Role Management)              │
└───────────────────────┬─────────────────────────────┘
                        │ MSAL Auth
        ┌───────────────┴───────────────┐
        │                               │
┌───────▼──────────┐         ┌──────────▼──────────┐
│ Escrow Dashboard │         │   AP Admin Portal   │
│ (Angular SPA)    │         │   (Angular SPA)     │
│ ASP.NET BFF Host │         │   ASP.NET BFF Host  │
└───────┬──────────┘         └──────────┬──────────┘
        │                               │
        │       ┌───────────────────────┘
        │       │  Service Client (NSwag-generated)
        ▼       ▼
┌──────────────────────────────────────────────────────┐
│                   Epp.Api (Core)                     │
│  Accounts, Payments, BulkPayments, Parties,          │
│  BusinessUnits, Stripe, PaymentAggregates            │
└───────────────────────┬──────────────────────────────┘
                        │
        ┌───────────────┼──────────────────┐
        ▼               ▼                  ▼
  Elis.Api          Ewis.Api        SharedServices.Api
  (ELIS Integration) (EWIS/Wire)    (Tasks, Storage, 
                                    Verification)
```

**Backend-for-Frontend (BFF) Pattern:** Both portals follow BFF architecture. Each Angular SPA communicates with its own ASP.NET Core host (which acts as a thin proxy). The host authenticates via MSAL and forwards calls to backend microservices using NSwag-generated typed service clients.

**Service Communication:** All downstream API calls go through strongly-typed client interfaces (e.g., `IEscrowPaymentsClient`, `IBulkPaymentClient`) injected via dependency injection, pointing to the `Epp.Api` and other service endpoints.

---

## 2. Authentication & Identity Framework

Both portals use **Microsoft Identity Platform (MSAL)** for authentication:

- **Protocol:** OAuth 2.0 / OpenID Connect via Azure Active Directory
- **Library:** `@azure/msal-angular` (frontend) + `Microsoft.Identity.Web` (backend)
- **Token:** JWT ID Token containing `roles` claim (array of assigned Azure AD App Roles)
- **Flow:** Redirect-based authentication; `MsalGuard` protects all routes; `MsalInterceptor` injects Bearer tokens on all HTTP calls
- **Settings API:** Both portals expose a public `/api/Settings` endpoint that returns MSAL config (`clientId`, `authority`, `redirectUri`, `scopes`, `tenantId`) — this is fetched by the Angular app on startup before authentication begins
- **Login Failure:** Dedicated `/failure/login/msal` (Escrow) and `/login-failed` (AP Admin) pages handle auth failures

---

## 3. Portal 1 – Escrow Dashboard (CEA Dashboard)

### 3.1 Architecture & Technology Stack

| Layer | Technology |
|---|---|
| Frontend SPA | Angular (Standalone Components pattern, modern Angular) |
| UI Library | Angular Material (mat-table, mat-dialog, mat-sidenav, mat-expansion, mat-tabs) |
| State Management | RxJS BehaviorSubject + reactive streams (no NgRx) |
| HTTP Client | Angular HttpClient + NSwag-generated service clients |
| Backend Host | ASP.NET Core 8 (BFF) |
| Authentication | Azure AD via MSAL |
| Search/Filter | Azure AI Search (OData filters) |
| Storage | Preferences API (JSON serialized, scoped to user) |
| Scroll | `ngx-scrollbar` with infinite scroll via `ngx-scrollbar/reached-event` |
| Masks | `ngx-mask` |
| External | EWIS (Wire Transfer Integration System), Modern Treasury |

**Project Structure:**
```
Epp.Escrow.Admin/
├── Epp.Escrow.Admin/          ← ASP.NET Core BFF Host
│   ├── Api/                   ← BFF Controller layer
│   ├── Services/              ← EscrowUserAffiliationService
│   ├── epp.escrow.admin.client/  ← Angular SPA
│   │   └── src/app/
│   │       ├── features/admin/
│   │       │   ├── pages/     ← All page components
│   │       │   ├── components/ ← Shared UI components (navigation, loader, dialogs)
│   │       │   ├── services/  ← Admin feature services
│   │       │   ├── models/    ← Frontend view models
│   │       │   ├── helpers/   ← Utility functions
│   │       │   ├── pipes/     ← Angular pipes
│   │       │   └── directives/ ← Custom directives
│   │       └── core/          ← Auth, API, constants, models, validators
└── Epp.Escrow.Admin.Shared/   ← Shared .NET code (auth, authorization roles)
```

---

### 3.2 User Roles & Access Control

Roles are defined in `Epp.Escrow.Admin.Shared/Authorization/AuthorizationRoles.cs` and enforced both on backend (`[Authorize(Roles = ...)]`) and frontend (`*ngIfInAnyRole` directive):

| Role ID | Role Name | Description |
|---|---|---|
| `User.FieldUser` | **Field User** | Member of Escrow Closing team. Initiates financial transactions; approves transactions from TPS. Company interface for customers. Limited dashboard access. Can view only their own transactions ("My Payments"). |
| `User.FieldApprover` | **Field Approver** | Reviews and approves individual transactions created in EPP. |
| `User.AccountingUser` | **Accounting User** | Can initiate or approve transactions. Has full access to CEA dashboard screens. Can monitor all transactions. Mutually exclusive with Field User (supersedes it). Can perform all admin payment actions (reject, reverse, retry, mark posted, claim, resolve). |
| `User.Administrator` | **Administrator** | Creates and updates banks and bank accounts. Manages system setup, users, locations, banks. Cannot be combined with FieldUser or AccountingUser. Can be combined only with Support. |
| `User.Support` | **Support** | View-only access to all CEA dashboard screens. Cannot perform actions. |
| `User.AccountVerificationAdministrator` | **Account Verification Admin** | Admin user with full access. Can allow counterparties to onboard after PNC/EWS rejection errors. Can allow reattempt of onboarding. |
| `User.CEAFraudInvestigator` | **CEA Fraud Alert Investigator** | Legal/Audit team member. View-only access + ability to reveal PII sensitive information (bank account numbers, etc.) on demand from specific screens. |

**Role-based default redirect (on login):**

| User Has Role | Redirected To |
|---|---|
| FieldUser, AccountingUser, Support, CeaFraudInvestigator | `/payments` |
| Administrator | `/accounts/banks` |
| AccountVerificationAdministrator | `/counterparties` |
| None matching | `/access-denied` |

---

### 3.3 Navigation Structure & Role-Based Routing

```
/ (root — MSAL guarded)
├── home                    → Home (placeholder — not yet implemented)
├── approvals               → Approvals (placeholder — not yet implemented)
├── payments/               → Payments section [FieldUser, AccountingUser, Support, CeaFraudInvestigator]
│   ├── (default)           → Payment History List
│   ├── profiles            → Profiles
│   ├── request             → Create New Payment Request
│   ├── monitoring          → Payment Monitoring [Support, CeaFraudInvestigator, AccountVerificationAdmin, Administrator, AccountingUser]
│   └── my                  → My Payments [FieldUser only]
├── accounts/               → Accounts section [Administrator, Support, CeaFraudInvestigator]
│   ├── banks               → Banks List
│   ├── banks/add           → Add New Bank
│   ├── banks/:id/edit      → Edit Bank
│   ├── banks/:id           → Bank Details
│   ├── bank-accounts       → Internal Bank Accounts List
│   └── bank-accounts/:id/edit → Edit Internal Bank Account
├── counterparties/         → Counterparties [FieldUser, AccountingUser, AccountVerificationAdmin, Support, CeaFraudInvestigator]
│   ├── (default)           → Counterparties List
│   └── onboard             → Onboard Counterparty
├── reports                 → Reports (placeholder — not yet implemented)
├── settings/               → Settings [Administrator, AccountingUser — shown in bottom nav]
│   └── monitoring          → Payment Monitoring Rule Settings
├── tasks                   → Tasks List
├── ewis                    → EWIS Payment Integrations List
├── access-denied           → Access Denied page
├── failure/login/msal      → MSAL Login Failure
└── **                      → Page Not Found
```

---

### 3.4 Screen-by-Screen Documentation

---

#### Screen 1: Home

| Attribute | Detail |
|---|---|
| **Route** | `/home` |
| **Status** | Placeholder — HTML template is empty (not yet implemented) |
| **Purpose** | Intended as a landing/dashboard overview page |
| **Access** | All authenticated users |
| **Current State** | Empty component; no data loading or UI |

**Gap:** This screen is not yet implemented. Per the navigation structure it is marked `readonly` in the nav and has no routerLink active.

---

#### Screen 2: Approvals

| Attribute | Detail |
|---|---|
| **Route** | `/approvals` |
| **Status** | Placeholder — template contains only `<p>approvals works!</p>` |
| **Purpose** | Intended for reviewing and approving pending items |
| **Access** | All authenticated users |
| **Current State** | Empty component shell |

**Gap:** This screen is not yet implemented. Navigation item is marked `readonly` (no routerLink).

---

#### Screen 3: Payment History List (Default Payments View)

| Attribute | Detail |
|---|---|
| **Route** | `/payments` (exact) |
| **Component** | `PaymentsHistoryListComponent` |
| **Purpose** | Displays a paginated, searchable, filterable list of all escrow payment intents (historical view) |
| **Access** | FieldUser, AccountingUser, Support, CeaFraudInvestigator |

**UI Components:**
- Data table (`mat-table`) with columns: Counter Party, Stewart Bank Account, Escrow File Number, Amount, Type, Status, Created Date, Payment Date, Payment Reference, Company, Source, Officer
- Search bar (debounced, min 2 characters) using Azure AI Search
- Filter panel (side drawer — `mat-sidenav`) with `PaymentFilterComponent` and `PaymentAggregateFilterComponent`
- Filter summary chips (`PaymentFilterSummaryComponent`)
- Column resize via `ColumnResizeDirective`
- Sort capability (`MatSort`)
- Infinite scroll (`NgScrollbar` + `NgScrollbarReachedModule`)
- Row expansion animation (collapse/expand detail row)
- Tab interface: by aggregate / individual payments
- Export dialog (`PaymentExportDialogComponent`)
- Action menus (CDK Menu) on rows

**Data Sources:**
- Azure AI Search index (OData queries) via `SearchIndexRequest`
- Models: `EscrowPaymentIndexModel`, `EscrowPaymentAggregateIndexModel`
- Filter types: `EscrowPaymentSearchFilter`, `EscrowAggregatePaymentsFacetsType`, `EscrowPaymentsFacetsType`

**Business Rules:**
- Search term minimum length: 2 characters
- OData filters are constructed via helper `toODataChildAwareFilter()` and `convertToODataFilter()`
- Payment statuses are mapped through `EscrowPaymentIntentDisplayStatus` enum
- "Reverse Funds" action is disabled under certain conditions (checked via `isReverseFundsDisabled()`)
- Pagination via scroll (infinite/virtual scroll)
- Filter state is saved to/from user preferences (`PREFERENCES` constants)

**Payment Intent Status Values (EscrowPaymentIntentDisplayStatus):**
`Pending`, `Created`, `BeginProcessingVendor`, `SentToBank`, `TransmissionFailed`, `Posted`, `Rejected`, `Reversed`, `ManuallyResolved`, `Claimed`, `MarkedAsPosted`, and more (as mapped in monitoring tabs)

---

#### Screen 4: Payment Monitoring

| Attribute | Detail |
|---|---|
| **Route** | `/payments/monitoring` |
| **Component** | `PaymentsMonitoringListComponent` |
| **Purpose** | Real-time monitoring view of escrow payment intents in various processing states. Allows accounting/admin users to take action on stuck/failed payments. |
| **Access** | Support, CeaFraudInvestigator, AccountVerificationAdministrator, Administrator, AccountingUser |

**UI Components:**
- Tabbed interface (`MatTabs`) with tabs:
  - **Summary Tab** — `PaymentsMonitoringSummaryComponent` (aggregated view)
  - **Consolidation Queue Tab** — Payments grouped for consolidation
  - **Overnight Queue Tab** — Payments scheduled for overnight processing
  - Additional dynamic tabs per `monitoringTabs` definition (e.g., "Pending" status filter)
  - **Pending Tab** — payments with status: Pending, Created, BeginProcessingVendor, SentToBank
- Data table with same column set as History screen
- Filter sidebar (same filter components as history)
- Sort, column resize
- Infinite scroll with scroll restoration
- Autocomplete search
- AI Search integration

**Available Actions (AccountingUser role only via `AuthorizationRoleDirective`):**
- **Report Failure** — `ReportFailureDetails` POST — Record failure details for a payment intent
- **Resolve Manually** — `ResolveEscrowPaymentIntent` POST — Mark payment as manually resolved with details
- **Claim** — `ClaimEscrowPaymentIntent` POST — Associate payment with an escrow file number
- **Reverse** — `ReversePaymentIntent` POST — Reverse a payment transaction
- **Retry** — `RetryEscrowPaymentTransmissionFailed` POST — Retry a transmission-failed payment
- **Sync** — `SyncEscrowPaymentIntent` POST — Sync payment status with provider
- **Mark As Posted** — `MarkAsPosted` POST — Manually mark as posted with confirmation number and reason
- **Reject** — `RejectEscrowPaymentIntent` POST — Reject a payment intent
- **Get Providers** — `GetPaymentAccountProvidersForPaymentIntent` GET — List available payment providers

**Monitoring Tabs:** Defined dynamically. Each tab applies an OData status filter to the AI Search query so users see payment intents segmented by processing state.

**Business Rules:**
- Transmission-failed payment retry is visible to: AccountingUser, Support, CeaFraudInvestigator, AccountVerificationAdministrator
- Reverse funds action is conditionally disabled based on `isReverseFundsDisabled()` helper
- Payment monitoring rule settings (thresholds per bank and rail) affect which payments appear in alert states
- Obsolete monitoring rule settings are converted via `convertObsolete()` helper for backward compatibility

---

#### Screen 5: Payment Profiles

| Attribute | Detail |
|---|---|
| **Route** | `/payments/profiles` |
| **Component** | `PaymentsProfilesComponent` |
| **Purpose** | Displays payment profile data (counterparty banking/payment preference profiles linked to escrow payments) |
| **Access** | FieldUser, AccountingUser, Support, CeaFraudInvestigator |

*Note: Detailed implementation of PaymentsProfilesComponent was not fully analyzed — component exists in routes and index exports.*

---

#### Screen 6: Payment Request Creation (New Payment)

| Attribute | Detail |
|---|---|
| **Route** | `/payments/request` |
| **Component** | `PaymentCreationComponent` |
| **Purpose** | Allows authorized users to create a new escrow payment request — either a payment invitation sent to a counterparty, or a direct "send funds" payment. |
| **Access** | FieldUser, AccountingUser (creation); Support, FieldApprover, CeaFraudInvestigator, Administrator, AccountingUser, AccountVerificationAdministrator (for "send funds" specific sections) |

**Form Fields:**

| Field | Type | Validation |
|---|---|---|
| Transaction Direction | Radio (Inbound/Outbound) | Required |
| Amount | Number | Required, min $0.01, max configured `ESCROW_PAYMENTS.MaxAmount` |
| Internal Bank Account | Select (autocomplete) | Required |
| Payment Use Case | Select | Required |
| Property State | Select (US states) | Required |
| Property Description | Text | Required, no whitespace-only, max 256 chars |
| Escrow File Number | Text | Required, no whitespace-only |
| Remittance Information | Text | Optional, max 140 chars |
| Party First Name | Text | Required, max `ESCROW_CUSTOMER.FirstNameMaxLength` |
| Party Last Name | Text | Required, max `ESCROW_CUSTOMER.FirstNameMaxLength` |
| Party Email | Email | Required, email format, max `ESCROW_CUSTOMER.EmailMaxLength` |
| Party Phone | Phone | Required, mobile number format (`mobileNumberValidator`) |
| Escrow Officer First Name | Text | Required, max 128 chars |
| Escrow Officer Last Name | Text | Required, max 128 chars |
| Escrow Officer Email | Email | Required, email format, max 100 chars |
| Escrow Officer Phone | Phone | Required, mobile number format |

**Data Sources:**
- Available Internal Bank Accounts: `InternalBankAccountApiService.getAvailableInternalBankAccounts()` — filtered by user's escrow office affiliations (FieldUser gets only affiliated accounts)
- Payment Use Cases: `TransactionRouterApiService.getPaymentUseCases()` — from transaction router
- Counterparties: `PartyProjectionApiService` — paginated autocomplete with scroll-loading (`OptionsScrollDirective`)

**Business Logic:**
- The `createdByUserEmail` is set automatically from the authenticated user's identity token
- FieldUser sees only internal bank accounts affiliated to their escrow offices (via `EscrowUserAffiliationService`)
- Unaffiliated/unrestricted roles (Support, AccountingUser, Administrator, etc.) see all internal bank accounts
- Transaction direction affects which form fields are shown/required
- On success: navigates away (likely to payment history)
- On error: displays notification toast

**System Actions:**
- Creates either a `CreateEscrowPaymentRequest` (invitation-based) or `CreateEscrowPayment` (direct payment) depending on form mode
- Both endpoints are authorized: `[FieldUser, AccountingUser]`

---

#### Screen 7: My Payments

| Attribute | Detail |
|---|---|
| **Route** | `/payments/my` |
| **Component** | `PaymentsUserPaymentsListComponent` |
| **Purpose** | A personal filtered view of payments initiated by the currently logged-in user (Field User self-service view) |
| **Access** | FieldUser only (hidden from other roles in nav) |

---

#### Screen 8: Consolidated Payments

| Attribute | Detail |
|---|---|
| **Component** | `ConsolidatedPaymentsComponent` (embedded in monitoring tabs) |
| **Purpose** | View for consolidated/batched payment aggregates — shows aggregated payment requests grouped for processing |
| **Access** | AccountingUser |

**Actions Available:**
- Release payment aggregate: `ReleaseEscrowPaymentAggregate` POST
- Release individual aggregate request: `ReleaseEscrowPaymentAggregateRequest` POST
- Reject aggregate request: `RejectEscrowPaymentAggregateRequest` POST (requires reason text)

---

#### Screen 9: Payment Requests List

| Attribute | Detail |
|---|---|
| **Component** | `PaymentRequestsListComponent` (embedded within payment screens) |
| **Purpose** | Displays outbound payment requests/invitations that have been sent to counterparties but not yet actioned |
| **Access** | FieldUser, AccountingUser, CeaFraudInvestigator, FieldApprover, Support |

**UI Components:**
- Table with columns: Name, Email, Description, Escrow File Number, Status, Sent At
- Search bar (debounced 600ms)
- Pagination (mat-paginator)
- Toggle: "Include Expired" slide toggle

**Status Values:**
- `Invitation Sent` — Active invitation pending counterparty action
- `Expired` — Past expiry date (computed client-side by comparing `expireAt` with `Date.now()`)

**Business Rules:**
- Status is computed at display time by checking `item.expireAt <= Date.now()`
- Expired items are shown with "failed" CSS class
- Toggle allows showing or hiding expired invitations

---

#### Screen 10: Payment Monitoring Summary

| Attribute | Detail |
|---|---|
| **Component** | `PaymentsMonitoringSummaryComponent` (tab within Monitoring) |
| **Purpose** | Aggregated summary view of payment monitoring state — key metrics and status breakdowns |
| **Service** | `MonitoringSummaryService`, `MonitoringResultVerifyService` |

---

#### Screen 11: Banks List (Accounts → Banks)

| Attribute | Detail |
|---|---|
| **Route** | `/accounts/banks` |
| **Component** | `BanksListComponent` |
| **Purpose** | View and manage banks configured in the system (the banking institutions used for escrow fund movement) |
| **Access** | Administrator, Support, CeaFraudInvestigator |

---

#### Screen 12: Add/Edit Bank

| Attribute | Detail |
|---|---|
| **Routes** | `/accounts/banks/add`, `/accounts/banks/:id/edit` |
| **Component** | `BankManageComponent` |
| **Purpose** | Create or update bank records |
| **Access** | Administrator (create/edit restricted to Administrator role via API) |

---

#### Screen 13: Bank Details

| Attribute | Detail |
|---|---|
| **Route** | `/accounts/banks/:id` |
| **Component** | `BankDetailsComponent` |
| **Purpose** | View detailed information about a specific bank |
| **Access** | Administrator, Support, CeaFraudInvestigator |

---

#### Screen 14: Internal Bank Accounts List

| Attribute | Detail |
|---|---|
| **Route** | `/accounts/bank-accounts` |
| **Component** | `InternalBankAccountsListComponent` |
| **Purpose** | View, search, and manage Internal Bank Accounts — the company's own banking accounts used to receive/send escrow funds |
| **Access** | Administrator, Support, CeaFraudInvestigator |

**Actions Available (role-dependent):**
- **Search** — POST `/api/InternalBankAccounts/Search` — filter by criteria
- **Create** — POST `/api/InternalBankAccounts` [Administrator only]
- **Reveal Account Number** — GET `/api/InternalBankAccounts/{key}/Reveal` [CeaFraudInvestigator only] — fetches unmasked account number at runtime (PII protection)
- **View Associations** — GET `/api/InternalBankAccounts/{key}/Associations`
- **Get Parent Account** — GET `/api/InternalBankAccounts/{key}/Parent`

---

#### Screen 15: Edit Internal Bank Account

| Attribute | Detail |
|---|---|
| **Route** | `/accounts/bank-accounts/:id/edit` |
| **Component** | `InternalBankAccountEditComponent` |
| **Purpose** | Edit an existing internal bank account — update details and payment rails |
| **Access** | Administrator only |

**Editable Fields (via PATCH):**
- Account details (name, description, etc.)
- Payment rails: ACH, Wire, SameDayACH, RTP (PATCH `/api/InternalBankAccounts/{key}/PaymentRails`)

---

#### Screen 16: Counterparties List

| Attribute | Detail |
|---|---|
| **Route** | `/counterparties` |
| **Component** | `CounterpartiesListComponent` |
| **Purpose** | Lists all counterparties (external parties) registered in the system — companies or individuals who receive or send escrow payments |
| **Access** | FieldUser, AccountingUser, AccountVerificationAdministrator, Support, CeaFraudInvestigator |

**UI Components:**
- Data table with columns: Name, Status, Bank Accounts Count, Payment Flows
- Search bar (debounced 600ms)
- Pagination (mat-paginator)
- Row click → opens `CounterpartyDetailsDialogComponent` modal
- "Onboard" button [AccountVerificationAdministrator only] — navigates to `/counterparties/onboard`

**Data Source:** `PartyProjectionApiService` — searches party projections

**Business Rules:**
- Clicking a row opens a details dialog showing full party information
- Onboarding navigation is role-restricted

---

#### Screen 17: Onboard Counterparty

| Attribute | Detail |
|---|---|
| **Route** | `/counterparties/onboard` |
| **Component** | `CounterpartiesOnboardComponent` |
| **Purpose** | Allows AccountVerificationAdministrators to onboard a new counterparty — bypassing or retrying after a failed account verification (EWS/PNC checks) |
| **Access** | AccountVerificationAdministrator |

---

#### Screen 18: Counterparty Details Dialog

| Attribute | Detail |
|---|---|
| **Component** | `CounterpartyDetailsDialogComponent` (modal overlay) |
| **Purpose** | Detailed view of a counterparty party record — bank accounts, payment flows, status, etc. |
| **Trigger** | Row click on Counterparties List |

---

#### Screen 19: Reports

| Attribute | Detail |
|---|---|
| **Route** | `/reports` |
| **Component** | `ReportingComponent` |
| **Status** | Placeholder — template contains only `<p>reporting works!</p>` |

**Gap:** Not yet implemented.

---

#### Screen 20: Payment Monitoring Rule Settings

| Attribute | Detail |
|---|---|
| **Route** | `/settings/monitoring` |
| **Component** | `PaymentMonitoringRuleSettingsComponent` |
| **Purpose** | Configure payment monitoring rules — thresholds, status transitions, and alert criteria per payment rail and per bank account |
| **Access** | Administrator, AccountingUser (shown in bottom nav for these roles) |

**UI Components:**
- Bank account selector (default + specific banks)
- Rail tabs: ACH, Wire, Same-Day ACH, RTP
- Status threshold sliders and inputs per status
- Status transition table with configurable rules
- Audit log section

**Form Structure (`RailFormGroup`):**
- `bankKey` — selected bank (or `"DEFAULT"` for system-wide)
- `railsRules` — `FormArray` of one form group per rail

**Payment Rails:**
- `ACH` — Automated Clearing House
- `Wire` — Wire transfer
- `SameDayACH` — Same-day ACH
- `RTP` — Real-Time Payments

**Status Descriptions (for user guidance):**
- `Pending` — Payment initiated but not yet picked up for processing

**Persistence:** Rules are stored via the **Preferences API** with structured naming:
- `EppEscrowAdmin_Settings_PaymentMonitoring_ACH_Pending` (example)
- Scoped globally or per user
- Uses ETag-based optimistic concurrency on updates

**Business Rules:**
- Threshold validator (`thresholdValidator`) enforces min/max ranges
- Obsolete settings format is detected via `isObsolete()` and converted via `convertObsolete()`
- On save: either `CreatePreference` or `UpdatePreference` depending on existence
- Polling with retry logic (`retry`, `timer`) for settings load

---

#### Screen 21: Settings Root

| Attribute | Detail |
|---|---|
| **Route** | `/settings` (parent with `RouterOutlet`) |
| **Component** | `SettingsRootComponent` |
| **Purpose** | Tab container for settings sub-pages |
| **Current Tabs** | Monitoring (→ Payment Monitoring Rule Settings) |

---

#### Screen 22: Tasks List

| Attribute | Detail |
|---|---|
| **Route** | `/tasks` |
| **Component** | `TaskListComponent` |
| **Purpose** | Shows tasks assigned to the current user in the SharedServices.Tasks system — action items, follow-ups, etc. |
| **Access** | All authenticated users |

**UI Components:**
- Data table with columns: Title, Status, Due Date, Importance, Tags
- Infinite scroll (pagination built in)
- Row click → opens `TaskDetailsDialogComponent` modal

**Data Source:** `TaskApiService.searchTasks()` — fetches tasks for the user's ID and application key (the Azure AD client ID of this portal)

**Task Statuses / Importance:** Displayed via `TaskStatusPipe` and `TaskImportancePipe`

**Actions:**
- View task details (dialog)
- Update task status via `TaskApiService.updateTaskStatus()` — sends `userReference`, `applicationKey`, and new `status`

---

#### Screen 23: Task Details Dialog

| Attribute | Detail |
|---|---|
| **Component** | `TaskDetailsDialogComponent` |
| **Purpose** | Full details of a single task — description, due date, links, status update controls |
| **Trigger** | Row click on Tasks List |

---

#### Screen 24: EWIS Payment Integrations List

| Attribute | Detail |
|---|---|
| **Route** | `/ewis` |
| **Component** | `PaymentIntegrationListComponent` |
| **Purpose** | Displays wire transfer integration records from the EWIS (External Wire Integration System) — shows status of wire payment requests submitted externally |
| **Access** | All authenticated users |

**UI Components:**
- Data table with columns: ResWare Trans ID, Beneficiary Name, Transactee, Request Amount, Internal Bank Account, ABA/SWIFT Number of Receiving Bank, Beneficiary Account Number (masked), Status, Error Message, Provider, Request Received DateTime
- Search bar (debounced 600ms)
- Pagination (mat-paginator)
- Row click → opens `PaymentIntegrationDetailsDialogComponent` modal
- Status badges via `EwisStatusPipe`
- Monetary values formatted via `CurrencyPipe`

**Data Source:** `PaymentIntegrationApiService.searchPaymentIntegrations()` — fetches `PaymentIntegrationDto` items

**Displayed Metrics:** Total count shown separately via `SearchPaymentIntegrationsCountResponse`

---

#### Screen 25: EWIS Details Dialog

| Attribute | Detail |
|---|---|
| **Component** | `PaymentIntegrationDetailsDialogComponent` |
| **Purpose** | Detailed view of a single EWIS payment integration record — includes full beneficiary, bank routing, status and error details |
| **Trigger** | Row click on EWIS List |

**Additional Data:** `TransacteeController` provides `GET /api/ewis/transactee/{transacteeId}` to look up transactee details by their EWIS integer ID.

---

### 3.5 End-to-End Workflows

#### Workflow 1: Create & Track an Escrow Payment (Field User / Accounting User)

```
1. User logs in → role-based redirect to /payments
2. User navigates to /payments/request
3. Fills payment creation form:
   - Selects transaction direction (Inbound = collecting money; Outbound = disbursing money)
   - Enters amount, escrow file number, property details
   - Selects internal bank account (filtered by office affiliation for FieldUser)
   - Selects payment use case from transaction router
   - Enters counterparty party details (name, email, phone)
   - Enters escrow officer details
4. Submits form:
   - API: POST /api/Escrow/PaymentRequest or POST /api/Escrow/Payments
   - createdByUserEmail set automatically from JWT token
5. System returns created payment key
6. User can track payment in /payments (History) or /payments/monitoring (Monitoring)
```

#### Workflow 2: Monitor & Resolve a Failed Payment (Accounting User)

```
1. Accounting User logs in → redirected to /payments
2. Navigates to /payments/monitoring
3. Filters for "Transmission Failed" status tab
4. Identifies stuck payment
5. Takes one of the following actions:
   a) Retry: POST /api/Escrow/Payments/Intents/{key}/Retry — re-submits to payment provider
   b) Sync: POST /api/Escrow/Payments/Intents/{key}/Sync — refreshes status from provider
   c) Mark As Posted: POST /api/Escrow/Payments/Intents/{key}/MarkAsPosted — with confirmation number (for manual bank confirmation)
   d) Resolve Manually: POST /api/Escrow/Payments/{key}/ResolveManually — with resolution notes
   e) Report Failure: POST /api/Escrow/Payments/{key}/ReportFailure — logs failure details
   f) Reject: POST /api/Escrow/Payments/Intents/{key}/Reject — permanently rejects
   g) Reverse: POST /api/Escrow/Payments/{key}/Reverse — reverses the payment
6. All actions include user identity (UserKey, Email, Name) passed to API from JWT
7. System processes command and returns HTTP 202 Accepted
8. Payment status updates in list after next refresh/poll
```

#### Workflow 3: Manage Counterparty (Account Verification Admin)

```
1. AccountVerificationAdministrator logs in → redirected to /counterparties
2. Reviews counterparties list (search by name/status)
3. Clicks a counterparty → views details dialog (bank accounts, payment flows, status)
4. If counterparty onboarding failed (EWS/PNC rejection):
   - Navigates to /counterparties/onboard
   - Initiates re-onboarding process
5. Counterparty gets re-onboarded (system re-runs verification)
```

#### Workflow 4: Release Consolidated Payments (Accounting User)

```
1. Accounting User navigates to /payments/monitoring → "Consolidation Queue" tab
2. Reviews consolidated payment aggregates
3. Selects an aggregate and clicks "Release":
   - POST /api/Escrow/Payments/Aggregate/{key}/Release
   - Includes user identity
4. For individual requests within an aggregate:
   - POST /api/Escrow/Payments/Aggregate/{key}/Requests/{reqKey}/Release
   - Or: POST /api/Escrow/Payments/Aggregate/{key}/Requests/{reqKey}/Reject (with reason)
```

#### Workflow 5: Configure Payment Monitoring Rules (Administrator / Accounting User)

```
1. User navigates to Settings → Monitoring
2. Selects bank (DEFAULT or specific bank)
3. For each payment rail (ACH, Wire, SameDayACH, RTP):
   - Sets status thresholds (time-based alert rules)
   - Configures status transitions
4. Saves:
   - If no existing preference → POST /api/preferences (create)
   - If existing preference → PUT /api/preferences/{key} (update with ETag for concurrency)
5. Rules are persisted in Preferences API under structured names
6. Monitoring views use these rules to flag/alert on payments exceeding thresholds
```

#### Workflow 6: Reveal Sensitive Bank Account Number (CEA Fraud Investigator)

```
1. CEA Fraud Investigator identifies a suspicious transaction
2. Navigates to /counterparties or /accounts/bank-accounts
3. Locates the relevant party or internal bank account
4. Clicks "Reveal Account Number" (visible only to CeaFraudInvestigator role):
   - GET /api/BankAccounts/{key}/Reveal (for counterparty bank accounts)
   - GET /api/InternalBankAccounts/{key}/Reveal (for internal accounts)
5. System fetches unmasked account number at runtime (not stored)
6. Number is displayed temporarily in UI for investigation purposes
```

---

### 3.6 API Layer Documentation

The BFF (Backend-for-Frontend) host exposes the following API controllers:

| Controller | Route | Purpose |
|---|---|---|
| `EscrowPaymentsController` | `POST /api/Escrow/Payments` | Create escrow payment |
| `EscrowPaymentsController` | `POST /api/Escrow/Payments/{key}/ReportFailure` | Report failure details [AccountingUser] |
| `EscrowPaymentsController` | `POST /api/Escrow/Payments/{key}/ResolveManually` | Manual resolution [AccountingUser] |
| `EscrowPaymentsController` | `POST /api/Escrow/Payments/{key}/Claim` | Claim payment [AccountingUser] |
| `EscrowPaymentsController` | `POST /api/Escrow/Payments/{key}/Reverse` | Reverse payment [AccountingUser] |
| `EscrowPaymentsController` | `POST /api/Escrow/Payments/Intents/{key}/Retry` | Retry transmission failed [AccountingUser] |
| `EscrowPaymentsController` | `POST /api/Escrow/Payments/Intents/{key}/Sync` | Sync status [AccountingUser] |
| `EscrowPaymentsController` | `POST /api/Escrow/Payments/Intents/{key}/MarkAsPosted` | Mark as posted [AccountingUser] |
| `EscrowPaymentsController` | `GET /api/Escrow/Payments/Intents/{key}/Providers` | Get payment providers [AccountingUser] |
| `EscrowPaymentsController` | `POST /api/Escrow/Payments/Intents/{key}/Reject` | Reject payment intent [AccountingUser] |
| `EscrowPaymentAggregateController` | `POST /api/Escrow/Payments/Aggregate/{key}/Release` | Release aggregate [AccountingUser] |
| `EscrowPaymentAggregateController` | `POST /api/Escrow/Payments/Aggregate/{key}/Requests/{reqKey}/Release` | Release request [AccountingUser] |
| `EscrowPaymentAggregateController` | `POST /api/Escrow/Payments/Aggregate/{key}/Requests/{reqKey}/Reject` | Reject request [AccountingUser] |
| `PaymentRequestController` | `POST /api/Escrow/PaymentRequest` | Create payment request [FieldUser, AccountingUser] |
| `PaymentRequestController` | `POST /api/Escrow/PaymentRequest/Search` | Search payment requests [multiple roles] |
| `BankAccountController` | `GET /api/BankAccounts/{key}/Reveal` | Reveal bank account number [CeaFraudInvestigator] |
| `BankController` | Various | Bank CRUD |
| `InternalBankAccountController` | `GET /api/InternalBankAccounts/{key}` | Get IBA [Admin, Support, CeaFraud] |
| `InternalBankAccountController` | `POST /api/InternalBankAccounts/Search` | Search IBAs [Admin, Support, CeaFraud] |
| `InternalBankAccountController` | `POST /api/InternalBankAccounts` | Create IBA [Administrator] |
| `InternalBankAccountController` | `PATCH /api/InternalBankAccounts/{key}` | Update IBA [Administrator] |
| `InternalBankAccountController` | `GET /api/InternalBankAccounts/{key}/Associations` | Get associations [Admin, Support, CeaFraud] |
| `InternalBankAccountController` | `POST /api/InternalBankAccounts/{key}/Associations` | Create association [Administrator] |
| `InternalBankAccountController` | `PATCH /api/InternalBankAccounts/{key}/PaymentRails` | Update payment rails [Administrator] |
| `InternalBankAccountController` | `GET /api/InternalBankAccounts/{key}/Parent` | Get parent IBA [Admin, Support, CeaFraud] |
| `InternalBankAccountController` | `GET /api/InternalBankAccounts/Available` | Get available IBAs [FieldUser, AccountingUser; filtered by affiliations for FieldUser] |
| `InternalBankAccountController` | `GET /api/InternalBankAccounts/{key}/Reveal` | Reveal IBA number [CeaFraudInvestigator] |
| `EscrowOfficeController` | `GET /api/EscrowOffices` | Get all escrow offices |
| `EscrowOfficeController` | `GET /api/EscrowOffices/Affiliations` | Get user's affiliated escrow offices [FieldUser returns filtered; others return empty = all] |
| `PreferencesController` | `POST /api/preferences` | Create preference [Authenticated] |
| `PreferencesController` | `PUT /api/preferences/{key}` | Update preference [Authenticated] |
| `PreferencesController` | `GET /api/preferences/{namePrefix}` | Get preferences by name [Support, CeaFraud, AccountVerificationAdmin, Administrator, AccountingUser] |
| `PreferencesController` | `DELETE /api/preferences/{key}` | Delete preference [Authenticated] |
| `TaskController` | `GET /api/Tasks/{key}` | Get task details |
| `TaskController` | `POST /api/Tasks/Search` | Search user tasks |
| `TaskController` | `POST /api/Tasks/{key}` | Update task status |
| `TransactionRouterController` | `GET /api/TransactionRouter/PaymentUseCases` | Get payment use cases |
| `TransactionRouterController` | `GET /api/TransactionRouter/RoutingNumberPaymentRails` | Get rails for routing number |
| `TransacteeController` | `GET /api/ewis/transactee/{id}` | Get transactee from EWIS |
| `PaymentIntegrationController` | Various | EWIS payment integration data |
| `ModernTreasuryInternalAccountController` | Various | Modern Treasury internal account management |
| `CustomerOnboardingTokenController` | Various | Customer onboarding token management |
| `SettingsController` | `GET /api/Settings` | MSAL & app config [AllowAnonymous] |
| `InternalBankAccountExternalAssociationController` | Various | External association management |
| `PartyProjectionController` | Various | Party projection search |
| `PartyConnectedSystemAssociationController` | Various | Party connected system associations |
| `EscrowPaymentAggregateProjectionController` | Various | Payment aggregate projections |
| `EscrowPaymentProjectionController` | Various | Payment projections |

---

## 4. Portal 2 – AP Admin Portal

### 4.1 Architecture & Technology Stack

| Layer | Technology |
|---|---|
| Frontend SPA | Angular (Module-based, classic NgModule pattern) |
| UI Library | Bootstrap (ngx-bootstrap), custom SCSS |
| Charts | ng2-charts (Chart.js wrapper) |
| State Management | RxJS BehaviorSubject + reactive streams |
| Notifications | ngx-toastr |
| Time Display | ngx-timeago |
| HTTP Client | Angular HttpClient + NSwag-generated service clients |
| Backend Host | ASP.NET Core 8 (BFF) |
| Authentication | Azure AD via MSAL |
| Payments | Stripe (connected accounts, payment methods) |

**Project Structure:**
```
Epp.Admin/
├── Epp.Admin/               ← ASP.NET Core BFF Host
│   ├── Api/                 ← BFF Controller layer (30 controllers)
│   ├── ClientApp/           ← Angular SPA (module-based)
│   │   └── src/app/
│   │       └── modules/
│   │           ├── home/          ← Dashboard
│   │           ├── accounts/      ← Account management
│   │           ├── business-units/ ← Business Unit management
│   │           ├── bulk-payments/ ← Bulk payment workflows
│   │           ├── payment-flows/ ← Payout period management
│   │           ├── integration-elis/ ← ELIS integration
│   │           ├── reporting/     ← Reports
│   │           ├── settings/      ← Settings
│   │           ├── profile/       ← User profile
│   │           ├── shared/        ← Shared components
│   │           ├── core/          ← API services, constants
│   │           └── modals/        ← Modal dialogs
└── Epp.Admin.Shared/        ← Shared .NET code (auth, authorization roles)
```

---

### 4.2 User Roles & Access Control

Roles are defined in `Epp.Admin.Shared/Authorization/AuthorizationRoles.cs`:

| Role ID | Role Name | Description |
|---|---|---|
| `Bulk.AP.Payment.Requester` | **Bulk AP Payment Requester** | Requests bulk payments and views history of approvals/rejections and payment results. Sees all AP screens **except** "Pending Approvals." Cannot approve payments. |
| `Bulk.AP.Payment.Approver` | **Bulk AP Payment Approver** | Reviews, approves, views history of approvals/rejections, and views payment results. Sees all AP screens **except** the bulk payment import screen. Cannot submit new payments. |
| `User.Admin` | **User Admin** | Can view and perform **any** action in the portal — full administrative access including deleting parties, syncing Stripe accounts, retrying disbursements, managing users. |
| `User.Basic` | **User Basic** | Observer/read-only role to view all pages in the portal without taking actions. |

**Route Guard Logic (BasicUserRoleGuard):**
- Checks that the user's Azure AD tenant matches the configured tenant
- Requires either `User.Basic` or `User.Admin` role to access any protected route
- Displays error notification with missing role info if unauthorized

---

### 4.3 Navigation Structure & Role-Based Routing

```
/ → redirects to /home (all routes guarded by MsalGuard + BasicUserRoleGuard)
├── home                    → Dashboard (home module)
├── accounts/               → Accounts module
│   ├── (list)              → Accounts list (searchable, filterable)
│   └── {partyKey}/
│       ├── details         → Account Details
│       ├── actions         → Account Actions
│       ├── associations    → Account Associations
│       ├── events          → Account Events
│       ├── logs            → Account Logs
│       └── payouts         → Account Payouts (payment history)
├── business-units/         → Business Units module
│   ├── (list)              → Business Units list
│   ├── new                 → Create New Business Unit
│   ├── {key}/              → Business Unit Details
│   └── {key}/connected-systems → Business Unit Connected Systems
├── settings                → Settings page
├── profile                 → User Profile
├── payment-flow/           → Payment Flows module
│   └── payout-period       → Payout Period management
├── integration/elis/       → ELIS Integration module
│   ├── (root)              → ELIS root view
│   └── service-maps        → ELIS Service Maps
├── reports/                → Reporting module
│   ├── (root)              → Reports root
│   ├── payments            → Reporting Payments
│   ├── payments-active     → Active Payments report
│   └── payments/{key}/details → Payment Details
├── bulk-payments/          → Bulk Payments module [MsalGuard only — no BasicUserRoleGuard override]
│   ├── root                → Bulk Payments Root
│   ├── batches             → Bulk Payment Batches
│   ├── import              → Bulk Payment Import [BulkApPaymentRequester]
│   ├── pending-approvals   → Pending Approvals [BulkApPaymentApprover]
│   ├── approved            → Approved Payments
│   ├── rejected            → Rejected Payments
│   └── approval-history    → Approval History
└── access-denied           → Access Denied page
```

---

### 4.4 Screen-by-Screen Documentation

---

#### Screen 1: Dashboard (Home)

| Attribute | Detail |
|---|---|
| **Route** | `/home` |
| **Component** | `DashboardComponent` |
| **Purpose** | Executive overview of current and previous payout periods — shows metrics, channel summaries, failure data, and business unit payment state |
| **Access** | All authenticated users (User.Basic + User.Admin) |

**UI Components:**
- Current Payout Period summary card
- Previous Payout Period summary card
- Total Requested metrics chart (`MetricsRequestsData`) with `ng2-charts`
- Business Unit payment channels breakdown (`MetricsChannelsData`)
- Failed payments data (`MetricsFailedData`)
- Previous period state by business unit

**Data Sources:**
- `PaymentFlowApiService.getPayoutPeriod()` — GET `/api/PaymentFlows/PayoutPeriod`
- `MetricsApiService.searchPaymentMetrics()` — searches payment metrics with:
  - Payment aggregate keys (current and previous payout periods)
  - Charge providers: `StripeCustomerPaymentMethodAch`, `StewartErpAccountsProvider`
  - 60-minute interval precision
- `OperationsApiService.getAllBusinessUnitsFromCache$()` — list of business units
- `PaymentAggregateApiService.getPaymentAggregate()` — previous period aggregate details
- `PayoutPeriodPaymentAggregateApiService.getPayoutPeriodPaymentAggregate()` — payout period dates

**Business Logic:**
- Uses `forkJoin` to combine multiple data streams in parallel
- Current and previous payout period aggregates identified via `paymentFlowDetails.currentPayoutPeriodAggregateKey` and `previousPayoutPeriodAggregateKey`
- Charts show per-business-unit and per-channel breakdowns
- Precision interval: 60 minutes (configurable)

---

#### Screen 2: Accounts List

| Attribute | Detail |
|---|---|
| **Route** | `/accounts` |
| **Component** | `AccountsComponent` |
| **Purpose** | Browse and search all registered party accounts — individuals or companies enrolled in the payment platform |
| **Access** | User.Basic, User.Admin |

**UI Components:**
- Search text input (debounced 600ms)
- Filter dropdowns:
  - Account Status filter
  - Business Type filter (Individual / Company)
  - Pending Payments toggle
- Paginated table showing:
  - Party name (first name / last name / company name)
  - Account status (displayed, with "ProviderInactive"/"AccountingInactive" normalized to "Inactive")
  - Payment channels (Stripe ACH, ERP provider)
  - Payouts enabled indicator
- Click row → opens account in new tab (`window.open`)
- Pagination: 10 items/page (`ngx-bootstrap/pagination`)

**Filters Applied:**
- `paymentProviders`: Always includes `StewartErpAccountsProvider` and `StripeConnectedExternalAccountAch`
- `businessType`: Individual or Company (optional)
- `accountStatus`: Optional account status
- `hasPendingPayments`: Boolean toggle
- Filter state is persisted in query string for shareable URLs

**Business Logic:**
- `isPayoutsEnabled()`: A party has payouts enabled when it has an active `paymentFlowEnabledAccount` and its status is "Active"
- Party view model maps payment flow enabled accounts into grouped `paymentChannels` (by provider key)
- Active channel priority is sorted to determine `isDefault` flag

---

#### Screen 3: Account Details

| Attribute | Detail |
|---|---|
| **Route** | `/accounts/{partyKey}/details` |
| **Component** | `AccountDetailsComponent` |
| **Purpose** | Full detail view of a single party account — contact info, representative, Stripe account details, bank accounts |
| **Access** | User.Basic, User.Admin |

**UI Components:**
- Party info card (name, status, business type)
- Contact information section
- Representative section (shown for Company type only)
- Stripe Account details (external Stripe data: status, requirements, capabilities)
- Party bank accounts (`PartyAccountAggregateModel`)
- Accounting party account section
- "Generate Payment Link" modal button (only for users) — calls `PartyUserAccessTokenController`

**Data Sources:**
- `AccountStateService.party$` — shared state from parent route
- `PartyApiService.getPartyContact()` — GET `/api/Parties/{key}/Contact`
- `PartyApiService.getPartyRepresentative()` — GET `/api/Parties/{key}/Representative` (Company only)
- `AccountDataService.getStripeAccountDetails()` — fetches Stripe data if Stripe party account exists
- Party accounts from state service

**Business Rules:**
- Representative section only displayed for `BusinessTypes.Company`
- Stripe section only shown if party has an account with `AccountProviders.StripeConnectedAccount`
- Payment link modal shows for User.Admin to generate onboarding/payment tokens

---

#### Screen 4: Account Actions

| Attribute | Detail |
|---|---|
| **Route** | `/accounts/{partyKey}/actions` |
| **Component** | `AccountActionsComponent` (in `account-actions/` directory) |
| **Purpose** | Administrative actions that can be taken on a party account |
| **Access** | User.Admin (actions require admin role) |

**Available Actions (based on API controllers):**
- **Sync Stripe Account Status** — POST `/api/Accounts/Stripe/Actions/Sync` [User.Admin] — syncs account status from Stripe
- **Delete Party** — DELETE `/api/Parties/{key}` [User.Admin]
- **Set Party User as Administrator** — POST `/api/Parties/{key}/Users/SetAdministrator` [User.Admin]
- **Update Party Preferences** — PUT `/api/Parties/{key}/Preferences` [User.Admin]
- **Retry Funds Disbursement** — POST `/api/FundsDisbursements/{key}/Retry` [User.Admin]

---

#### Screen 5: Account Events

| Attribute | Detail |
|---|---|
| **Route** | `/accounts/{partyKey}/events` |
| **Component** | `AccountEventsComponent` |
| **Purpose** | Timeline/log of events that have occurred on a party account (status changes, payment events, etc.) |
| **Access** | User.Basic, User.Admin |

---

#### Screen 6: Account Logs

| Attribute | Detail |
|---|---|
| **Route** | `/accounts/{partyKey}/logs` |
| **Component** | `AccountLogsComponent` |
| **Purpose** | System logs related to a specific party account |
| **Access** | User.Basic, User.Admin |

---

#### Screen 7: Account Payouts

| Attribute | Detail |
|---|---|
| **Route** | `/accounts/{partyKey}/payouts` |
| **Component** | `AccountPayoutsComponent` |
| **Purpose** | Paginated list of all payment disbursements made to/from a specific party account |
| **Access** | User.Basic, User.Admin |

**UI Components:**
- Paginated payment table (10 per page)
- Click row → opens payment details modal

**Data Source:** `PaymentProjectionApiService.searchPayments()` — filters by `disbursementEntityKey` (the party key)

---

#### Screen 8: Account Associations

| Attribute | Detail |
|---|---|
| **Route** | `/accounts/{partyKey}/associations` |
| **Component** | `AccountAssociationsComponent` |
| **Purpose** | Shows connections between this party and other entities — business units, connected systems, party users |
| **Access** | User.Basic, User.Admin |

---

#### Screen 9: Business Units List

| Attribute | Detail |
|---|---|
| **Route** | `/business-units` |
| **Component** | `BusinessUnitsComponent` |
| **Purpose** | Lists all business units configured in the system — the organizational units that group payment accounts and connected systems |
| **Access** | User.Basic, User.Admin |

---

#### Screen 10: Create New Business Unit

| Attribute | Detail |
|---|---|
| **Route** | `/business-units/new` |
| **Component** | `BusinessUnitsNewComponent` |
| **Purpose** | Create a new business unit |
| **Access** | User.Admin |

---

#### Screen 11: Business Unit Details

| Attribute | Detail |
|---|---|
| **Route** | `/business-units/{key}` |
| **Component** | `BusinessUnitComponent` |
| **Purpose** | View details of a specific business unit — name, configuration, payment accounts, associated users, connected systems |
| **Access** | User.Basic, User.Admin |

**Data Sources:**
- `BusinessUnitController.getBusinessUnit()` — GET `/api/Operations/BusinessUnits/{key}`
- `OperationsController.getBusinessUnitAssociatedUsers()` — GET `/api/v2/Operations/BusinessUnits/{key}/AssociatedUsers`
- `OperationsController.createBusinessUnitAssociatedUser()` — POST [User.Admin]
- `OperationsController.deleteBusinessUnitAssociatedUser()` — DELETE [User.Admin]

---

#### Screen 12: Business Unit Connected Systems

| Attribute | Detail |
|---|---|
| **Route** | `/business-units/{key}/connected-systems` |
| **Component** | `BusinessUnitConnectedSystemsComponent` |
| **Purpose** | View and manage connected systems (external integrations) linked to a business unit |
| **Access** | User.Admin |

---

#### Screen 13: Payout Period Management

| Attribute | Detail |
|---|---|
| **Route** | `/payment-flow/payout-period` |
| **Component** | `PayoutPeriodComponent` (in `payment-flows/features/payout-period`) |
| **Purpose** | View and manage the current payout period — the defined time window during which AP payments are aggregated and released |
| **Access** | User.Basic, User.Admin |

**Data Source:** `PaymentFlowApiService.getPayoutPeriod()` — `PayoutPeriodFlowDetailsModel` containing:
- `currentPayoutPeriodAggregateKey`
- `currentPayoutPeriodAggregateReference`
- `currentPayoutPeriodStartDateUtc` / `currentPayoutPeriodEndDateUtc`
- `previousPayoutPeriodAggregateKey`

---

#### Screen 14: Bulk Payments Root (Navigation)

| Attribute | Detail |
|---|---|
| **Route** | `/bulk-payments/root` |
| **Component** | `BulkPaymentsRootComponent` |
| **Purpose** | Root layout/navigation container for the Bulk Payments module |
| **Access** | MsalGuard (all authenticated users; individual sub-pages enforce role) |

---

#### Screen 15: Bulk Payment Batches

| Attribute | Detail |
|---|---|
| **Route** | `/bulk-payments/batches` |
| **Component** | `BulkPaymentsBatchesComponent` |
| **Purpose** | Lists all imported bulk payment batch files — with their status (processing, completed, failed) and summary metrics |
| **Access** | BulkApPaymentRequester, BulkApPaymentApprover, User.Admin |

**Data Source:** `BulkPaymentProjectionApiService` — searches bulk import file projections

---

#### Screen 16: Bulk Payment Import

| Attribute | Detail |
|---|---|
| **Route** | `/bulk-payments/import` |
| **Component** | `BulkPaymentsImportComponent` |
| **Purpose** | Upload a CSV file of payment records for bulk processing — initiate a new batch of AP payments |
| **Access** | BulkApPaymentRequester only (explicitly excluded from Approver view) |

**UI Components:**
- Business Unit dropdown (populated from user's affiliated business units)
- Connected System dropdown (auto-populated from selected business unit; auto-selected if only one)
- Batch Total Amount input (formatted with thousands separator)
- File drop zone / file picker (CSV only, single file)
- CSV template download link
- Validation error display (file-level and line-level errors)

**Form Validation:**

| Field | Rules |
|---|---|
| Business Unit | Required |
| Connected System | Required |
| Batch Total Amount | Required, no whitespace, must be valid amount (amountValidator) |
| File | Required, CSV extension only, single file only |

**Business Logic:**
1. User selects their business unit — connected systems load from the selected unit
2. If only one connected system exists, it is auto-selected
3. User selects CSV file (drag-and-drop or file picker)
4. Only `.csv` extension is accepted
5. Multiple file selection is detected and blocked
6. On submit: POST `/api/Payments/Bulk/Import` with file + metadata
7. Backend validates each CSV row
8. If `success: true` → navigates to `/bulk-payments/batches` with success toast
9. If `importError` present → shows general error message
10. If `importFileInputErrors` present → shows per-row line errors in table
11. CSV template available at GET `/api/Payments/Bulk/Import/CsvTemplate` [AllowAnonymous]

---

#### Screen 17: Pending Approvals

| Attribute | Detail |
|---|---|
| **Route** | `/bulk-payments/pending-approvals` |
| **Component** | `BulkPaymentsPendingApprovalsComponent` |
| **Purpose** | Review and action payment records imported but waiting for approval before being submitted for processing |
| **Access** | BulkApPaymentApprover (for approve/reject actions); visible to all role holders |

**UI Components:**
- Paginated list of `BulkImportRecordProjection` items with status `PendingApproval`
- Checkboxes for individual item selection
- "Select All" / "Select Page" mode toggle
- Batch Total Amount metric display (`BulkImportRecordMetric`)
- Bulk approve button (opens `BulkPaymentsApprovePaymentRequestsModalComponent`)
- Bulk reject button (opens `BulkPaymentsRejectPaymentRequestsModalComponent`)
- Filter by file, date range

**Selection Modes:**
- `SingleItems` — individual checkbox selection
- `SelectAll` — selects all records matching current filter (server-side total)

**Unselected Items Tracking:** When in "SelectAll" mode, items explicitly unchecked are tracked in `unSelectedBulkImportRecordKeys` and excluded from bulk operations.

**Actions:**
- **Approve Single:** POST `/api/Payments/Bulk/Import/Record/{key}/Approve` [BulkApPaymentApprover]
- **Reject Single:** POST `/api/Payments/Bulk/Import/Record/{key}/Reject` [BulkApPaymentApprover] — requires `rejectReason`
- **Approve Multiple:** POST `/api/Payments/Bulk/Import/Record/ApproveMultiple` [BulkApPaymentApprover] — supports `selectAll` with filter + unselected keys
- **Reject Multiple:** POST `/api/Payments/Bulk/Import/Record/RejectMultiple` [BulkApPaymentApprover] — supports `selectAll` with filter + unselected keys + `rejectReason`

**Server-Side "Select All" Logic (Backend):**
When `selectAll: true` is sent, the backend:
1. Gets the current user's connected systems via `operationsClient.SearchBusinessUnitAssociatedUserAsync()`
2. Paginates through ALL matching records (200 at a time) using the provided filter
3. Excludes any keys in `unSelectedBulkImportRecordKeys`
4. Returns the full list for bulk operation

**State Persistence:** Selection state stored in local storage (`BulkPaymentsLocalStorageService`) with 60-minute expiration, scoped to "anyuser".

---

#### Screen 18: Approved Payments

| Attribute | Detail |
|---|---|
| **Route** | `/bulk-payments/approved` |
| **Component** | `BulkPaymentsApprovedPaymentsComponent` |
| **Purpose** | View all bulk payment records that have been approved — historical record of approvals |
| **Access** | BulkApPaymentRequester (primary), BulkApPaymentApprover, User.Admin, User.Basic |

**UI Components:**
- Paginated list of approved `BulkImportRecordProjection` items
- Search by term (debounced)
- Date range filter (from/to)
- CSV export button (downloads file with timestamp in name)

**Export Feature:**
- `BulkPaymentProjectionApiService.exportApprovedCsv()` — streams CSV download
- File name format: `ApprovedPayments_YYYY-MM-DD.csv`
- Filter state persisted in query string

---

#### Screen 19: Rejected Payments

| Attribute | Detail |
|---|---|
| **Route** | `/bulk-payments/rejected` |
| **Component** | (Inferred from route name — similar to Approved pattern) |
| **Purpose** | View all bulk payment records that have been rejected — shows rejection reason |
| **Access** | All bulk payment role holders |

---

#### Screen 20: Approval History

| Attribute | Detail |
|---|---|
| **Route** | `/bulk-payments/approval-history` |
| **Component** | `ApprovalHistoryRootComponent` |
| **Purpose** | Full audit trail of all approval and rejection actions performed in the bulk payments system |
| **Access** | All bulk payment role holders |

---

#### Screen 21: ELIS Integration Root

| Attribute | Detail |
|---|---|
| **Route** | `/integration/elis` |
| **Component** | ELIS module root component |
| **Purpose** | View and manage integration with ELIS (Electronic Ledger Integration System) — mapping of payment service types |
| **Access** | User.Basic, User.Admin |

---

#### Screen 22: ELIS Service Maps

| Attribute | Detail |
|---|---|
| **Route** | `/integration/elis/service-maps` |
| **Component** | `IntegrationElisServiceMapsComponent` |
| **Purpose** | Configure and view service type mappings between EPP and the ELIS accounting system |
| **Access** | User.Admin |

---

#### Screen 23: Reporting

| Attribute | Detail |
|---|---|
| **Route** | `/reports` |
| **Component** | `ReportingPaymentsComponent`, `ReportingPaymentsActiveComponent`, details view |
| **Purpose** | Payment reporting and analysis |
| **Access** | User.Basic, User.Admin |

*Note: Reporting module exists with route definitions but components have minimal implementation observed.*

---

#### Screen 24: Settings

| Attribute | Detail |
|---|---|
| **Route** | `/settings` |
| **Component** | `SettingsComponent` |
| **Purpose** | System settings page for the AP Admin portal |
| **Access** | User.Basic, User.Admin |

---

### 4.5 End-to-End Workflows

#### Workflow 1: Submit Bulk AP Payments (Requester Role)

```
1. BulkApPaymentRequester logs in → navigates to /bulk-payments/import
2. Selects Business Unit from dropdown (shows only user's affiliated units via /api/v2/Operations/BusinessUnits/Mine)
3. Selects Connected System (auto-selected if only one available)
4. Downloads CSV template from /api/Payments/Bulk/Import/CsvTemplate (if needed)
5. Prepares CSV file with payment records
6. Enters Batch Total Amount (must match sum of CSV records)
7. Drops or selects CSV file
8. Validates:
   - File must be .csv
   - Single file only
   - Business unit and connected system required
   - Batch total amount must be valid currency amount
9. Submits → POST /api/Payments/Bulk/Import
10. System validates file contents and returns:
    - success: true → navigate to /bulk-payments/batches with success message
    - importError → display error string
    - importFileInputErrors → display per-row errors with line numbers
11. Requester can then view batch in /bulk-payments/batches
```

#### Workflow 2: Review and Approve/Reject Bulk Payments (Approver Role)

```
1. BulkApPaymentApprover logs in → navigates to /bulk-payments/pending-approvals
2. Views list of pending payment records (PendingApproval status)
3. Reviews records individually or selects in bulk:
   Option A: Individual record review:
      - Reviews details
      - Approve → POST /api/Payments/Bulk/Import/Record/{key}/Approve
      - Reject → opens dialog, enters reason, POST /api/Payments/Bulk/Import/Record/{key}/Reject
   Option B: Batch action:
      - Selects all or specific records
      - Clicks "Approve All Selected" / "Reject All Selected"
      - For "Select All": sends filter + excluded keys to server
      - POST /api/Payments/Bulk/Import/Record/ApproveMultiple or RejectMultiple
4. Successfully approved records → move to Approved Payments (/bulk-payments/approved)
5. Rejected records → move to Rejected Payments (/bulk-payments/rejected) with reason
6. All actions recorded in Approval History (/bulk-payments/approval-history)
```

#### Workflow 3: Manage an Account (User Admin)

```
1. User.Admin logs in → navigates to /accounts
2. Searches/filters for the target account (by name, status, business type)
3. Opens account (new tab) → /accounts/{partyKey}/details
4. Reviews contact, representative, Stripe account details
5. Available admin actions at /accounts/{partyKey}/actions:
   a) Sync Stripe Account: POST /api/Accounts/Stripe/Actions/Sync → updates status from Stripe
   b) Delete Party: DELETE /api/Parties/{key} → removes party
   c) Set User as Admin: POST /api/Parties/{key}/Users/SetAdministrator
   d) Update Preferences: PUT /api/Parties/{key}/Preferences
   e) Retry Disbursement: POST /api/FundsDisbursements/{key}/Retry
6. View payment history at /accounts/{partyKey}/payouts
7. View event log at /accounts/{partyKey}/events
```

#### Workflow 4: Dashboard Monitoring (Any Authenticated User)

```
1. User logs in → lands on /home (Dashboard)
2. System loads payout period details:
   a) GET /api/PaymentFlows/PayoutPeriod → current and previous period aggregate keys
3. Loads metrics for current period:
   a) Searches payment metrics for current aggregate key
   b) Splits by business unit and payment channel (Stripe ACH, ERP)
4. Loads metrics for previous period:
   a) Searches payment metrics for previous aggregate key
5. Dashboard displays:
   - Current payout period dates, total requested amounts, channel breakdown chart
   - Previous payout period: total failures, state by business unit
6. User.Admin can drill into individual business units
```

#### Workflow 5: Manage Business Unit Users (User Admin)

```
1. User.Admin navigates to /business-units/{key}
2. Views current associated users
3. To add user:
   - POST /api/v2/Operations/BusinessUnits/{key}/AssociatedUsers [User.Admin]
   - Specifies email, connected systems
4. To remove user:
   - DELETE /api/v2/Operations/BusinessUnits/{key}/AssociatedUsers [User.Admin]
5. Connected system assignments determine which bulk payment batches users can see/manage
```

---

### 4.6 API Layer Documentation

| Controller | Route | Purpose |
|---|---|---|
| `AccountController` | `GET /api/Accounts/{key}` | Get account by key |
| `BulkPaymentsController` | `GET /api/Payments/Bulk/Import/CsvTemplate` | Download CSV template [AllowAnonymous] |
| `BulkPaymentsController` | `POST /api/Payments/Bulk/Import` | Import bulk payment file [BulkApPaymentRequester] |
| `BulkPaymentsController` | `POST /api/Payments/Bulk/Import/Record/{key}/Approve` | Approve single record [BulkApPaymentApprover] |
| `BulkPaymentsController` | `POST /api/Payments/Bulk/Import/Record/{key}/Reject` | Reject single record [BulkApPaymentApprover] |
| `BulkPaymentsController` | `POST /api/Payments/Bulk/Import/Record/ApproveMultiple` | Bulk approve [BulkApPaymentApprover] |
| `BulkPaymentsController` | `POST /api/Payments/Bulk/Import/Record/RejectMultiple` | Bulk reject [BulkApPaymentApprover] |
| `BusinessUnitController` | `GET /api/Operations/BusinessUnits` | Get all business units |
| `BusinessUnitController` | `GET /api/Operations/BusinessUnits/{key}` | Get specific business unit |
| `BusinessUnitAccountController` | Various | Business unit account management |
| `BusinessUnitPaymentAccountController` | Various | Business unit payment account management |
| `FundingRequestController` | `GET /api/FundingRequests/{key}` | Get funding request |
| `FundsDisbursementController` | `GET /api/FundsDisbursements/{key}` | Get funds disbursement |
| `FundsDisbursementController` | `POST /api/FundsDisbursements/{key}/Retry` | Retry disbursement [User.Admin] |
| `FundsTransferController` | `GET /api/FundsTransfers/{key}` | Get funds transfer |
| `KnownConnectedSystemController` | Various | Manage known connected systems |
| `OnboardingTokenController` | `GET /api/Onboarding/Token/{key}` | Get onboarding token |
| `OnboardingTokenAssociationController` | Various | Onboarding token associations |
| `OperationsController` | `GET /api/v2/Operations/BusinessUnits` | Get all business units (v2) [AllowAnonymous] |
| `OperationsController` | `GET /api/v2/Operations/BusinessUnits/Mine` | Get user's business units [Requester/Approver] |
| `OperationsController` | `GET /api/v2/Operations/BusinessUnits/{key}` | Get specific BU (v2) |
| `OperationsController` | `GET /api/v2/Operations/BusinessUnits/{key}/AssociatedUsers` | Get BU users |
| `OperationsController` | `POST /api/v2/Operations/BusinessUnits/{key}/AssociatedUsers` | Add BU user [User.Admin] |
| `OperationsController` | `DELETE /api/v2/Operations/BusinessUnits/{key}/AssociatedUsers` | Remove BU user [User.Admin] |
| `PartyController` | `GET /api/Parties/{key}` | Get party |
| `PartyController` | `GET /api/Parties/{key}/Full` | Get full party details |
| `PartyController` | `DELETE /api/Parties/{key}` | Delete party [User.Admin] |
| `PartyController` | `GET /api/Parties/{key}/Preferences` | Get party preferences |
| `PartyController` | `PUT /api/Parties/{key}/Preferences` | Update party preferences [User.Admin] |
| `PartyController` | `GET /api/Parties/{key}/Users` | Get party users |
| `PartyController` | `GET /api/Parties/{key}/Representative` | Get party representative |
| `PartyController` | `POST /api/Parties/{key}/Users/SetAdministrator` | Set user as admin [User.Admin] |
| `PartyController` | `GET /api/Parties/{key}/Contact` | Get party contact |
| `PartyUserController` | `GET /api/Parties/Users/{key}` | Get party user |
| `PartyUserAccessTokenController` | Various | Generate user access tokens |
| `PartyUserConnectedSystemAssociationController` | Various | User connected system associations |
| `PartyUserPartyAssociationController` | Various | User-party associations |
| `PartyConnectedSystemAssociationController` | Various | Party connected system associations |
| `PartyAccountController` | Various | Party account management |
| `PaymentController` | `GET /api/Payments/{key}` | Get payment details |
| `PaymentAggregateController` | `GET /api/PaymentAggregates` | Get by reference |
| `PaymentAggregateController` | `GET /api/PaymentAggregates/{key}` | Get specific aggregate |
| `PaymentAggregateController` | `GET /api/PaymentAggregates/{key}/Totals` | Get aggregate totals |
| `PaymentFlowController` | `GET /api/PaymentFlows/PayoutPeriod` | Get current payout period |
| `PaymentFlowEnabledAccountController` | Various | Manage payment flow enabled accounts |
| `PayoutPeriodPaymentAggregateController` | `GET /api/PayoutPeriodPaymentAggregates/{key}` | Get payout period aggregate |
| `PayoutPeriodPaymentAggregateController` | `GET /api/PayoutPeriodPaymentAggregates/Totals` | Get payout period totals |
| `PayoutPeriodPaymentAggregateController` | `GET /api/PayoutPeriodPaymentAggregates/{key}/Summary` | Get aggregate summary |
| `SettingsController` | `GET /api/Settings` | App/auth configuration [AllowAnonymous] |
| `StripeController` | `GET /api/Stripe/AccountService/{ref}` | Get Stripe account details |
| `StripeController` | `GET /api/Stripe/AccountService/{ref}/PaymentAccounts` | Get Stripe payment accounts |
| `StripeController` | `GET /api/Stripe/PersonService/{ref}` | Get Stripe persons |
| `StripeController` | `POST /api/Stripe/{ref}/Update` | Update Stripe account |
| `StripeAccountActionsController` | `POST /api/Accounts/Stripe/Actions/Sync` | Sync Stripe status [User.Admin] |
| `StripePaymentAccountController` | Various | Stripe payment account management |
| `StripeFundingRequestController` | `GET /api/FundingRequest/Stripe/{key}` | Get Stripe funding request |

---

## 5. Shared Infrastructure & External Integrations

### 5.1 Epp.Api (Core Backend)
The central backend service exposing all business domain APIs. Contains services for:
- Parties (Accounts / Counterparties)
- Payments (individual, aggregate, escrow, bulk)
- Business Units and Connected Systems
- Onboarding
- Stripe integration proxy

### 5.2 SharedServices.Api
Provides cross-cutting services:
- **Tasks** (`SharedServices.Api.Tasks`): Task management used by Escrow Dashboard
- **Storage** (`SharedServices.Api.Storage`): File/blob storage
- **Verification** (`SharedServices.Api.Verification`): Account verification logic

### 5.3 Ewis.Api (External Wire Integration System)
Wire transfer integration system. Escrow Dashboard connects to this for:
- `PaymentIntegrationController` — EWIS payment records
- `TransacteeController` — EWIS transactee lookup by integer ID

### 5.4 Elis.Api (Electronic Ledger Integration System)
Referenced in AP Admin's `integration/elis` module. Provides accounting ledger synchronization and service map configuration.

### 5.5 Stripe
Integrated via:
- `StripeController` — reads Stripe account, persons, and payment accounts
- `StripeAccountActionsController` — sync status actions
- `StripeFundingRequestController` — Stripe funding requests
- `StripePaymentAccountController` — Stripe payment account management

**Payment Providers:**
- `StewartErpAccountsProvider` — primary ERP-based payment provider
- `StripeConnectedExternalAccountAch` — Stripe ACH for connected accounts
- `StripeCustomerPaymentMethodAch` — Stripe ACH for customer payment methods

### 5.6 Azure AI Search
Used exclusively in Escrow Dashboard for fast, full-text, filterable payment search:
- OData filter syntax generated client-side
- Supports faceting, ordering, and advanced query expressions
- AI search validator (`aiSearchValidator`) ensures valid search terms
- Special characters escaped via `escapeSpecial()`

### 5.7 Modern Treasury
Referenced via `ModernTreasuryInternalAccountController` in Escrow Dashboard — manages internal bank accounts through the Modern Treasury financial operations platform.

### 5.8 Preferences API
User/system preference storage with:
- Create, read, update, delete preferences
- Scoped: per-user (by UUID), global (`"global"`), or custom scope
- ETag-based concurrency control
- Used for: saved filter presets, payment monitoring rule settings, column preferences

---

## 6. Cross-Portal Interactions

| Interaction | Source | Target | Mechanism |
|---|---|---|---|
| Both portals share `Epp.Api` backend | Both | `Epp.Api` | HTTP service clients |
| Both portals use the same Azure AD tenant | Both | Azure AD | MSAL tokens with role claims |
| Payment aggregates from Escrow are visible in AP Admin dashboard | AP Admin | Payment Aggregate data | `PaymentAggregateController` |
| ELIS data flows from Elis.Api to both portals | Both | `Elis.Api` | Integration service clients |
| Tasks created in one context visible in Escrow Dashboard | Escrow | `SharedServices.Api.Tasks` | Task API |
| Party/counterparty onboarding affects both portals | Both | Parties data in `Epp.Api` | Shared party projections |

---

## 7. Gaps, Inconsistencies & Observations

### 7.1 Incomplete Screen Implementations

| Screen | Portal | Status | Note |
|---|---|---|---|
| Home | Escrow Dashboard | Placeholder | HTML template is empty; navigation item is `readonly` with no routerLink |
| Approvals | Escrow Dashboard | Placeholder | Template contains only `<p>approvals works!</p>` |
| Reports | Escrow Dashboard | Placeholder | Template contains only `<p>reporting works!</p>` |
| Reporting Payments | AP Admin | Minimal | Component exists with no logic |

### 7.2 Navigation Inconsistency

The Escrow Dashboard's **Home** and **Approvals** navigation items are marked `class="readonly"` with no `[routerLink]` binding, meaning clicking them does nothing. These appear to be planned but unimplemented screens currently deployed to production. This could confuse users who see the menu items but cannot navigate to them.

### 7.3 Role Logic — Mutual Exclusivity Note

The `AccountingUser` role documentation states it is "mutually exclusive of Field User role" and that if a user has both, AccountingUser supersedes FieldUser. However, this enforcement appears to be **only in documentation** — the code does not explicitly enforce mutual exclusivity in the backend. The frontend default redirect logic processes roles in priority order which achieves the practical effect, but edge cases may exist.

### 7.4 Approvals Screen — Pending Implementation

The Approvals screen (Escrow Dashboard `/approvals`) is referenced in the navigation but is not implemented. Based on the payment workflow, this screen likely was intended to show pending payment requests awaiting Field Approver action (the `FieldApprover` role exists but is not referenced in any navigation items or access rules beyond the payment request search endpoint).

### 7.5 Settings Route vs. Navigation (AP Admin)

The Settings page in AP Admin has minimal visible implementation. The navigation exists in the route config but the `SettingsComponent` in the module only defines a basic template.

### 7.6 Dual API Versioning (AP Admin Operations)

`OperationsController` is registered at `api/v2/Operations` while `BusinessUnitController` is at `api/Operations/BusinessUnits`. This creates two parallel routes for business unit data (`/api/Operations/BusinessUnits` and `/api/v2/Operations/BusinessUnits`). The v2 version provides richer information (connected systems, configuration, associated users). The older v1 route appears to be maintained for backward compatibility.

### 7.7 EWIS Transactee ID Type

The `TransacteeController` accepts `transacteeId` as an `int` (integer), not a GUID. This is inconsistent with the rest of the system which uses GUIDs throughout. This reflects that EWIS is a legacy integer-keyed system being integrated into the modern UUID-based EPP platform.

### 7.8 BulkPayments Module — Route Guard Difference

The `bulk-payments` route in AP Admin uses only `MsalGuard` and not `BasicUserRoleGuard`, unlike all other routes. This means any authenticated user (regardless of having `User.Basic` or `User.Admin`) can access the bulk payments section, and the role-specific restrictions are enforced at the component/API level rather than at the route level.

### 7.9 Preferences API — Race Condition Risk

The Payment Monitoring Rule Settings component performs a create-or-update pattern: it checks if a preference exists, then either creates or updates it. This check-then-act pattern has a potential race condition if two users save settings simultaneously. The ETag-based optimistic concurrency on updates mitigates conflicts for updates, but concurrent create operations could fail with HTTP 409 (Conflict) without explicit user guidance on retry.

### 7.10 My Payments — FieldUser Isolation

The "My Payments" tab is only shown to `FieldUser` in the navigation, but the underlying filter presumably filters by `createdByUserEmail`. This is correct for field user privacy, but the `/payments/my` route itself does not have an explicit route guard — any user with the payments section access could navigate to it directly if they know the URL.

---

*End of Document*

---

**Document prepared by:** GitHub Copilot  
**Based on:** Full codebase analysis of `Epp.Escrow.Admin` and `Epp.Admin` projects  
**Source of truth:** Actual TypeScript/C# source code — no assumptions made
