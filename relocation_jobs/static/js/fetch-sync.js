/** Bridge between vanilla fetch orchestration and the React fetch UI. */

let fetchRevision = 0;

export function publishFetchView(view) {
  fetchRevision += 1;
  const payload = { ...view, rev: fetchRevision };
  const api = window.relocationJobs;
  if (api?.setFetchView) {
    api.setFetchView(payload);
    return;
  }
  if (!window.relocationJobs) window.relocationJobs = {};
  window.relocationJobs._pendingFetchView = payload;
}
