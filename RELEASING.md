# Publishing stackone-adk

Run `Publish to PyPI` manually from `main` with an existing release tag. It tests
and builds the selected release commit, then
uploads those tested distributions from a separate job. It authenticates through
PyPI Trusted Publishing; do not add a `PYPI_API_TOKEN` or `UV_PUBLISH_TOKEN` secret.
Pull requests changing the workflow run the build checks without publishing.

## One-time configuration

In the existing **stackone-adk** project on PyPI, open **Manage → Publishing** and
add a GitHub Trusted Publisher, or reuse the existing one if these fields match:

| Field | Value |
| --- | --- |
| Owner | `StackOneHQ` |
| Repository | `stackone-adk-plugin` |
| Workflow filename | `release.yaml` |
| Environment | `pypi` |

The workflow filename is the filename alone, not its `.github/workflows/` path.
In GitHub, create the `pypi` environment under **Settings → Environments**. Choose
**Selected branches and tags** and allow only the **branch** `main`. Remove any
tag rules, including `v*`. Keep pull-request approval required on `main`.

This environment restriction is required: it ensures publishing uses the reviewed
workflow on `main`. A tag can contain a different workflow, so allowing release
tags into the environment would let that workflow bypass the source checks.

The PyPI configuration is separate from the GitHub environment. Both must match
before an upload can succeed. See the official
[PyPI setup guide](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).

## Ordinary releases

1. Merge the version change, updated lockfile, and release changes into `main`.
2. Tag the intended commit with `v` followed by the exact package version and push
   that tag. The workflow accepts stable `vMAJOR.MINOR.PATCH` tags only.
3. Open **Actions → Publish to PyPI → Run workflow**. Select branch `main` and
   enter the tag. Pushing a tag alone does not publish.
4. Watch the run. It checks the selected commit against the explicit remote main
   branch before running package tooling, then reads metadata with isolated
   Python. It rejects unmerged source or a tag that disagrees with `pyproject.toml`.
5. Confirm both distribution files appear on the version-specific PyPI page.
6. Check installation and imports in a fresh environment, as shown below.

The selected tag can predate the workflow because the workflow itself runs from
`main`. Never move an existing release tag or change an already published version.

## First release from the existing commit

The intended `0.3.0` commit predates this workflow. After the workflow is merged and
the PyPI publisher is configured, create the tag at the original commit and run
the workflow from `main` with that existing tag:

```bash
git fetch origin main --tags
git tag v0.3.0 47b20e6eb90aa7d36a87a0df6720ae37cf1feb44
git push origin refs/tags/v0.3.0
gh workflow run release.yaml --repo StackOneHQ/stackone-adk-plugin \
  --ref main -f tag=v0.3.0
```

If the tag already exists, confirm its commit instead of recreating it. Manual
runs check out the tag's code while using the workflow from `main`; they do not
publish whatever happens to be the latest commit on `main`.

After publishing, verify https://pypi.org/project/stackone-adk/0.3.0/ and run:

```bash
uv run --isolated --no-project --python 3.12 \
  --with 'stackone-adk==0.3.0' --with 'stackone-ai==3.0.0' \
  python -I -c 'from importlib.metadata import version; from stackone_adk import StackOnePlugin; from stackone_ai import StackOneToolSet; print(version("stackone-adk"), version("stackone-ai"))'
```

A package-age policy may temporarily prevent a new release from installing on a
managed device. Wait for the policy window or request an administrator exception;
do not disable endpoint protection. A failed upload due to an unmatched Trusted
Publisher needs the PyPI settings corrected, not a replacement API token.
