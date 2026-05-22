"""
ingestion.py
------------
Part of a code review tool.

Public API
----------
    clone_and_read(github_url: str) -> dict

Clones a GitHub repository, filters .py / .js files (skipping node_modules,
.git, __pycache__), reads their contents, and returns a structured dict.

No dependency on any other part of the project.
"""

import os
import re
import shutil
from pathlib import Path
from typing import Optional

import git  # GitPython


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
}

SKIP_DIRS: set[str] = {
    "node_modules",
    ".git",
    "__pycache__",
}

import tempfile
CLONE_BASE: str = tempfile.gettempdir()

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clone_and_read(github_url: str) -> dict:
    """
    Clone a GitHub repository and read all .py / .js source files.

    Parameters
    ----------
    github_url : str
        Public GitHub HTTPS URL, e.g. "https://github.com/owner/repo".
        A trailing ".git" is accepted but not required.

    Returns
    -------
    dict
        {
            "repo_name"   : str,          # derived from the URL
            "files"       : [             # one entry per readable file
                {
                    "path"    : str,      # path relative to repo root
                    "content" : str,      # full UTF-8 file content
                    "language": str,      # "Python" | "JavaScript"
                    "size_kb" : float,    # file size rounded to 2 dp
                }
            ],
            "total_files" : int,          # len(files)
            "clone_path"  : str,          # absolute path used for the clone
            "error"       : None | str    # None on success; message on failure
        }
    """
    repo_name  = _extract_repo_name(github_url)
    clone_path = os.path.join(CLONE_BASE, repo_name)

    # Base response skeleton
    result: dict = {
        "repo_name"  : repo_name,
        "files"      : [],
        "total_files": 0,
        "clone_path" : clone_path,
        "error"      : None,
    }

    # 1. Validate URL format
    validation_error = _validate_url(github_url)
    if validation_error:
        result["error"] = validation_error
        return result

    # 2. Clone
    clone_error = _clone_repo(github_url, clone_path)
    if clone_error:
        result["error"] = clone_error
        return result

    # 3. Walk, filter, read
    try:
        files = _collect_files(clone_path)
        result["files"]       = files
        result["total_files"] = len(files)
    except Exception as exc:
        result["error"] = f"Failed to read repository files: {exc}"

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_url(url: str) -> Optional[str]:
    """
    Return an error message if *url* is not a plausible GitHub HTTPS URL,
    or None if it looks valid.
    """
    if not url or not isinstance(url, str):
        return "github_url must be a non-empty string."

    url = url.strip()
    pattern = r"^https?://github\.com/[\w.\-]+/[\w.\-]+(\.git)?(/.*)?$"
    if not re.match(pattern, url, re.IGNORECASE):
        return (
            f"Invalid GitHub URL: {url!r}. "
            "Expected format: https://github.com/owner/repo"
        )
    return None


def _extract_repo_name(url: str) -> str:
    """
    Derive a filesystem-safe repo name from the URL.

    Examples
    --------
    "https://github.com/pallets/click.git"  ->  "click"
    "https://github.com/owner/my-repo"      ->  "my-repo"
    """
    name = url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name or "repo"


def _clone_repo(url: str, dest: str) -> Optional[str]:
    if os.path.exists(dest):
        import stat
        for dirpath, dirnames, filenames in os.walk(dest, topdown=False):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                os.chmod(filepath, stat.S_IWRITE)
                try:
                    os.unlink(filepath)
                except Exception:
                    pass
            for dirname in dirnames:
                dirfullpath = os.path.join(dirpath, dirname)
                os.chmod(dirfullpath, stat.S_IWRITE)
                try:
                    os.rmdir(dirfullpath)
                except Exception:
                    pass
        try:
            os.rmdir(dest)
        except Exception:
            pass

    try:
        git.Repo.clone_from(url, dest, depth=1)
        return None
    except git.exc.GitCommandError as exc:
        msg = str(exc)
        if "Repository not found" in msg or "does not exist" in msg:
            return f"Repository not found or is private: {url}"
        if "Authentication failed" in msg:
            return f"Authentication failed — repository may be private: {url}"
        return f"Git clone failed: {msg}"
    except Exception as exc:
        return f"Unexpected error during clone: {exc}"
def _should_skip_dir(dirname: str) -> bool:
    """Return True if this directory should be excluded from the file walk."""
    return dirname in SKIP_DIRS or dirname.startswith(".")


def _collect_files(root: str) -> list[dict]:
    """
    Recursively walk *root*, collect .py / .js files, read them, and
    return a list of file-info dicts (see clone_and_read docstring).
    """
    collected: list[dict] = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune banned directories in-place to stop os.walk descending into them
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

        for filename in sorted(filenames):
            ext      = Path(filename).suffix.lower()
            language = ALLOWED_EXTENSIONS.get(ext)
            if language is None:
                continue

            abs_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(abs_path, root)

            content, size_kb = _read_file(abs_path)
            if content is None:
                continue  # skip unreadable / binary files

            collected.append(
                {
                    "path"    : rel_path,
                    "content" : content,
                    "language": language,
                    "size_kb" : size_kb,
                }
            )

    return collected


def _read_file(abs_path: str) -> tuple[Optional[str], float]:
    """
    Read *abs_path* as UTF-8 text.

    Returns
    -------
    (content, size_kb)  on success
    (None, 0.0)         if the file cannot be read or decoded
    """
    try:
        size_bytes = os.path.getsize(abs_path)
        size_kb    = round(size_bytes / 1024, 2)
        with open(abs_path, "r", encoding="utf-8", errors="strict") as fh:
            content = fh.read()
        return content, size_kb
    except (UnicodeDecodeError, OSError):
        return None, 0.0


# ---------------------------------------------------------------------------
# Smoke-test  (python ingestion.py [url])
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    url = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/pallets/click"
    print(f"Cloning: {url}\n")

    output = clone_and_read(url)

    if output["error"]:
        print(f"ERROR: {output['error']}")
        sys.exit(1)

    print(f"Repo      : {output['repo_name']}")
    print(f"Clone path: {output['clone_path']}")
    print(f"Files read: {output['total_files']}\n")

    for f in output["files"][:5]:
        preview = f["content"][:80].replace("\n", "\\n")
        print(f"  [{f['language']:10s}] {f['path']:45s} {f['size_kb']:6.2f} KB")
        print(f"             {preview!r}...\n")
