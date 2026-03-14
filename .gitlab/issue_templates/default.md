## Summary
<!-- What does this MR do and why? -->

Closes #<!-- GitLab issue number -->

## Changes
- 
- 
- 

## Type of Change
- [ ] 🐛 Bug fix (non-breaking)
- [ ] ✨ New feature (non-breaking)
- [ ] 💥 Breaking change
- [ ] ♻️  Refactor / code quality
- [ ] 📦 Dependency update
- [ ] 🔒 Security fix
- [ ] 📝 Docs / config only

## Project-Specific Checklist

#### 🧩 Odoo Module / Backend
- [ ] Module `__manifest__.py` version bumped if applicable
- [ ] Database migration script added under `migrations/` if data or schema changed
- [ ] New models/fields have correct access rights defined in `security/ir.model.access.csv`
- [ ] Record rules reviewed — no unintended data exposure between companies/users
- [ ] No raw SQL unless absolutely necessary; ORM used correctly
- [ ] N+1 queries avoided — `read_group`, prefetch, or SQL optimizations applied where needed
- [ ] `onchange`, `compute`, and `constraint` methods are side-effect free and tested
- [ ] New Python dependencies added to `requirements.txt`

#### 📱 Mobile API
<!-- Fill in only if this MR affects the API consumed by the mobile app -->
- [ ] API contract unchanged — or change communicated to mobile team
- [ ] New/modified endpoints are authenticated (API key / session) and authorized
- [ ] Response structure follows existing API conventions
- [ ] Backward-compatible — existing mobile app versions will not break
- [ ] Error responses return appropriate HTTP status codes and messages

---

## Testing
- [ ] Manually tested in local Odoo instance
- [ ] Tested against staging database
- [ ] Automated tests added / updated (if applicable)

<details>
<summary>Manual test steps</summary>

1. 
2. 
3. 

</details>

## Screenshots
<!-- For UI changes — before/after screenshots -->

| Before | After |
|--------|-------|
|        |       |

## General Checklist
- [ ] Self-reviewed the diff
- [ ] Follows project code style and conventions
- [ ] No leftover debug code, `_logger.debug`, or TODO comments
- [ ] All CI checks pass
- [ ] No secrets or credentials committed
- [ ] `README.md` or module docs updated if behaviour changed

## Deployment Notes
<!-- Odoo module upgrade required? (-u module_name) | Docker image rebuild? | Config changes? -->

## Reviewer Notes
<!-- Specific areas for focused review, known trade-offs, or context that helps -->

---
/assign me
