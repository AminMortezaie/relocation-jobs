from __future__ import annotations

from pathlib import Path

from relocation_jobs.mcp.render import render_tex_to_pdf


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
