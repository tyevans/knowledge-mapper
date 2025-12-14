# Runbook Template
#
# Copy this template when creating new runbooks.
# Replace placeholders with specific content.
#
# Template sections:
# - Overview: Alert metadata and impact description
# - Quick Reference: One-glance info for rapid response
# - Diagnosis Steps: Numbered investigation steps
# - Resolution Steps: Options (A, B, C) for different root causes
# - Escalation: When and who to escalate to
# - Post-Incident: Checklist after resolution
# - Related Resources: Links to documentation

# [ALERT NAME] Runbook

## Overview

**Alert Name:** [Alert name from Prometheus]
**Severity:** [critical/warning/info]
**Service:** [Affected service name]
**Last Updated:** [YYYY-MM-DD]
**Author:** [Author name]

### Description

[Brief description of what this alert indicates and why it matters]

### Impact

[Description of user/business impact when this alert fires]

---

## Quick Reference

| Item | Value |
|------|-------|
| **Dashboard** | [Link to relevant Grafana dashboard] |
| **Logs** | [Loki query or log location] |
| **Metrics** | [Key Prometheus metrics to check] |
| **Escalation** | [Who to contact if unresolved] |

---

## Diagnosis Steps

### 1. Initial Assessment

```bash
# Check service status
docker compose ps

# Check recent logs
docker compose logs --tail=100 [service]
```

### 2. [Specific Diagnosis Step]

[Detailed steps for diagnosis]

### 3. [Additional Diagnosis Steps]

[Continue with numbered steps]

---

## Resolution Steps

### Option A: [Resolution Name]

**When to use:** [Conditions for this resolution]

```bash
# Commands to execute
[specific commands]
```

**Expected outcome:** [What should happen after running]

### Option B: [Alternative Resolution]

**When to use:** [Conditions for this resolution]

[Steps for alternative resolution]

---

## Escalation

### When to Escalate

- [ ] Issue not resolved within [X] minutes
- [ ] Root cause is unclear
- [ ] Multiple services affected
- [ ] Data integrity concerns

### Escalation Contacts

| Role | Contact | Method |
|------|---------|--------|
| On-Call Engineer | [TBD] | [Slack/Phone] |
| Team Lead | [TBD] | [Slack/Phone] |
| Infrastructure | [TBD] | [Slack/Phone] |

---

## Post-Incident

After resolving the incident:

1. [ ] Document timeline of events
2. [ ] Identify root cause
3. [ ] Create follow-up tickets for improvements
4. [ ] Schedule post-incident review if severity warrants
5. [ ] Update this runbook with learnings

---

## Related Resources

- [Link to architecture documentation]
- [Link to related ADRs]
- [Link to monitoring dashboards]

---

## Revision History

| Date | Author | Change |
|------|--------|--------|
| [Date] | [Author] | Initial creation |
