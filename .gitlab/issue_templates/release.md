## 🚀 Release — vX.Y.Z

### Release Type
- [ ] Major (breaking changes)
- [ ] Minor (new features, backward-compatible)
- [ ] Patch (bug fixes only)

### Release Branch
- **From:** `release/vX.Y.Z`
- **Into:** `main`

### Changelog

#### ✨ New Features
- 

#### 🐛 Bug Fixes
- 

#### 🔒 Security
- 

#### ♻️ Improvements & Refactors
- 

#### 💥 Breaking Changes
- 

#### 📦 Dependency Updates
- 

### Included MRs
- !
- !

---

## Release Checks

#### 🧩 Odoo Modules / Backend
- [ ] All custom addon versions bumped in `__manifest__.py`
- [ ] All database migration scripts present and tested against a production-like dataset
- [ ] Module upgrade list prepared (`-u module1,module2`)
- [ ] New Python dependencies added to `requirements.txt` and Docker image rebuilt
- [ ] Access rights and record rules reviewed for new/changed models
- [ ] Scheduled actions and automation rules verified in staging
- [ ] `changes.md` updated with this release's entries

#### 📱 Mobile API
- [ ] API contract changes communicated to mobile team
- [ ] Breaking API changes versioned or backward-compatible shim in place
- [ ] API endpoints smoke tested against staging
- [ ] Mobile app version compatibility confirmed

---

## Pre-Release Checklist
- [ ] All intended MRs merged into the release branch
- [ ] All CI pipelines green on release branch
- [ ] Full regression / smoke test passed in staging Odoo instance
- [ ] Docker image built and tested: `docker compose -f docker-compose.prod.yaml up`
- [ ] `odoo.conf` production settings reviewed (workers, db_maxconn, etc.)
- [ ] Security scan completed — no new critical findings

## Post-Merge Steps
- [ ] Tag the release: `git tag vX.Y.Z && git push origin vX.Y.Z`
- [ ] Publish release notes in GitLab Releases
- [ ] Deploy to production (rebuild Docker image, run `odoo -u <modules>`)
- [ ] Notify stakeholders / post in team channel
- [ ] Monitor Odoo server logs for errors for 30 min post-deploy

## Rollback Plan
1. Restore database from pre-deploy backup
2. Roll back Docker image to previous tag
3. 

---
/label ~release
