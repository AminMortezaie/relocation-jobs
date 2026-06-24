function hasAtsScore(job) {
  return job?.ats_score != null && job?.ats_score !== "";
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
  return [...scored, ...unscored];
}
