# tests/test_file_headers.py
"""
Unit test verifying that every Python source file in the repository
starts with the required relative path comment on Line 1.
"""

import os
from tools.check_file_headers import get_all_py_files, check_and_fix_file


def test_all_python_files_have_correct_path_headers():
    """Ensures 100% of .py files have valid '# <path>' headers on line 1."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    py_files = get_all_py_files(root_dir)
    assert len(py_files) > 0

    invalid_files = []
    for f in py_files:
        valid, msg = check_and_fix_file(f, root_dir, fix=False)
        if not valid:
            invalid_files.append(msg)

    assert len(invalid_files) == 0, f"Found files with missing or incorrect headers:\n" + "\n".join(invalid_files)
