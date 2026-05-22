"""
parser.py — Part 2: Code Structure Parser
==========================================
Accepts the ingestion output dict from Part 1 and returns a structured
analysis of every source file — functions, classes, imports, chunks, and
complexity ratings.

No external dependencies; uses only the Python standard library.
"""

import ast
import re
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LARGE_FILE_THRESHOLD: int = 100   # lines — files above this get chunked
CHUNK_SIZE: int = 50              # lines per chunk


# ---------------------------------------------------------------------------
# Complexity helpers
# ---------------------------------------------------------------------------

# AST node types that count as a branching point for complexity estimation
_COMPLEXITY_NODES = (
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.If,
    ast.With,
    ast.AsyncWith,
    ast.ExceptHandler,
    ast.comprehension,
)


def _ast_complexity(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """
    Estimate cyclomatic-style complexity of a Python function.

    Walks the function's AST and counts branching/looping nodes.
    Returns 'low', 'medium', or 'high'.

    Parameters
    ----------
    func_node:
        An ast.FunctionDef or ast.AsyncFunctionDef node.

    Returns
    -------
    str
        'low'    — 0–3 branching nodes
        'medium' — 4–7 branching nodes
        'high'   — 8+ branching nodes
    """
    count = sum(
        1
        for node in ast.walk(func_node)
        if isinstance(node, _COMPLEXITY_NODES)
    )
    if count <= 3:
        return "low"
    if count <= 7:
        return "medium"
    return "high"


def _regex_complexity(code: str) -> str:
    """
    Estimate complexity of a JavaScript (or other) function via regex.

    Counts occurrences of common branching/looping keywords.

    Parameters
    ----------
    code:
        Raw source code of the function as a string.

    Returns
    -------
    str
        'low' / 'medium' / 'high'
    """
    keywords = re.findall(
        r"\b(if|else\s+if|for|while|switch|catch|&&|\|\|)\b", code
    )
    count = len(keywords)
    if count <= 3:
        return "low"
    if count <= 7:
        return "medium"
    return "high"


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _make_chunks(content: str) -> list[dict[str, Any]]:
    """
    Split source into 50-line chunks when the file exceeds 100 lines.

    Small files return an empty list — Part 3 should send the full content.

    Parameters
    ----------
    content:
        Full source text of the file.

    Returns
    -------
    list[dict]
        Each dict: { "chunk_id": int, "code": str, "lines": str }
        'lines' is a human-readable range, e.g. "1-50".
        Returns [] if the file is <= LARGE_FILE_THRESHOLD lines.
    """
    lines = content.splitlines()
    if len(lines) <= LARGE_FILE_THRESHOLD:
        return []

    chunks: list[dict[str, Any]] = []
    chunk_id = 0
    for start in range(0, len(lines), CHUNK_SIZE):
        end = min(start + CHUNK_SIZE, len(lines))
        chunks.append({
            "chunk_id": chunk_id,
            "code": "\n".join(lines[start:end]),
            "lines": f"{start + 1}-{end}",
        })
        chunk_id += 1

    return chunks


# ---------------------------------------------------------------------------
# Python parser (ast-based)
# ---------------------------------------------------------------------------

def _source_segment(source_lines: list[str], start: int, end: int) -> str:
    """
    Return the raw source for lines [start, end] (both 1-based, inclusive).

    Parameters
    ----------
    source_lines:
        All lines of the file (as returned by str.splitlines()).
    start:
        First line number (1-based).
    end:
        Last line number (1-based).

    Returns
    -------
    str
        The joined source segment.
    """
    return "\n".join(source_lines[start - 1 : end])


def _parse_python(path: str, content: str) -> dict[str, Any]:
    """
    Parse a Python source file with the built-in ast module.

    Extracts top-level and class-level functions, all class definitions,
    and import statements. Returns a single parsed-file dict.

    Parameters
    ----------
    path:
        Relative file path (used as the 'path' key in output).
    content:
        Full source text of the file.

    Returns
    -------
    dict
        Parsed-file dict conforming to the output schema.
    """
    functions: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []
    imports: list[str] = []
    source_lines = content.splitlines()

    try:
        tree = ast.parse(content, filename=path)
    except SyntaxError as exc:
        # Gracefully degrade: return empty structure with error note
        return {
            "path": path,
            "language": "python",
            "functions": [],
            "classes": [],
            "imports": [],
            "chunks": _make_chunks(content),
            "_parse_error": f"SyntaxError line {exc.lineno}: {exc.msg}",
        }

    # --- Imports ---
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append(f"{module}.{alias.name}" if module else alias.name)

    # --- Top-level functions ---
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end_line = getattr(node, "end_lineno", node.lineno)
            functions.append({
                "name": node.name,
                "line_start": node.lineno,
                "line_end": end_line,
                "code": _source_segment(source_lines, node.lineno, end_line),
                "complexity": _ast_complexity(node),
            })

    # --- Classes with their methods ---
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods: list[str] = []
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    end_line = getattr(child, "end_lineno", child.lineno)
                    methods.append(child.name)
                    # Also surface class methods in the global functions list
                    functions.append({
                        "name": f"{node.name}.{child.name}",
                        "line_start": child.lineno,
                        "line_end": end_line,
                        "code": _source_segment(source_lines, child.lineno, end_line),
                        "complexity": _ast_complexity(child),
                    })
            end_line = getattr(node, "end_lineno", node.lineno)
            classes.append({
                "name": node.name,
                "methods": methods,
                "line_start": node.lineno,
                "line_end": end_line,
            })

    return {
        "path": path,
        "language": "python",
        "functions": functions,
        "classes": classes,
        "imports": sorted(set(imports)),
        "chunks": _make_chunks(content),
    }


# ---------------------------------------------------------------------------
# JavaScript parser (regex-based)
# ---------------------------------------------------------------------------

# Matches: function foo(...) {  |  const foo = (...) => {  |  const foo = function(...) {
_JS_FUNC_RE = re.compile(
    r"""
    (?:                               # named function declaration
        (?:export\s+)?
        (?:async\s+)?
        function\s+(?P<name1>\w+)\s*\([^)]*\)
    )
    |
    (?:                               # arrow / function expression
        (?:const|let|var)\s+(?P<name2>\w+)\s*=\s*
        (?:async\s+)?(?:function\s*)?\([^)]*\)\s*(?:=>\s*)?
    )
    """,
    re.VERBOSE,
)

_JS_CLASS_RE = re.compile(r"\bclass\s+(\w+)")
_JS_METHOD_RE = re.compile(r"^\s{2,}(?:async\s+)?(\w+)\s*\(", re.MULTILINE)
_JS_IMPORT_RE = re.compile(
    r"""
    (?:import\s+.*?from\s+['"](?P<mod1>[^'"]+)['"])   # ES module import
    |
    (?:require\s*\(\s*['"](?P<mod2>[^'"]+)['"]\s*\))  # CommonJS require
    """,
    re.VERBOSE,
)

_JS_SKIP_KEYWORDS = frozenset(
    {"if", "for", "while", "switch", "catch", "function", "return"}
)


def _js_body_bounds(content: str, search_from: int) -> tuple[int, int]:
    """
    Find the character offsets of the matching '{...}' block.

    Scans forward from search_from for the first '{', then walks until the
    matching '}' is found by tracking brace depth.

    Parameters
    ----------
    content:
        Full file source.
    search_from:
        Character offset to start searching for '{'.

    Returns
    -------
    tuple[int, int]
        (open_brace_pos, close_brace_pos) — both inclusive offsets.
        Returns (-1, -1) if no opening brace is found.
    """
    brace_pos = content.find("{", search_from)
    if brace_pos == -1:
        return -1, -1

    depth = 0
    idx = brace_pos
    for ch in content[brace_pos:]:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return brace_pos, idx
        idx += 1
    return brace_pos, idx


def _parse_javascript(path: str, content: str) -> dict[str, Any]:
    """
    Parse a JavaScript source file using regex heuristics.

    Extracts function declarations, arrow functions, class names, and
    import/require statements.

    Parameters
    ----------
    path:
        Relative file path.
    content:
        Full source text.

    Returns
    -------
    dict
        Parsed-file dict conforming to the output schema.
    """
    functions: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []
    imports: list[str] = []

    # --- Imports ---
    for m in _JS_IMPORT_RE.finditer(content):
        mod = m.group("mod1") or m.group("mod2") or ""
        if mod:
            imports.append(mod)

    # --- Functions ---
    for m in _JS_FUNC_RE.finditer(content):
        name = m.group("name1") or m.group("name2") or "<anonymous>"
        before = content[: m.start()]
        line_start = before.count("\n") + 1

        open_b, close_b = _js_body_bounds(content, m.end())
        if open_b == -1:
            code = content[m.start() : m.start() + 120]
            line_end = line_start
        else:
            code = content[m.start() : close_b + 1]
            line_end = line_start + code.count("\n")

        functions.append({
            "name": name,
            "line_start": line_start,
            "line_end": line_end,
            "code": code,
            "complexity": _regex_complexity(code),
        })

    # --- Classes ---
    for m in _JS_CLASS_RE.finditer(content):
        class_name = m.group(1)
        open_b, close_b = _js_body_bounds(content, m.end())
        before = content[: m.start()]
        line_start = before.count("\n") + 1

        if open_b == -1:
            classes.append({
                "name": class_name,
                "methods": [],
                "line_start": line_start,
                "line_end": line_start,
            })
            continue

        body = content[open_b : close_b + 1]
        methods = [
            mm.group(1)
            for mm in _JS_METHOD_RE.finditer(body)
            if mm.group(1) not in _JS_SKIP_KEYWORDS
        ]
        line_end = line_start + body.count("\n")
        classes.append({
            "name": class_name,
            "methods": methods,
            "line_start": line_start,
            "line_end": line_end,
        })

    return {
        "path": path,
        "language": "javascript",
        "functions": functions,
        "classes": classes,
        "imports": sorted(set(imports)),
        "chunks": _make_chunks(content),
    }


# ---------------------------------------------------------------------------
# Generic fallback parser
# ---------------------------------------------------------------------------

def _parse_generic(path: str, content: str, language: str) -> dict[str, Any]:
    """
    Fallback parser for unsupported file types.

    No AST or regex extraction — chunks the raw source so Part 3 can still
    send the content to the LLM for a best-effort review.

    Parameters
    ----------
    path:
        Relative file path.
    content:
        Full source text.
    language:
        Language identifier string from the ingestion output.

    Returns
    -------
    dict
        Parsed-file dict with empty extraction fields and raw chunks.
    """
    return {
        "path": path,
        "language": language,
        "functions": [],
        "classes": [],
        "imports": [],
        "chunks": _make_chunks(content),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_files(ingestion_output: dict[str, Any]) -> dict[str, Any]:
    """
    Parse all source files from the ingestion output.

    Dispatches each file to the appropriate parser based on language/extension,
    then assembles the final result dict.

    Parameters
    ----------
    ingestion_output : dict
        Exactly the structure produced by Part 1 (the ingester)::

            {
                "repo_name":   str,
                "files": [
                    {
                        "path":     str,
                        "content":  str,
                        "language": str,
                        "size_kb":  float
                    },
                    ...
                ],
                "total_files": int,
                "clone_path":  str
            }

    Returns
    -------
    dict
        Parsed repository structure::

            {
                "parsed_files": [
                    {
                        "path":      str,
                        "language":  str,
                        "functions": [
                            {
                                "name":       str,
                                "line_start": int,
                                "line_end":   int,
                                "code":       str,
                                "complexity": str   # 'low' | 'medium' | 'high'
                            }
                        ],
                        "classes": [
                            {
                                "name":       str,
                                "methods":    list[str],
                                "line_start": int,
                                "line_end":   int
                            }
                        ],
                        "imports": [str],
                        "chunks": [
                            {
                                "chunk_id": int,
                                "code":     str,
                                "lines":    str     # e.g. "1-50"
                            }
                        ]
                    }
                ],
                "total_functions": int,
                "total_classes":   int
            }

    Raises
    ------
    TypeError
        If ingestion_output is not a dict or 'files' is not a list.
    KeyError
        If required top-level keys are missing from ingestion_output.
    """
    # --- Input validation ---
    if not isinstance(ingestion_output, dict):
        raise TypeError(
            f"ingestion_output must be a dict, got {type(ingestion_output).__name__}"
        )
    required_keys = {"repo_name", "files", "total_files", "clone_path"}
    missing = required_keys - ingestion_output.keys()
    if missing:
        raise KeyError(f"ingestion_output is missing required keys: {missing}")

    files: list[dict[str, Any]] = ingestion_output["files"]
    if not isinstance(files, list):
        raise TypeError(f"'files' must be a list, got {type(files).__name__}")

    parsed_files: list[dict[str, Any]] = []

    for file_entry in files:
        path: str = file_entry.get("path", "")
        content: str = file_entry.get("content", "")
        language: str = (file_entry.get("language") or "").lower().strip()

        # Normalise language from file extension if field is blank
        if not language:
            if path.endswith(".py"):
                language = "python"
            elif path.endswith((".js", ".mjs", ".cjs")):
                language = "javascript"
            else:
                language = "unknown"

        if language == "python":
            parsed = _parse_python(path, content)
        elif language == "javascript":
            parsed = _parse_javascript(path, content)
        else:
            parsed = _parse_generic(path, content, language)

        parsed_files.append(parsed)

    total_functions = sum(len(pf["functions"]) for pf in parsed_files)
    total_classes = sum(len(pf["classes"]) for pf in parsed_files)

    return {
        "parsed_files": parsed_files,
        "total_functions": total_functions,
        "total_classes": total_classes,
    }


# ---------------------------------------------------------------------------
# Smoke test — run:  python parser.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _SAMPLE_PY = '''\
import os
from typing import List, Optional

CONSTANT = 42


class Greeter:
    """A simple greeter."""

    def __init__(self, name: str) -> None:
        self.name = name

    def greet(self) -> str:
        """Return greeting string."""
        if self.name:
            for _ in range(3):
                if True:
                    pass
        return f"Hello, {self.name}"


def standalone(x: int) -> int:
    """Top-level function with nested loops (high complexity)."""
    result = 0
    for i in range(x):
        if i % 2 == 0:
            for j in range(i):
                if j > 1:
                    while j > 0:
                        result += j
                        j -= 1
    return result
'''

    _SAMPLE_JS = r"""\
import { readFile } from 'fs/promises';
const db = require('database');

class UserService {
  async getUser(id) {
    if (!id) return null;
    for (const item of list) {
      if (item.active) { continue; }
    }
    return db.find(id);
  }

  deleteUser(id) {
    return db.delete(id);
  }
}

const formatName = (first, last) => {
  if (!first || !last) return '';
  return `${first} ${last}`;
};

function validateEmail(email) {
  if (!email) return false;
  return /^[^\s@]+@[^\s@]+$/.test(email);
}
"""

    import json

    sample_input: dict[str, Any] = {
        "repo_name": "demo-repo",
        "clone_path": "/tmp/demo-repo",
        "total_files": 2,
        "files": [
            {
                "path": "app/greeter.py",
                "content": _SAMPLE_PY,
                "language": "python",
                "size_kb": 0.4,
            },
            {
                "path": "src/userService.js",
                "content": _SAMPLE_JS,
                "language": "javascript",
                "size_kb": 0.3,
            },
        ],
    }

    result = parse_files(sample_input)
    print(json.dumps(result, indent=2))
