from __future__ import annotations

import re
from datetime import date

from relocation_jobs.mcp.types import ValidationIssue, ValidationResult

_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_EMPLOYER_LINE_RE = re.compile(r"\\company\{([^}]+)\}")
_OPEN_ENDED_RE = re.compile(r"\b(?:Present|Current|Now)\b", re.IGNORECASE)
_MAX_LINES = 400


def _extract_years(text: str) -> set[str]:
    return set(_YEAR_RE.findall(text))


def _extract_employer_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for match in _EMPLOYER_LINE_RE.finditer(text):
        cleaned = match.group(1).strip()
        if len(cleaned) >= 3:
            tokens.add(cleaned.lower())
    return tokens


def _structure_issues(tex: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if "\\begin{document}" not in tex:
        issues.append(ValidationIssue(
            code="missing_document_begin",
            message="Missing \\begin{document}",
        ))
    if "\\end{document}" not in tex:
        issues.append(ValidationIssue(
            code="missing_document_end",
            message="Missing \\end{document}",
        ))
    begin_count = len(re.findall(r"\\begin\{", tex))
    end_count = len(re.findall(r"\\end\{", tex))
    if begin_count != end_count:
        issues.append(ValidationIssue(
            code="unbalanced_environments",
            message=f"Unbalanced \\begin/\\end ({begin_count} begins, {end_count} ends)",
        ))
    line_count = len(tex.splitlines())
    if line_count > _MAX_LINES:
        issues.append(ValidationIssue(
            code="too_long",
            message=f"Resume tex has {line_count} lines (max {_MAX_LINES})",
        ))
    return issues


def _years_allowed_from_open_ended(master_tex: str) -> set[str]:
    if not _OPEN_ENDED_RE.search(master_tex):
        return set()
    return {str(date.today().year)}


def _fact_issues(tex: str, master_tex: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    master_years = _extract_years(master_tex)
    tailored_years = _extract_years(tex)
    extra_years = tailored_years - master_years - _years_allowed_from_open_ended(master_tex)
    if extra_years:
        issues.append(ValidationIssue(
            code="new_years",
            message=f"Years not in master resume: {', '.join(sorted(extra_years))}",
        ))

    master_employers = _extract_employer_tokens(master_tex)
    tailored_employers = _extract_employer_tokens(tex)
    extra_employers = tailored_employers - master_employers
    if extra_employers:
        issues.append(ValidationIssue(
            code="new_employers",
            message=f"Employer tokens not in master resume: {', '.join(sorted(extra_employers))}",
        ))
    return issues


def validate_tex_content(tex: str, master_tex: str) -> ValidationResult:
    issues = _structure_issues(tex) + _fact_issues(tex, master_tex)
    return ValidationResult(ok=not issues, issues=issues)
