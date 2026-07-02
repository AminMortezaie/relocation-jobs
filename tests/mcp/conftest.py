from __future__ import annotations

import pytest

from relocation_jobs.mcp import repo as mcp_repo
from relocation_jobs.mcp.types import ApplicationProfile

GO_MASTER_TEX = r"""
\documentclass{article}
\begin{document}
\company{Example Corp} \hfill 2020 -- 2024\\
\position{Go Backend Engineer}
\end{document}
"""

JAVA_MASTER_TEX = r"""
\documentclass{article}
\begin{document}
\company{Java Corp} \hfill 2019 -- 2023\\
\position{Java Backend Engineer}
\end{document}
"""


@pytest.fixture
def mcp_documents(db):
    mcp_repo.save_master_resume(1, "go", GO_MASTER_TEX, label="Go backend")
    mcp_repo.save_master_resume(1, "java", JAVA_MASTER_TEX, label="Java backend")
    mcp_repo.save_profile(1, ApplicationProfile(full_name="Test User", email="test@example.com"))
    yield
