"""Allocate and reconcile tested GitHub patch releases, one exact main commit.

The whole release workflow is serialized, including allocation and build.
Versions come from local tags through setuptools-scm; no version commit is made.
"""

import argparse
import hashlib
import json
import os
import re
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.ci_policy import git
from scripts.github_api import api, command, repository, sha

TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
FLOOR = (0, 2, 0)


def select_version(tags: dict[str, str], commit: str) -> str:
    versions = {name: tuple(map(int, TAG.fullmatch(name).groups())) for name in tags if TAG.fullmatch(name)}
    own = [versions[name] for name in versions if tags[name] == commit]
    if len(own) > 1:
        raise ValueError("Multiple release versions point at this commit; inspect before retrying.")
    if own:
        version = own[0]
    else:
        major, minor, patch = max([FLOOR, *versions.values()])
        version = (major, minor, patch + 1)
    return ".".join(map(str, version))


def prepare(repo: Path, commit: str, *, checkout: bool = False) -> dict[str, str]:
    sha(commit)
    if commit not in git(repo, "rev-list", "--first-parent", "origin/main").splitlines():
        raise ValueError("Release commit must be on main's first-parent history.")
    if git(repo, "status", "--porcelain").strip():
        raise ValueError("Release source must be clean.")
    if checkout:
        git(repo, "checkout", "--detach", commit)
    if git(repo, "rev-parse", "HEAD").strip() != commit:
        raise ValueError("Release checkout must equal the requested commit.")
    tags = {
        tag: git(repo, "rev-parse", f"{tag}^{{commit}}").strip()
        for tag in git(repo, "tag", "--list", "v*").splitlines()
        if TAG.fullmatch(tag)
    }
    version = select_version(tags, commit)
    tag = f"v{version}"
    if tag not in tags:
        git(repo, "-c", "tag.gpgSign=false", "tag", tag, commit)
    return {"version": version, "tag": tag, "commit": commit}


def archive_version(path: Path) -> str:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(names) != 1:
                raise ValueError("Wheel needs exactly one package metadata file.")
            if archive.getinfo(names[0]).file_size > 1024 * 1024:
                raise ValueError("Wheel package metadata exceeds its bound.")
            contents = archive.read(names[0])
    else:
        with tarfile.open(path, "r:gz") as archive:
            entries = [
                entry
                for entry in archive.getmembers()
                if len(Path(entry.name).parts) == 2 and entry.name.endswith("/PKG-INFO")
            ]
            if len(entries) != 1 or not entries[0].isfile() or entries[0].size > 1024 * 1024:
                raise ValueError("Source archive needs bounded, regular root package metadata.")
            contents = archive.extractfile(entries[0]).read()
    metadata = BytesParser().parsebytes(contents)
    if metadata["Name"] != "software-factory" or not metadata["Version"]:
        raise ValueError("Unexpected package metadata.")
    return metadata["Version"]


def validate_assets(directory: Path, version: str) -> list[Path]:
    if not TAG.fullmatch(f"v{version}"):
        raise ValueError("A stable release version is required.")
    expected = [
        directory / f"software_factory-{version}-py3-none-any.whl",
        directory / f"software_factory-{version}.tar.gz",
    ]
    for path in expected:
        if not path.is_file() or archive_version(path) != version:
            raise ValueError("Missing archive or package version differs from release version.")
    return expected


def checksums(paths: list[Path]) -> str:
    return "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in paths)


def tag_commit(repo: str, tag: str) -> str | None:
    ref = api(f"repos/{repo}/git/ref/tags/{tag}", missing=True)
    if ref is None:
        return None
    obj = ref["object"]
    for _ in range(4):
        if obj["type"] == "commit":
            return sha(obj["sha"])
        if obj["type"] != "tag":
            break
        obj = api(f"repos/{repo}/git/tags/{sha(obj['sha'])}")["object"]
    raise ValueError("Release tag does not resolve to a commit.")


def find_release(repo: str, tag: str) -> dict | None:
    """Find drafts as well as published releases with authenticated push access."""
    for page in range(1, 101):
        records = api(f"repos/{repo}/releases?per_page=100&page={page}")
        for record in records:
            if record["tag_name"] == tag:
                return record
        if len(records) < 100:
            return None
    raise ValueError("Release lookup exceeded its pagination bound; inspect before retrying.")


def require_release(repo: str, tag: str) -> dict:
    record = find_release(repo, tag)
    if record is None:
        raise ValueError("Expected release was not observed after mutation.")
    return record


def should_mark_latest(repo: str, version: str) -> bool:
    candidate = TAG.fullmatch(f"v{version}")
    if candidate is None:
        raise ValueError("A stable release version is required.")
    latest = api(f"repos/{repo}/releases/latest", missing=True)
    if latest is None:
        return True
    observed = TAG.fullmatch(latest["tag_name"])
    if observed is None:
        raise ValueError("Latest release has an unexpected version; inspect before publishing.")
    return tuple(map(int, candidate.groups())) >= tuple(map(int, observed.groups()))


def verify_published(repo: str, tag: str, version: str, release: dict) -> None:
    expected = {f"software_factory-{version}-py3-none-any.whl", f"software_factory-{version}.tar.gz", "SHA256SUMS"}
    if {asset["name"] for asset in release["assets"]} != expected:
        raise ValueError("Release assets are incomplete or unexpected.")
    with TemporaryDirectory(prefix="factory-release-readback-") as temporary:
        folder = Path(temporary)
        command("gh", "release", "download", tag, "--repo", repo, "--dir", str(folder))
        paths = validate_assets(folder, version)
        if (folder / "SHA256SUMS").read_text() != checksums(paths):
            raise ValueError("Published archive checksums do not match.")


def publish(repo: str, commit: str, version: str, directory: Path) -> dict[str, str]:
    repository(repo)
    sha(commit)
    assets = validate_assets(directory, version)
    tag = f"v{version}"
    observed = tag_commit(repo, tag)
    if observed is not None and observed != commit:
        raise ValueError("Release tag points at another commit; refusing to move it.")
    if observed is None:
        api(f"repos/{repo}/git/refs", method="POST", data={"ref": f"refs/tags/{tag}", "sha": commit})
    if tag_commit(repo, tag) != commit:
        raise ValueError("Remote release tag does not match the tested commit.")
    release = find_release(repo, tag)
    if release and release.get("prerelease"):
        raise ValueError("Existing release is a prerelease; inspect before retrying.")
    if release and not release["draft"]:
        verify_published(repo, tag, version, release)
        return {"tag": tag, "commit": commit, "url": release["html_url"], "state": "already-published"}
    if release is None:
        command(
            "gh",
            "release",
            "create",
            tag,
            "--repo",
            repo,
            "--draft",
            "--verify-tag",
            "--title",
            tag,
            "--notes",
            f"Tested Python wheel and source archive. Source commit: {commit}.",
        )
    checksum = directory / "SHA256SUMS"
    checksum.write_text(checksums(assets))
    command("gh", "release", "upload", tag, "--repo", repo, "--clobber", *map(str, [*assets, checksum]))
    release = require_release(repo, tag)
    verify_published(repo, tag, version, release)
    latest = "true" if should_mark_latest(repo, version) else "false"
    command("gh", "release", "edit", tag, "--repo", repo, "--draft=false", f"--latest={latest}")
    release = require_release(repo, tag)
    if release["draft"] or tag_commit(repo, tag) != commit:
        raise ValueError("Published release was not observed at the tested commit.")
    return {"tag": tag, "commit": commit, "url": release["html_url"], "state": "published"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    prepare_args = commands.add_parser("prepare")
    prepare_args.add_argument("--commit", required=True)
    prepare_args.add_argument("--checkout", action="store_true")
    publish_args = commands.add_parser("publish")
    publish_args.add_argument("--commit", required=True)
    publish_args.add_argument("--version", required=True)
    publish_args.add_argument("--dist", type=Path, default=Path("dist"))
    args = parser.parse_args()
    if args.action == "prepare":
        result = prepare(Path.cwd(), args.commit, checkout=args.checkout)
        if output := os.environ.get("GITHUB_OUTPUT"):
            with Path(output).open("a") as stream:
                for key, value in result.items():
                    stream.write(f"{key}={value}\n")
    else:
        result = publish(os.environ["GITHUB_REPOSITORY"], args.commit, args.version, args.dist)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
