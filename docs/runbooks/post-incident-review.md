# Post-Incident Review Template

## Incident Information

| Field | Value |
|-------|-------|
| **Incident ID** | INC-YYYY-NNN |
| **Date/Time** | YYYY-MM-DD HH:MM - HH:MM (timezone) |
| **Duration** | X hours Y minutes |
| **Severity** | SEV-1 / SEV-2 / SEV-3 |
| **Impacted Services** | [List services] |
| **Customer Impact** | [Description] |
| **Incident Commander** | [Name] |
| **Author** | [Name] |
| **Review Date** | YYYY-MM-DD |

---

## Severity Definitions

| Severity | Definition | Examples |
|----------|------------|----------|
| **SEV-1** | Critical impact. Complete service outage or data loss affecting all users | Backend down, database corruption |
| **SEV-2** | High impact. Major feature unavailable or significant degradation | Authentication broken, high error rate |
| **SEV-3** | Medium impact. Minor feature unavailable or slight degradation | Slow queries, partial functionality loss |

---

## Executive Summary

[2-3 sentence summary of what happened, impact, and resolution. This should be understandable by non-technical stakeholders.]

**Example:**
> On January 15, 2024, the backend API experienced a complete outage for 45 minutes due to database connection pool exhaustion. Approximately 5,000 API requests failed during this period. The issue was resolved by restarting the backend service and increasing the connection pool size.

---

## Timeline

All times in UTC.

| Time | Event |
|------|-------|
| HH:MM | [First indication of problem - monitoring alert, user report, etc.] |
| HH:MM | [Alert fired / Incident declared] |
| HH:MM | [First responder engaged] |
| HH:MM | [Diagnosis started] |
| HH:MM | [Key diagnostic finding] |
| HH:MM | [Root cause identified] |
| HH:MM | [Mitigation applied] |
| HH:MM | [Service restored / Metrics recovered] |
| HH:MM | [Incident closed] |

---

## Impact Analysis

### User Impact

| Metric | Value |
|--------|-------|
| Affected users | [Number or percentage] |
| Failed requests | [Count] |
| Error rate during incident | [Percentage] |
| Duration of impact | [Minutes/hours] |
| Regions affected | [List or "All"] |

### Business Impact

| Area | Impact |
|------|--------|
| Revenue impact | [Estimated $ or "None" / "Minimal" / "Significant"] |
| SLA impact | [Describe SLA breach if any] |
| Customer complaints | [Count or "None"] |
| Data loss | [Describe or "None"] |
| Reputation impact | [Assessment] |

---

## Root Cause Analysis

### What Happened

[Detailed technical description of the failure mechanism. Be specific about what broke and how.]

**Example:**
> The PostgreSQL connection pool in the backend service was configured with a maximum of 10 connections. A combination of slow database queries and increased traffic caused all connections to be checked out simultaneously. New requests were blocked waiting for connections, leading to timeouts and 503 errors.

### Why It Happened

[Underlying cause - not just the trigger. What conditions allowed this to happen?]

**Example:**
> The connection pool was sized for average load but not peak load. Additionally, a recently deployed feature introduced a slow query that held connections longer than expected. There was no alerting on connection pool utilization.

### Contributing Factors

1. [Factor 1 - e.g., "Connection pool size too small for peak load"]
2. [Factor 2 - e.g., "Slow query introduced in recent deployment"]
3. [Factor 3 - e.g., "No monitoring on pool utilization"]
4. [Factor 4 - e.g., "Load testing did not cover this scenario"]

### 5 Whys Analysis

| # | Question | Answer |
|---|----------|--------|
| 1 | Why did users see 503 errors? | Because backend requests timed out waiting for database connections |
| 2 | Why were requests waiting for connections? | Because all connections in the pool were in use |
| 3 | Why were all connections in use? | Because queries were taking longer than expected |
| 4 | Why were queries taking longer? | Because a new feature added an unoptimized query |
| 5 | Why was the query unoptimized? | Because load testing didn't cover this query path |

---

## Detection and Response

### How Was the Incident Detected?

- [ ] Automated alerting (Prometheus/PagerDuty)
- [ ] Customer report
- [ ] Internal user report
- [ ] Routine monitoring review
- [ ] Other: [Describe]

### Detection Metrics

| Metric | Value |
|--------|-------|
| Time from first impact to detection | [X minutes] |
| Time from detection to first responder | [X minutes] |
| Time from first responder to mitigation | [X minutes] |
| Time from mitigation to resolution | [X minutes] |

### Response Evaluation

**What went well:**
- [Item 1]
- [Item 2]
- [Item 3]

**What could be improved:**
- [Item 1]
- [Item 2]
- [Item 3]

**Luck / Near Misses:**
- [Describe any factors that prevented worse outcomes]
- [Describe any "near misses" that could have escalated the incident]

---

## Resolution

### Immediate Actions Taken

1. [Action 1 - e.g., "Restarted backend service to clear stuck connections"]
2. [Action 2 - e.g., "Increased connection pool size from 10 to 25"]
3. [Action 3 - e.g., "Killed long-running queries"]

### Verification

```bash
# Commands used to verify resolution
[Commands used to confirm service recovery]
```

### Permanent Fix

[Description of permanent solution, or reference to ticket for follow-up]

**Example:**
> Created JIRA-123 to optimize the slow query. Increased default connection pool size in configuration. Added connection pool utilization alert (JIRA-124).

---

## Action Items

| ID | Action | Owner | Priority | Due Date | Status | Ticket |
|----|--------|-------|----------|----------|--------|--------|
| 1 | [Action description] | [Name] | P1/P2/P3 | YYYY-MM-DD | Open | JIRA-XXX |
| 2 | [Action description] | [Name] | P1/P2/P3 | YYYY-MM-DD | Open | JIRA-XXX |
| 3 | [Action description] | [Name] | P1/P2/P3 | YYYY-MM-DD | Open | JIRA-XXX |

### Priority Definitions

- **P1**: Must be completed within 1 week. Directly prevents recurrence.
- **P2**: Should be completed within 1 month. Improves detection/response.
- **P3**: Complete within quarter. General improvement.

---

## Lessons Learned

### What We Learned

1. [Learning 1 - e.g., "Connection pool sizing must account for peak load, not average"]
2. [Learning 2 - e.g., "Query performance testing should be part of code review"]

### Process Improvements

1. [Improvement 1 - e.g., "Add connection pool utilization to standard dashboard"]
2. [Improvement 2 - e.g., "Include database query analysis in PR checklist"]

### Monitoring Improvements

1. [Improvement 1 - e.g., "Add alert for connection pool > 80% utilized"]
2. [Improvement 2 - e.g., "Add slow query logging threshold"]

### Runbook Updates

- [ ] [Runbook name] needs update: [Description of update needed]
- [ ] New runbook needed: [Description of new runbook]

---

## Appendix

### Relevant Logs

```
[Paste relevant log snippets that helped diagnose the issue]
```

### Relevant Metrics

[Include screenshots or links to dashboards showing the incident. Annotate key moments.]

- Dashboard URL: http://localhost:3000/d/xxx
- Prometheus query: `[query used for diagnosis]`

### Communication Log

| Time | Channel | Message |
|------|---------|---------|
| HH:MM | #incidents | [Summary of communication] |
| HH:MM | Status Page | [External communication] |

### References

- [Link to incident Slack channel/thread]
- [Link to related tickets/PRs]
- [Link to relevant documentation]
- [Link to previous similar incidents]

---

## Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Incident Commander | | | |
| Team Lead | | | |
| Engineering Manager | | | |

---

## Review Meeting Notes

**Date:** YYYY-MM-DD
**Attendees:** [List attendees]

### Discussion Points

1. [Point discussed]
2. [Point discussed]

### Decisions Made

1. [Decision]
2. [Decision]

### Follow-up Required

1. [Follow-up item]
2. [Follow-up item]

---

## Revision History

| Date | Author | Change |
|------|--------|--------|
|  | Tyler Evans | Initial template creation |
| [Date] | [Author] | [Change description] |
