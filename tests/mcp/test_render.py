from __future__ import annotations

from pathlib import Path

import pytest

from relocation_jobs.mcp.render import render_tex_to_pdf, sanitize_tex_for_tectonic


def test_render_tex_to_pdf_success(monkeypatch, tmp_path):
    tex = tmp_path / "resume.tex"
    tex.write_text(r"\documentclass{article}\begin{document}Hi\end{document}", encoding="utf-8")
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    def fake_run(argv, **kwargs):
        class Result:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Result()

    monkeypatch.setenv("MCP_LATEX_CMD", "tectonic")
    monkeypatch.setattr("relocation_jobs.mcp.render.subprocess.run", fake_run)

    result = render_tex_to_pdf(tex)
    assert result.ok is True
    assert result.pdf_path == str(pdf)


def test_render_tex_to_pdf_missing_compiler(monkeypatch, tmp_path):
    tex = tmp_path / "resume.tex"
    tex.write_text(r"\documentclass{article}\begin{document}Hi\end{document}", encoding="utf-8")

    def fake_run(argv, **kwargs):
        raise FileNotFoundError(argv[0])

    monkeypatch.setenv("MCP_LATEX_CMD", "missing-latex-binary")
    monkeypatch.setattr("relocation_jobs.mcp.render.subprocess.run", fake_run)

    result = render_tex_to_pdf(tex)
    assert result.ok is False
    assert "not found" in result.log.lower()


def test_sanitize_tex_for_tectonic_removes_fontawesome5():
    tex = r"""
\documentclass{article}
\usepackage{hyperref}
\usepackage{fontawesome5}
\begin{document}
\faGithub\ \href{https://github.com/x}{github}
Hi
\end{document}
"""
    sanitized, removed = sanitize_tex_for_tectonic(tex)
    assert "fontawesome5" in removed
    assert "fa-icons" in removed
    assert "fontawesome5" not in sanitized
    assert r"\faGithub" not in sanitized
    assert r"\usepackage{hyperref}" in sanitized
    assert r"\href{https://github.com/x}{github}" in sanitized


def test_sanitize_tex_for_tectonic_strips_fa_icon_with_argument():
    tex = r"\documentclass{article}\begin{document}\faIcon{github} link\end{document}"
    sanitized, removed = sanitize_tex_for_tectonic(tex)
    assert "fa-icons" in removed
    assert r"\faIcon" not in sanitized
    assert "link" in sanitized


@pytest.mark.skipif(
    __import__("shutil").which("tectonic") is None,
    reason="tectonic not installed",
)
def test_render_tex_to_pdf_sanitizes_fontawesome_before_compile(tmp_path):
    tex = tmp_path / "resume.tex"
    tex.write_text(
        r"""
\documentclass{article}
\usepackage{hyperref}
\usepackage{fontawesome5}
\begin{document}
\faGithub\ \href{https://github.com/x}{github}
\end{document}
""",
        encoding="utf-8",
    )
    result = render_tex_to_pdf(tex)
    assert result.ok is True
    assert (tmp_path / "resume.pdf").is_file()
    assert "fa-icons" in result.log or "fontawesome5" in result.log
    assert r"\usepackage{fontawesome5}" in tex.read_text(encoding="utf-8")


def test_resolve_latex_command_finds_homebrew_tectonic(monkeypatch):
    monkeypatch.delenv("MCP_LATEX_CMD", raising=False)
    monkeypatch.setattr("relocation_jobs.mcp.render.shutil.which", lambda _: None)
    from relocation_jobs.mcp.render import _resolve_latex_command

    if Path("/opt/homebrew/bin/tectonic").is_file():
        assert _resolve_latex_command() == "/opt/homebrew/bin/tectonic"
    else:
        assert _resolve_latex_command() == "tectonic"


def test_sanitize_tex_for_tectonic_replaces_em_dash():
    tex = "2020 -- 2024\nCompany — role"
    sanitized, removed = sanitize_tex_for_tectonic(tex)
    assert "—" not in sanitized
    assert "unicode-em-dash" in removed
