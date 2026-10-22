# tools/check_file_headers.py
"""
Script to validate and automatically fix first-line file path headers for all Python files.
Format required on Line 1:
# <relative_path_with_forward_slashes>
Example:
# core/app.py
"""

import argparse
import os
import sys
from typing import List, Tuple

EXCLUDE_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache",
    ".idea", ".vscode", "build", "dist", ".agents", ".gemini"
}


def get_all_py_files(root_dir: str) -> List[str]:
    """Recursively collects all Python files in the workspace excluding virtual environments and test caches."""
    py_files = []
    for root, dirs, files in os.walk(root_dir):
        # Prune excluded directories
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        
        # Also check that current root is not inside an excluded directory
        rel_root = os.path.relpath(root, root_dir).replace("\\", "/")
        parts = rel_root.split("/")
        if any(p.startswith(".") or p in EXCLUDE_DIRS for p in parts if p != "."):
            continue

        for file in files:
            if file.endswith(".py"):
                full_path = os.path.join(root, file)
                py_files.append(full_path)
    return py_files


def check_and_fix_file(filepath: str, root_dir: str, fix: bool = False) -> Tuple[bool, str]:
    """
    Checks if the first line is the correct relative path comment.
    If fix is True, automatically updates the file.
    """
    rel_path = os.path.relpath(filepath, root_dir).replace("\\", "/")
    expected_header = f"# {rel_path}"

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        with open(filepath, "r", encoding="latin-1") as f:
            content = f.read()

    lines = content.splitlines(keepends=True)
    if not lines:
        # Empty file
        if fix:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"{expected_header}\n")
            return True, f"Added header to empty file: {rel_path}"
        return False, f"Empty file missing header: {rel_path}"

    first_line = lines[0].strip()

    # Check if first line matches expected header exactly
    if first_line == expected_header:
        return True, f"OK: {rel_path}"

    # If first line has a comment with a file path variant or typo
    if fix:
        # Check if line 1 was a comment that looks like a path header (e.g. #plugins/screen/commands.py or # /path)
        # or if an existing header is present on line 1 or 2
        new_lines = list(lines)
        if first_line.startswith("#") and (first_line.endswith(".py") or "plugins/" in first_line or "core/" in first_line):
            # Replace line 1
            new_lines[0] = f"{expected_header}\n"
        else:
            # Check if line 2 had the header (e.g. docstring was on line 1)
            # Remove any stray header comments inside the first 5 lines
            cleaned_lines = []
            for i, line in enumerate(new_lines):
                s = line.strip()
                if i < 5 and s.startswith("#") and s.endswith(".py"):
                    continue # Skip old/misplaced header
                cleaned_lines.append(line)
            new_lines = [f"{expected_header}\n"] + cleaned_lines

        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        return True, f"Fixed header: {rel_path}"

    return False, f"Invalid/Missing header in {rel_path} (Got: '{first_line}', Expected: '{expected_header}')"


def main():
    parser = argparse.ArgumentParser(description="Validate and fix Python file path headers.")
    parser.add_argument("--fix", action="store_true", help="Automatically insert or fix file path headers")
    parser.add_argument("--root", default=".", help="Root directory of the project")
    args = parser.parse_args()

    root_dir = os.path.abspath(args.root)
    py_files = get_all_py_files(root_dir)

    all_valid = True
    for py_file in py_files:
        valid, msg = check_and_fix_file(py_file, root_dir, fix=args.fix)
        if not valid or args.fix:
            print(msg)
        if not valid and not args.fix:
            all_valid = False

    if not all_valid and not args.fix:
        print(f"\n[ERROR] One or more Python files have invalid or missing file path headers.")
        print(f"Run 'python tools/check_file_headers.py --fix' to automatically fix them.")
        sys.exit(1)
    else:
        print(f"\n[SUCCESS] All {len(py_files)} Python files verified with correct file path headers.")
        sys.exit(0)


if __name__ == "__main__":
    main()
