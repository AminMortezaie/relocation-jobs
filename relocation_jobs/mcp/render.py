from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_COMPILE_TIMEOUT_SEC = 60
_TECTONIC_INCOMPATIBLE_PACKAGES = ("fontawesome5", "fontawesome")
_USEPACKAGE_RE = re.compile(r"^\\usepackage(\[[^\]]*\])?\{([^}]+)\}")


@dataclass
class CompileResult:
    ok: bool
    log: str = ""
    pdf_path: str = ""


def _latex_command() -> str:
    return (os.environ.get("MCP_LATEX_CMD") or "tectonic").strip() or "tectonic"


def sanitize_tex_for_tectonic(tex: str) -> tuple[str, list[str]]:
    removed: list[str] = []
    kept: list[str] = []
    for line in tex.splitlines():
        match = _USEPACKAGE_RE.match(line.strip())
        if match is not None:
            packages = [part.strip() for part in match.group(2).split(",")]
            blocked = [pkg for pkg in packages if pkg in _TECTONIC_INCOMPATIBLE_PACKAGES]
            if blocked:
                removed.extend(blocked)
                continue
        kept.append(line)
    sanitized = "\n".join(kept)
    if tex.endswith("\n"):
        sanitized += "\n"
    return sanitized, removed


def _build_command(cmd: str, tex_path: Path, out_dir: Path) -> list[str]:
    name = Path(cmd).name
    if name == "tectonic":
        return [cmd, "--outdir", str(out_dir), str(tex_path)]
    if name in ("pdflatex", "xelatex", "lualatex"):
        return [cmd, "-interaction=nonstopmode", "-output-directory", str(out_dir), str(tex_path)]
    return [cmd, str(tex_path)]


def _compile_failed(result: CompileResult, pdf_path: Path) -> bool:
    if result.ok and pdf_path.is_file():
        return False
    return True


def _should_retry_without_fontawesome(result: CompileResult, pdf_path: Path, cmd: str) -> bool:
    if Path(cmd).name != "tectonic":
        return False
    if not _compile_failed(result, pdf_path):
        return False
    log = (result.log or "").strip()
    if not log or log == "note: Running TeX ...":
        return True
    return "fontawesome" in log.lower()


def _run_compile(tex_path: Path, out_dir: Path) -> CompileResult:
    pdf_path = out_dir / tex_path.with_suffix(".pdf").name
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

    log = ((completed.stdout or "") + (completed.stderr or "")).strip()
    if completed.returncode == 0 and pdf_path.is_file():
        return CompileResult(ok=True, pdf_path=str(pdf_path), log=log)
    return CompileResult(
        ok=False,
        log=log or f"Compile failed (exit {completed.returncode})",
    )


def render_tex_to_pdf(tex_path: Path) -> CompileResult:
    if not tex_path.is_file():
        return CompileResult(ok=False, log=f"Tex file not found: {tex_path}")

    out_dir = tex_path.parent
    original = tex_path.read_text(encoding="utf-8")
    result = _run_compile(tex_path, out_dir)
    pdf_path = out_dir / tex_path.with_suffix(".pdf").name
    if not _should_retry_without_fontawesome(result, pdf_path, _latex_command()):
        return result

    sanitized, removed = sanitize_tex_for_tectonic(original)
    if not removed or sanitized == original:
        return result

    tex_path.write_text(sanitized, encoding="utf-8")
    retry = _run_compile(tex_path, out_dir)
    tex_path.write_text(original, encoding="utf-8")
    if retry.ok:
        pkgs = ", ".join(sorted(set(removed)))
        note = f"Compiled after omitting tectonic-incompatible package(s): {pkgs}"
        retry.log = f"{note}\n\n{retry.log}".strip()
        return retry

    combined = f"{result.log}\n\nRetry without {', '.join(sorted(set(removed)))}:\n{retry.log}"
    return CompileResult(ok=False, log=combined.strip())
