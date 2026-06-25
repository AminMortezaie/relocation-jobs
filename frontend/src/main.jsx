import { StrictMode, useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { createRoot } from "react-dom/client";
import App from "./App";
import BoardPagination from "./BoardPagination";
import FetchHeader from "./FetchHeader";
import FetchPanel from "./FetchPanel";

function BoardRoot() {
  const [view, setView] = useState({ loading: true, companies: [], ui: {}, pagination: null });

  const setBoardView = useCallback((next) => {
    setView(next);
  }, []);

  useEffect(() => {
    window.relocationJobs = window.relocationJobs || {};
    window.relocationJobs.setBoardView = setBoardView;
    if (window.relocationJobs._pendingView) {
      setBoardView(window.relocationJobs._pendingView);
      window.relocationJobs._pendingView = null;
    }
  }, [setBoardView]);

  const paginationMount = document.getElementById("board-pagination-root");

  return (
    <>
      {paginationMount
        ? createPortal(<BoardPagination pagination={view.pagination} />, paginationMount)
        : null}
      <App view={view} />
    </>
  );
}

function FetchRoot() {
  const [fetchView, setFetchView] = useState({ header: {}, panel: {}, rev: 0 });

  const setFetchViewFn = useCallback((next) => {
    setFetchView({ ...next });
  }, []);

  useEffect(() => {
    window.relocationJobs = window.relocationJobs || {};
    window.relocationJobs.setFetchView = setFetchViewFn;
    if (window.relocationJobs._pendingFetchView) {
      setFetchViewFn(window.relocationJobs._pendingFetchView);
      window.relocationJobs._pendingFetchView = null;
    }
  }, [setFetchViewFn]);

  const headerMount = document.getElementById("fetch-header-root");
  const panel = fetchView.panel || {};

  return (
    <>
      {headerMount
        ? createPortal(<FetchHeader header={fetchView.header || {}} />, headerMount)
        : null}
      {createPortal(<FetchPanel panel={panel} />, document.body)}
    </>
  );
}

const boardMount = document.getElementById("jobs");
if (boardMount) {
  createRoot(boardMount).render(
    <StrictMode>
      <BoardRoot />
    </StrictMode>,
  );
}

createRoot(document.getElementById("fetch-panel-root") || document.body).render(
  <StrictMode>
    <FetchRoot />
  </StrictMode>,
);
