from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

_COMPILE_TIMEOUT_SEC = 60


@dataclass
class CompileResult:
    ok: bool
    log: str = ""
    pdf_path: str = ""


def _latex_command() -> str:
    return (os.environ.get("MCP_LATEX_CMD") or "tectonic").strip() or "tectonic"


def _build_command(cmd: str, tex_path: Path, out_dir: Path) -> list[str]:
    name = Path(cmd).name
    if name == "tectonic":
        return [cmd, "--outdir", str(out_dir), str(tex_path)]
    if name in ("pdflatex", "xelatex", "lualatex"):
        return [cmd, "-interaction=nonstopmode", "-output-directory", str(out_dir), str(tex_path)]
    return [cmd, str(tex_path)]


def render_tex_to_pdf(tex_path: Path) -> CompileResult:
    if not tex_path.is_file():
        return CompileResult(ok=False, log=f"Tex file not found: {tex_path}")

    out_dir = tex_path.parent
    pdf_name = tex_path.with_suffix(".pdf").name
    cmd = _latex_command()
    argv = _build_command(cmd, tex_path, out_dir)

    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=_COMPILE_TIMEOUT_SEC,
            cwd=str(out_dir),
            check=False,
        )
    except FileNotFoundError:
        return CompileResult(
            ok=False,
            log=f"LaTeX compiler not found: {cmd}. Install tectonic or set MCP_LATEX_CMD.",
        )
    except subprocess.TimeoutExpired:
        return CompileResult(ok=False, log=f"LaTeX compile timed out after {_COMPILE_TIMEOUT_SEC}s")

    log = (completed.stdout or "") + (completed.stderr or "")
    pdf_path = out_dir / pdf_name
    if completed.returncode != 0 or not pdf_path.is_file():
        return CompileResult(ok=False, log=log.strip() or f"Compile failed (exit {completed.returncode})")

    return CompileResult(ok=True, pdf_path=str(pdf_path), log=log.strip())
