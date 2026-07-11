# Frontend-Backend Integration Checks

This document defines all 13 integration categories that the audit checks.

## Part 2: Frontend-Backend Integration Checks

### 1. API Contract/Schema Drift
**What to check:** Frontend types match backend responses; check against OpenAPI/GraphQL
**Layer:** Source-level (type contract comparison) + Browser-level (network interception)
**Severity:** High

### 2. Type Mismatches
**What to check:** Backend sends string, frontend assumes number (silent formatting bugs)
**Layer:** Source-level (TypeScript analysis) + Browser-level (runtime type checking)
**Severity:** Medium

### 3. Loading/Error/Empty State Wiring
**What to check:** Every API call has distinct branches for loading, success, empty, error, timeout
**Layer:** Source-level (component analysis) + Browser-level (network monitoring)
**Severity:** High

### 4. Unhandled Promise Rejections
**What to check:** Backend returns error but UI shows no change
**Layer:** Browser-level (console monitoring) + Source-level (error handling analysis)
**Severity:** High

### 5. Race Conditions/Stale Data
**What to check:** Slow older responses overwriting newer ones; in-flight requests aborted
**Layer:** Browser-level (network timing analysis)
**Severity:** High

### 6. Optimistic UI Correctness
**What to check:** Rollback behavior when server call fails after optimistic update
**Layer:** Browser-level (interaction testing) + Source-level (pattern analysis)
**Severity:** Medium

### 7. Auth/Session Boundary Handling
**What to check:** Token expiry behavior; 401 vs 403 handled distinctly
**Layer:** Browser-level (network interception) + Source-level (auth pattern analysis)
**Severity:** Critical

### 8. Latency/Timeout Behavior
**What to check:** Loading feedback for slow calls; retry path for timeouts
**Layer:** Browser-level (network throttling + timing)
**Severity:** Medium

### 9. Pagination/Data Consistency
**What to check:** Frontend handles changing pagination params correctly
**Layer:** Browser-level (network analysis) + Source-level (pagination logic)
**Severity:** Medium

### 10. Real-time/Websocket Sync
**What to check:** Websocket updates reconciled with REST state
**Layer:** Browser-level (websocket monitoring)
**Severity:** Medium

### 11. File Upload/Download Edge Cases
**What to check:** Large files, wrong types, network interruption handling
**Layer:** Browser-level (network testing)
**Severity:** Medium

### 12. Idempotency/Double-Submit
**What to check:** Rapid double-click protection on submit actions
**Layer:** Browser-level (interaction testing)
**Severity:** High

### 13. Localization/Timezone Mismatches
**What to check:** Dates converted from backend timezone, not shown raw
**Layer:** Browser-level (display analysis) + Source-level (date handling)
**Severity:** Medium

---

## Severity Definitions

| Severity | Definition |
|----------|------------|
| **Critical** | Breaks core user flows, causes data loss/corruption, security/auth issues |
| **High** | Damages user trust or usability but doesn't break core flows |
| **Medium** | Visible inconsistency affecting perceived quality/professionalism |
| **Low** | Minor polish issues |
