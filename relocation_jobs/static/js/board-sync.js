/** Bridge between vanilla panel code and the React job board. */

export function publishBoardView(view) {
  const api = window.relocationJobs;
  if (api?.setBoardView) {
    api.setBoardView(view);
    return;
  }
  if (!window.relocationJobs) window.relocationJobs = {};
  window.relocationJobs._pendingView = view;
}
