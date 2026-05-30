# Audit: Lead & Inquiry Write Authorization

This document summarizes the current state of authentication and role checks for Lead and Inquiry write endpoints across both the Next.js BFF (`vecrm-portal`) and the Frappe Backend (`vecrm`).

## Summary of BFF Handlers

| Endpoint | Method | Operation | Current Auth | Gap? |
|---|---|---|---|---|
| `/api/leads` | POST | `create_lead` | **NONE** (No role check in BFF) | Yes — missing all role/auth guards. |
| `/api/leads/[name]/touchpoints` | POST | `create_touchpoint` | `canReadLead` | Partial — ties write access strictly to read access. |
| `/api/leads/[name]/followup` | POST | `update_lead_followup` | `canReadLead` | Partial — ties write access strictly to read access. |
| `/api/leads/[name]/close` | POST | `close_lead` | `canReadLead` | Partial — ties write access strictly to read access. |
| `/api/leads/[name]/attachments` | POST | `upload_lead_attachment` | `canReadLead` | Partial — ties write access strictly to read access. |
| `/api/leads/[name]/attachments` | DELETE | `delete_lead_attachment` | `canReadLead` | Partial — ties write access strictly to read access. |
| `/api/leads/[name]/convert` | POST | `convert_lead_to_inquiry` | `canReadLead` | Partial — ties write access strictly to read access. |
| `/api/inquiries/[name]/close` | POST | `close_inquiry` | **NONE** (No role check in BFF) | Yes — missing all role/auth/row guards. |

## Backend Operations (`vecrm/api.py`)

All of the following `vecrm.api.*` endpoints are decorated with `@frappe.whitelist()` (without `allow_guest=True`), meaning they require *a* valid portal session, but they **completely lack internal role or ownership checks**:
- `create_lead`
- `create_touchpoint`
- `update_lead_followup`
- `close_lead`
- `upload_lead_attachment`
- `delete_lead_attachment`
- `convert_lead_to_inquiry`
- `close_inquiry`

As noted in `create_touchpoint`'s docstring: *"Permission model: BFF-layer enforcement only"*. The backend delegates 100% of the authorization responsibility to the Next.js BFF layer.

## Identified Gaps & Risks

1. **Unprotected Endpoints (`/api/leads` POST & `/api/inquiries/[name]/close` POST)**
   - These BFF routes extract the cookie and proxy to the backend without invoking `getVecrmSession()`, `isEngineerRole()`, or `canReadLead()`. 
   - **Risk:** Any authenticated user (including Engineers and HR) could theoretically hit these APIs to create leads or close any inquiry, despite UI buttons being hidden.

2. **Read == Write Equivalence**
   - For all protected endpoints, the BFF uses `canReadLead` as the authorization gate.
   - **Risk:** If a role (e.g., Sales Head) is granted read access to a lead, they implicitly gain write access (close, convert, followup, etc.). While this matches current business logic, it conflates read visibility with write permissions, making granular "read-only" views impossible in the future without refactoring.

3. **No Backend Defense-in-Depth**
   - The Frappe backend blindly trusts the BFF to scope access.
   - **Risk:** If a BFF endpoint is misconfigured (as seen with `create_lead` and `close_inquiry`), the backend performs the write without enforcing row-level ownership or role limits. A malicious user with a valid Frappe service account could bypass all constraints.
