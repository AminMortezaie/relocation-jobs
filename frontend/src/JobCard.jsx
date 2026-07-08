import { memo, useRef, useEffect } from "react";

function JobCard({ job, company, variant }) {
  const ref = useRef(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.job = job;
      ref.current.variant = variant;
    }
  }, [job, variant]);

  return <position-card ref={ref} variant={variant} />;
}

export default memo(JobCard);
