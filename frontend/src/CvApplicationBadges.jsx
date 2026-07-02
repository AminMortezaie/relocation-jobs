import { companyWorkspacePath } from "./companyWorkspace";

function CvApplicationBadges({ job, company }) {
  if (!job?.has_tailored_tex && !job?.has_pdf) return null;
  const href = companyWorkspacePath(job.country || company?.country, job.company || company?.name);
  return (
    <>
      {job.has_pdf ? (
        <a className="badge cv-pdf" href={href} title="Open tailored CV and PDF preview">
          PDF ready
        </a>
      ) : job.has_tailored_tex ? (
        <a className="badge cv-tex" href={href} title="Open tailored LaTeX source">
          CV ready
        </a>
      ) : null}
      {job.master_resume_slug ? (
        <span className="badge cv-master" title="Master resume variant used">
          {job.master_resume_slug}
        </span>
      ) : null}
    </>
  );
}

export default CvApplicationBadges;
