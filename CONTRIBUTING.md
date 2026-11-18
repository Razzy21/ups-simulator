# Contributing

## Branches

- `main` is always working and always passes tests. Nobody pushes to it directly.
- Work on short-lived branches cut from `main`:
  - `feat/<short-name>` new work
  - `fix/<short-name>` bug fixes
  - `docs/<short-name>` documentation
- Example: `feat/core-load-scenario`

## Pull requests

1. Pull the latest `main`, then branch.
2. Commit small, with clear messages (`core: load scenario from JSON`).
3. Run `pytest` before pushing.
4. Open a PR into `main` using the template.
5. At least one teammate reviews and approves.
6. Squash and merge, then delete the branch.

Keep PRs small (aim for under ~300 lines changed) so reviews stay quick.

## Repo settings to turn on (repo owner, once)

- Protect `main`: require a PR and 1 approval, block direct pushes.
- Enable "Automatically delete head branches".
- Set the default merge method to squash.

## Code rules

- `ups/core` has no web dependencies.
- Every core behavior has a unit test.
- Scenario files must validate against `schema/`.
