## 🚨 Hotfix

> This is a production hotfix — apply the expedited review process.

### Incident / Issue
Fixes #<!-- GitLab issue number -->

### Root Cause
<!-- What caused the issue? -->

### Fix Description
<!-- What was changed and why it resolves the issue -->

### Risk Assessment
- **Blast radius of the bug:** <!-- Who / what is affected? -->
- **Blast radius of this fix:** <!-- Could this break anything else? -->
- **Rollback plan:** <!-- e.g. revert module to previous version, restore DB backup -->

## Project-Specific Notes

#### 🧩 Odoo Module / Backend
- **Affected module(s):** <!-- e.g. custom_ictpack, contract -->
- **Odoo model / method affected:** <!-- e.g. account.move._post() -->
- **Database changes required:** <!-- yes / no — describe if yes -->
- **Module upgrade needed on deploy (`-u module`):** <!-- yes / no -->
- **Data integrity impact:** <!-- yes / no — describe if yes -->

#### 📱 Mobile API
<!-- Fill in only if the hotfix affects the mobile app API -->
- **Affected endpoint:** <!-- e.g. GET /api/v1/invoices -->
- **Mobile app versions impacted:**
- **Backward compatible after fix:** <!-- yes / no -->

---

## Testing
- [ ] Reproduced the bug before the fix
- [ ] Verified fix resolves the issue locally (Odoo instance)
- [ ] Tested against staging database
- [ ] Regression test added to prevent recurrence

## Deployment
- [ ] Can be deployed without downtime
- [ ] Requires database migration script
- [ ] Requires `odoo -u <module>` after deploy
- [ ] Requires Docker image rebuild
- [ ] Requires config / env var changes — list them:

## Post-Deploy Verification
- [ ] 
- [ ] 

## Follow-Up
- [ ] Follow-up issue opened: #

---
/label ~hotfix ~bug
/assign me
