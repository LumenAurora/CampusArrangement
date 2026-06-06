# Project Rules - CampusArrangement

## Git Workflow

### Branch Naming Convention
- `feat/xxx` - New features
- `fix/xxx` - Bug fixes
- `refactor/xxx` - Code refactoring
- `docs/xxx` - Documentation updates

### Branch Creation Rules
1. Always sync local master before creating a new branch: `git checkout master && git pull origin master`
2. Create branch from the latest master: `git checkout -b feat/xxx origin/master`
3. Never create branches from other feature branches unless explicitly needed

### Merge Conflict Resolution
1. NEVER use `--theirs` or `--ours` to resolve all conflicts at once
2. Must review each conflicting file individually
3. After resolving conflicts, run `git diff <source-branch> HEAD` to verify no changes are lost
4. Pay special attention to files modified by both branches

### Pre-Push Checklist
1. Verify code compiles/runs without errors
2. Run `git diff origin/master...HEAD` to review all changes
3. Ensure no unintended files are included (temp files, .env, etc.)
4. Commit message should be clear and descriptive

### Commit Messages
- Use conventional commit format: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`
- Keep messages concise but descriptive
- Example: `feat: add default position option for time slots`

### Force Push
- NEVER force push to master/main
- Only force push to your own feature branch when necessary
- Always warn the user before force pushing

## Code Style
- Python: Follow PEP 8
- Use type hints for function signatures
- Use `from __future__ import annotations` for forward references
