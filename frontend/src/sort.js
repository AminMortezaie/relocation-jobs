function hasAtsScore(job) {
  return job?.ats_score != null && job?.ats_score !== "";
}

function sortPinnedJobsFirst(jobs) {
  if (!jobs?.length) return jobs || [];
  const pinned = jobs.filter((job) => job.pinned);
  const rest = jobs.filter((job) => !job.pinned);
  return [...pinned, ...rest];
}

export function sortJobsForDisplay(jobs) {
  const list = jobs || [];
  if (!list.length) return list;

  const scored = [];
  const unscored = [];
  for (const job of list) {
    if (hasAtsScore(job)) scored.push(job);
    else unscored.push(job);
  }

  scored.sort((a, b) => Number(b.ats_score) - Number(a.ats_score));
  return sortPinnedJobsFirst([...scored, ...unscored]);
}
