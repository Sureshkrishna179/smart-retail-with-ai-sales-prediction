# Git Preparation & CI/CD Setup

To complete Phase 5 of the restructuring, you must run the following commands to safely manage secrets and git history before pushing to GitHub.

## 1. Clean Git History
If you accidentally committed `.env` or `.pkl` files in the past, remove them from history:

```bash
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch .env" \
  --prune-empty --tag-name-filter cat -- --all

git push origin --force --all
git push origin --force --tags
```

## 2. GitHub Secrets
In GitHub Settings → Secrets → Actions, add the following Repository Secrets:
- `CI_DB_PASSWORD` (Your secure database password)
- `CI_JWT_SECRET` (Run `python -c "import secrets; print(secrets.token_hex(32))"`)
- `FIREBASE_TOKEN` (Run `firebase login:ci` locally to get this)

## 3. Branch Protection
In GitHub Settings → Branches → Add rule for `main`:
- Require pull request reviews before merging
- Require status checks to pass (CI)
- Require branches to be up to date

## 4. Final Pre-push Checks
Run these to verify everything locally:
```bash
bandit -r src/ -ll
safety check
pytest tests/ -v
```
