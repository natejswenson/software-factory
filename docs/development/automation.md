# Automatic main merges and releases

Every ready same-repository PR targeting `main` automatically squash-merges when
the required GitHub Actions `test` check passes. Drafts stay drafts; marking one
ready reruns CI. Fork PRs and authors without repository write permission need a
maintainer's merge. Native branch protection also prevents direct main pushes,
force pushes and deletion, including by administrators.

Each nonempty commit must add or semantically update a Python unittest test with
assertions under `tests/test*.py`, including documentation/configuration commits.
The associated test must actually pass in the final suite. A test in the final
commit cannot cover earlier untested commits. Comment/docstring-only edits,
test deletion, skipped tests and undiscovered helper classes do not count.
CI runs the complete suite, source checks, wheel/source build and isolated
installation smoke on Linux with Python 3.11/3.14 and macOS with Python 3.14.
The `test` aggregate never passes if any matrix leg fails or is canceled.
These gates prove structural association and execution, not that a test is
relevant or exhaustive; factory review must still inspect behavior coverage.

After each successful main merge, Release verifies the exact immutable main
commit, builds from its version tag and publishes a GitHub patch release with
wheel, source archive and `SHA256SUMS`. Versions start at `v0.2.1` and increase
above the highest stable tag. Build-time setuptools-scm supplies matching
package/runtime versions; it is not a runtime dependency. No PyPI upload or
standing release secret is needed. Download packages from
[GitHub releases](https://github.com/natejswenson/software-factory/releases).

The trusted automatic merge job dispatches the exact observed merge commit
because ordinary push workflows do not run for merges made with `GITHUB_TOKEN`.
It never checks out PR code or consumes PR artifacts. Failed dispatch can be
retried by rerunning Auto merge: an already-merged matching-head PR redispatches
the same commit. Release verifies existing tags/releases/assets on retry and
refuses collisions; it uploads to a draft before publishing.

Allocation, build and publication share one noncanceling release queue. GitHub
allows 100 pending runs; overflow is canceled and needs an explicit retry.
Inspect canceled/failed Release runs and dispatch the missing exact main commit:

```sh
gh workflow run release.yml --ref main -f commit=<full-main-commit-sha>
```

Retries of an already published commit verify its existing assets rather than
creating another version. Cancellation/outages are visible in Actions; no
unbounded queue or guaranteed event delivery is claimed.
