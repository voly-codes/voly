# Releasing VOLY to PyPI

The release path builds one source distribution and one wheel, validates both,
installs the wheel in a clean environment, and publishes the same artifacts to
PyPI. Publication uses GitHub OIDC Trusted Publishing, so the repository does
not store a long-lived PyPI token.

## One-time setup

1. Create or reserve the `voly` project on PyPI.
2. In the PyPI project, add a GitHub trusted publisher with:
   - owner: `voly-codes`
   - repository: `voly`
   - workflow: `release.yml`
   - environment: `pypi`
3. Create the `pypi` environment in GitHub repository settings.
4. Add a required reviewer to that environment. This is the manual approval
   between a verified build and an irreversible public publication.

Do not add `PYPI_API_TOKEN`. The publish job requests only `id-token: write` and
exchanges GitHub's short-lived identity for a scoped PyPI publishing token.

## Release procedure

1. Change `[project].version` in `pyproject.toml` and merge with green CI.
2. Create a GitHub release with tag `vX.Y.Z`, matching the package version.
3. The release workflow builds and verifies the distributions.
4. Review the workflow result and approve the protected `pypi` environment.
5. Confirm that the new version appears on PyPI and that a clean
   `uvx --from voly==X.Y.Z voly quickstart --check --cwd <repo>` succeeds.

The workflow rejects a tag that does not exactly match the declared version.
PyPI package files cannot be replaced. If a bad version is published, yank it,
fix the problem, increment the patch version, and publish a new release.

## Scope of this stage

This repository is ready for Trusted Publishing, but no package is published
until the PyPI publisher and protected GitHub environment above are configured
and a GitHub release is explicitly published.
