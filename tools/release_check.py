#!/usr/bin/env python3
"""Check the public release tree without printing matched private values.

Default scope is an explicit allowlist. Use --tracked before committing/pushing;
use --staged to inspect exact staged blobs and --strict-tree for an isolated release directory. This is a publication gate,
not a substitute for reviewing whether free-form names are synthetic.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET

ROOT_FILES = {"README.md", ".gitignore", "LICENSE", "LICENSE.md", "CHANGELOG.md"}
ROOT_DIRS = {"gamemaster-skill", "ptty-skill", "tools", "tests"}
TEXT_SUFFIXES = {".md", ".txt", ".json", ".py", ".mjs", ".cjs", ".js", ".yaml", ".yml", ".toml", ".xml", ".rels", ".csv", ".html", ".sh"}
ARCHIVE_SUFFIXES = {".xlsx", ".docx", ".zip", ".skill"}
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 2000
PRIVATE_PARTS = re.compile(r"(?i)(?:^|[-_.])(?:credentials?|cookies?|sessions?|browser[-_]?profile|storage[-_]?state|secrets?)(?:$|[-_.])")
PRIVATE_DIRS = {"docs", "private", ".git", ".codex", ".agents", ".aws", ".ssh", "node_modules", "__pycache__", ".venv"}
CREDENTIAL = re.compile(r'''(?ix)(?:["']?(?:password|passwd|pwd|user(?:name)?|account|access[_-]?token|refresh[_-]?token|api[_-]?key|authorization|cookie|uisStr|pageSocket)["']?)\s*[:=]\s*(["'])([^\r\n]*?)\1''')
PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "provider_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{35,}|AKIA[A-Z0-9]{16})\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "url_credentials": re.compile(r"https?://[^\s/@:]+:[^\s/@]+@", re.I),
    "signed_url": re.compile(r"[?&](?:access_token|refresh_token|uisStr|token|password|authorization)=[^\s&\"'<>]{4,}", re.I),
    "concrete_event_url": re.compile(r"[?&]ssid=[A-Fa-f0-9]{24,}\b"),
    "platform_record_id": re.compile(r"\b(?:SS|XM|RY|DW)\d{6}[A-Z]{2}\d{6}\b"),
    "personal_absolute_path": re.compile(r"(?:/home/(?!USER\b|user\b)[\w.-]+/|/Users/(?!USER\b|user\b)[A-Za-z0-9_.-]+/|/mnt/[a-z]/|[A-Za-z]:\\(?:Users|A[^\\]*杂项)\\)"),
    "cn_identity_number": re.compile(r"(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)"),
    "cn_mobile_number": re.compile(r"(?<![A-Za-z0-9_.])(?:\+?86[- ]?)?1[3-9]\d{9}(?![A-Za-z0-9_.])"),
}
SAFE_AUTHORS = {"", "gamemaster", "gamemaster-skill", "ptty-skill", "openpyxl", "microsoft office user", "synthetic"}


def placeholder(value: str) -> bool:
    value = value.strip()
    return not value or value.startswith(("<", "$", "{", "process.env.", "os.environ")) or value.lower() in {"redacted", "placeholder", "example", "example_user", "demo", "demo_user", "your_password", "your_token", "your_username", "test", "synthetic"}


def allowed_path(name: str) -> bool:
    p = PurePosixPath(name)
    return name in ROOT_FILES or (len(p.parts) > 1 and p.parts[0] in ROOT_DIRS)


def private_path(name: str) -> bool:
    return any(p in PRIVATE_DIRS or p.startswith(".env") or PRIVATE_PARTS.search(p) or p.endswith((".pem", ".key", ".p12", ".pfx", ".har", ".log", ".pyc")) for p in PurePosixPath(name).parts)


def finding(path: str, rule: str, line: int | None = None) -> dict:
    item = {"path": path, "rule": rule}
    if line is not None:
        item["line"] = line
    return item


def scan_text(text: str, path: str, denylist: tuple[str, ...] = ()) -> list[dict]:
    issues = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for rule, pattern in PATTERNS.items():
            if pattern.search(line):
                issues.append(finding(path, rule, line_no))
        if any(not placeholder(m.group(2)) for m in CREDENTIAL.finditer(line)):
            issues.append(finding(path, "literal_credential_or_session", line_no))
        if any(term in line for term in denylist):
            issues.append(finding(path, "private_denylist_match", line_no))
    return issues


def scan_archive(data: bytes, path: str, denylist: tuple[str, ...], depth: int = 0) -> list[dict]:
    issues = []
    if depth > 2:
        return [finding(path, "archive_nesting_limit")]
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_MEMBERS or sum(i.file_size for i in entries) > MAX_ARCHIVE_BYTES:
                return [finding(path, "archive_size_limit")]
            for entry in entries:
                inner = PurePosixPath(entry.filename)
                member = path + "!" + entry.filename
                if inner.is_absolute() or ".." in inner.parts or "\\" in entry.filename:
                    issues.append(finding(member, "unsafe_archive_path"))
                    continue
                if entry.is_dir():
                    continue
                if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    issues.append(finding(member, "symlink_not_publishable"))
                    continue
                if entry.flag_bits & 1 or entry.file_size > MAX_MEMBER_BYTES:
                    issues.append(finding(member, "uninspectable_archive_member"))
                    continue
                if private_path(entry.filename):
                    issues.append(finding(member, "private_archive_path"))
                blob = archive.read(entry)
                if entry.filename == "docProps/custom.xml":
                    issues.append(finding(member, "unreviewed_custom_document_metadata"))
                if entry.filename == "docProps/core.xml":
                    try:
                        for elem in ET.fromstring(blob).iter():
                            if elem.tag.rsplit("}", 1)[-1] in {"creator", "lastModifiedBy"} and (elem.text or "").strip().lower() not in SAFE_AUTHORS:
                                issues.append(finding(member, "personal_document_author"))
                    except ET.ParseError:
                        issues.append(finding(member, "invalid_document_metadata"))
                if inner.suffix.lower() in ARCHIVE_SUFFIXES:
                    issues.extend(scan_archive(blob, member, denylist, depth + 1))
                elif inner.suffix.lower() in TEXT_SUFFIXES or inner.name in {"[Content_Types].xml", ".rels"}:
                    try:
                        issues.extend(scan_text(blob.decode("utf-8-sig"), member, denylist))
                    except UnicodeDecodeError:
                        issues.append(finding(member, "uninspectable_text_encoding"))
                else:
                    # Blank spreadsheet templates need no embedded media or executable parts.
                    issues.append(finding(member, "unreviewed_binary_member"))
    except (zipfile.BadZipFile, RuntimeError, OSError):
        issues.append(finding(path, "uninspectable_archive"))
    return issues


def scan_blob(data: bytes, relative: str, denylist: tuple[str, ...] = ()) -> list[dict]:
    issues = [finding(relative, "private_path")] if private_path(relative) else []
    path = PurePosixPath(relative)
    if len(data) > MAX_ARCHIVE_BYTES:
        return issues + [finding(relative, "file_size_limit")]
    if path.suffix.lower() in ARCHIVE_SUFFIXES:
        return issues + scan_archive(data, relative, denylist)
    if path.suffix.lower() in TEXT_SUFFIXES or path.name in ROOT_FILES or path.name == ".gitignore":
        try:
            return issues + scan_text(data.decode("utf-8-sig"), relative, denylist)
        except UnicodeDecodeError:
            return issues + [finding(relative, "uninspectable_text_encoding")]
    return issues + [finding(relative, "unreviewed_binary_or_extension")]


def scan_file(file: Path, relative: str, denylist: tuple[str, ...] = ()) -> list[dict]:
    if file.is_symlink():
        return [finding(relative, "symlink_not_publishable")]
    if not file.is_file():
        return [finding(relative, "missing_or_nonregular_file")]
    return scan_blob(file.read_bytes(), relative, denylist)


def public_files(root: Path) -> list[str]:
    files = [p.name for p in root.iterdir() if p.name in ROOT_FILES and (p.is_file() or p.is_symlink())]
    for directory in sorted(ROOT_DIRS):
        base = root / directory
        if base.is_symlink():
            files.append(directory)
        elif base.is_dir():
            files.extend(str(p.relative_to(root)) for p in base.rglob("*") if p.is_file() or p.is_symlink())
    return sorted(set(files))


def git_tracked(root: Path) -> list[str]:
    command = ["git", "-c", f"safe.directory={root}", "-C", str(root)]
    check = subprocess.run(command + ["rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if check.returncode or Path(check.stdout.strip()).resolve() != root:
        raise ValueError("requested root is not the root of its own Git repository")
    result = subprocess.run(command + ["ls-files", "-z"], capture_output=True)
    if result.returncode:
        raise ValueError("unable to read tracked file list")
    return sorted(set(result.stdout.decode("utf-8").rstrip("\0").split("\0"))) if result.stdout else []


def scan_tree(root: Path, *, tracked: bool = False, staged: bool = False, strict: bool = False, denylist: tuple[str, ...] = ()) -> dict:
    root = root.resolve()
    files = git_tracked(root) if tracked or staged else public_files(root)
    git_command = ["git", "-c", f"safe.directory={root}", "-C", str(root)]
    modes = {}
    if staged:
        entries = subprocess.run(git_command + ["ls-files", "--stage", "-z"], capture_output=True, check=True).stdout.decode("utf-8")
        for entry in entries.rstrip("\0").split("\0") if entries else []:
            meta, name = entry.split("\t", 1)
            mode, _, stage = meta.split()
            modes[name] = mode if stage == "0" else "unmerged"
    issues = []
    if strict:
        for child in root.iterdir():
            if child.name != ".git" and child.name not in ROOT_FILES | ROOT_DIRS:
                issues.append(finding(child.name, "outside_public_allowlist"))
    for name in files:
        if not allowed_path(name):
            issues.append(finding(name, "outside_public_allowlist"))
        if staged:
            if modes.get(name) not in {"100644", "100755"}:
                issues.append(finding(name, "nonregular_or_unmerged_git_entry"))
                continue
            blob = subprocess.run(git_command + ["show", ":" + name], capture_output=True)
            if blob.returncode:
                issues.append(finding(name, "unreadable_staged_blob"))
            else:
                issues.extend(scan_blob(blob.stdout, name, denylist))
            continue
        p = root / name
        if any(q.is_symlink() for q in (p, *p.parents) if q != root and root in q.parents):
            issues.append(finding(name, "symlink_not_publishable"))
            continue
        issues.extend(scan_file(p, name, denylist))
    return {"passed": not issues, "scope": "staged_blobs" if staged else "tracked_worktree" if tracked else "allowlisted_worktree", "strict_tree": strict, "files_checked": len(files), "findings": issues, "limitation": "Free-form personal names and disguised secrets still require human review; no matched values are included in this report."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--tracked", action="store_true", help="Check every tracked working-tree path, including ignored-but-tracked paths")
    source.add_argument("--staged", action="store_true", help="Inspect exact Git index blobs; use immediately before commit")
    parser.add_argument("--strict-tree", action="store_true", help="Reject extra top-level paths in an isolated release tree")
    parser.add_argument("--denylist", type=Path, help="Local UTF-8 file with private literal values, one per line; never commit this file")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    denylist = tuple(x.strip() for x in args.denylist.read_text(encoding="utf-8").splitlines() if x.strip()) if args.denylist else ()
    try:
        report = scan_tree(args.root, tracked=args.tracked, staged=args.staged, strict=args.strict_tree, denylist=denylist)
    except (OSError, ValueError) as exc:
        report = {"passed": False, "error": type(exc).__name__, "message": "release tree could not be inspected; check repository root and file access"}
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
