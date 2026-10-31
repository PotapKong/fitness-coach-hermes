#!/usr/bin/env python3
"""Opt-in, fail-closed updater for the public fitness-coach-hermes package.

Run once with --apply to install; copy THIS script to ~/.hermes/scripts/ and
use --no-agent cron only after inspecting the fixed upstream and local route.
This trusts the named public repository; it is not a malware sandbox.
"""
import argparse
import ast
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlparse

REPO = "https://github.com/PotapKong/fitness-coach-hermes.git"
BRANCH = "main"
FILES = ("SKILL.md", "README.md", "EVIDENCE.md", "VISUAL.md", "AUTOMATION.md",
         "AUDIT.md", "UPDATES.md", "LICENSE", "coach.py", "food_lookup.py", "ideas.py",
         "recipe_sources.py", "automation_core.py", "history_db.py", "recipes.json", "update_skill.py")
MARKER = ".upstream-sha"
PYTHON = tuple(name for name in FILES if name.endswith(".py"))
GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1"}


def git(*args, cwd=None):
    proc = subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, capture_output=True,
                          text=True, check=True, timeout=75)
    return proc.stdout.strip()


def remote_sha():
    line = git("ls-remote", "--exit-code", REPO, "refs/heads/" + BRANCH)
    sha, ref = line.split("\t")
    if ref != "refs/heads/" + BRANCH or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Unexpected upstream ref")
    return sha


def validate(source):
    unknown_code = {path.name for path in source.glob('*.py')} - set(FILES)
    if unknown_code:
        raise ValueError('New Python files need an explicitly reviewed updater allowlist: ' + ', '.join(sorted(unknown_code)))
    for name in FILES:
        file = source / name
        if not file.is_file() or file.is_symlink():
            raise ValueError(f"Missing or symlinked package file: {name}")
    if not (source / "SKILL.md").read_text(encoding="utf-8").startswith("---\nname: fitness-coach-hermes\n"):
        raise ValueError("Invalid skill name/frontmatter")
    for name in PYTHON:
        ast.parse((source / name).read_text(encoding="utf-8"), filename=name)
    catalog = json.loads((source / "recipes.json").read_text(encoding="utf-8"))
    if catalog.get("version") != 1 or not isinstance(catalog.get("recipes"), list):
        raise ValueError("Invalid catalog envelope")
    seen_ids, seen_urls = set(), set()
    for recipe in catalog["recipes"]:
        recipe_id, url = recipe["id"], recipe["url"].rstrip("/")
        if recipe_id in seen_ids or url in seen_urls:
            raise ValueError("Duplicate recipe id or URL")
        host = urlparse(url).hostname
        if urlparse(url).scheme != "https" or not host or host.removeprefix("www.") != recipe["source"]:
            raise ValueError("Invalid recipe URL")
        if not isinstance(recipe["meal"], list) or not set(recipe["meal"]) <= {"breakfast", "lunch", "dinner", "snack"}:
            raise ValueError("Invalid recipe meal tags")
        seen_ids.add(recipe_id)
        seen_urls.add(url)
    return len(seen_ids)


def install(source, target, sha):
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    release_root = target.parent.parent / "skill-releases" / "fitness-coach-hermes"
    release_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup = None
    if target.is_symlink():
        link = os.readlink(target)
        backup = (target.parent / link).resolve()
        if (not link.startswith("../skill-releases/fitness-coach-hermes/.fitness-coach-release-")
                or backup.parent != release_root.resolve()):
            raise ValueError("Existing target points outside managed releases")
        if not backup.is_dir():
            raise ValueError("Existing managed release is missing")
    elif target.exists():
        raise ValueError("Existing installation is not a managed link; back up and migrate manually")
    if backup is not None:
        managed = backup
        if not managed.is_dir():
            raise ValueError("Existing target is not a managed directory")
        marker = managed / MARKER
        if not marker.is_file():
            raise ValueError("Unmanaged existing installation; back up and migrate manually")
        unexpected = {item.name for item in managed.iterdir()} - (set(FILES) | {MARKER, "examples", "__pycache__"})
        if unexpected:
            raise ValueError("Installation contains extra files; refusing to overwrite: " + ", ".join(sorted(unexpected)))
    stage = Path(tempfile.mkdtemp(prefix=".fitness-coach-stage-", dir=release_root))
    release = None
    pointer = None
    try:
        for name in FILES:
            shutil.copyfile(source / name, stage / name)
            (stage / name).chmod(0o600)
        if (source / "examples").is_dir():
            if any(path.is_symlink() for path in (source / "examples").rglob("*")):
                raise ValueError("Symlink in examples; refusing to copy")
            shutil.copytree(source / "examples", stage / "examples", symlinks=False)
        (stage / MARKER).write_text(sha + "\n", encoding="ascii")
        (stage / MARKER).chmod(0o600)
        validate(stage)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        release = release_root / f".fitness-coach-release-{stamp}-{sha[:12]}-{os.getpid()}"
        stage.rename(release)
        pointer = target.parent / f".fitness-coach-pointer-{os.getpid()}"
        pointer.symlink_to(os.path.relpath(release, target.parent), target_is_directory=True)
        try:
            os.replace(pointer, target)  # atomic pointer swap: old skill remains active until this succeeds
        except BaseException:
            shutil.rmtree(release)
            release = None
            raise
    finally:
        if pointer is not None and pointer.is_symlink():
            pointer.unlink()
        if stage.exists():
            shutil.rmtree(stage)
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="Compare upstream SHA with installed SHA")
    group.add_argument("--apply", action="store_true", help="Install/update trusted public repository")
    parser.add_argument("--target", type=Path, default=Path.home() / ".hermes/skills/fitness-coach-hermes")
    args = parser.parse_args()
    if not args.check:
        args.apply = True  # no-argument Hermes --script cron runs the updater
    target = args.target.expanduser().absolute()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = target.parent / ".fitness-coach-update.lock"
    with lock_path.open("a+") as lock:
        lock_path.chmod(0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another fitness-coach update is running") from None
        update(args, target)


def update(args, target):
    sha = remote_sha()
    marker = target / MARKER
    current = marker.read_text(encoding="ascii").strip() if marker.is_file() else None
    if current == sha:
        try:
            validate(target)
        except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError):
            if args.check:
                print('installed package incomplete for current updater; repair needed', sha)
                return
            # A previous fixed-allowlist updater may have marked an incomplete release current.
        else:
            if args.check:
                print("up-to-date", sha)
            return
    if args.check:
        print("upstream update available", current or "not-installed", "->", sha)
        return
    work_root = target.parent.parent / "skill-releases" / "fitness-coach-hermes"
    work_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fitness-coach-upstream-", dir=work_root) as tmp:
        git("clone", "--depth", "1", "--branch", BRANCH, "--single-branch", REPO, tmp + "/repo")
        source = Path(tmp) / "repo"
        if git("rev-parse", "HEAD", cwd=source) != sha:
            raise RuntimeError("Remote moved during update; retry later")
        count = validate(source)
        backup = install(source, target, sha)
    print(f"Installed fitness-coach-hermes {sha} ({count} recipe links). Previous package: {backup or 'none'}. Reload skills in active agent session.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(f"fitness-coach update failed: {exc}", file=sys.stderr)
        sys.exit(1)
