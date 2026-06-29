from __future__ import annotations

from relocation_jobs.mcp.validate import validate_tex_content

MASTER = r"""
\documentclass{article}
\begin{document}
\company{Example Corp} \hfill 2020 -- 2024\\
\position{Backend Engineer}
\end{document}
"""


def test_validate_accepts_matching_tailored_tex():
    tailored = MASTER.replace("Backend Engineer", "Senior Backend Engineer")
    result = validate_tex_content(tailored, MASTER)
    assert result.ok is True
    assert result.issues == []


def test_validate_rejects_new_year():
    tailored = MASTER.replace("2024", "2025")
    result = validate_tex_content(tailored, MASTER)
    assert result.ok is False
    codes = {issue.code for issue in result.issues}
    assert "new_years" in codes


def test_validate_rejects_new_employer():
    tailored = MASTER + "\n\\company{Fake Corp}"
    result = validate_tex_content(tailored, MASTER)
    assert result.ok is False
    codes = {issue.code for issue in result.issues}
    assert "new_employers" in codes


def test_validate_rejects_unbalanced_environments():
    tailored = MASTER.replace("\\end{document}", "")
    result = validate_tex_content(tailored, MASTER)
    assert result.ok is False
    codes = {issue.code for issue in result.issues}
    assert "missing_document_end" in codes or "unbalanced_environments" in codes
