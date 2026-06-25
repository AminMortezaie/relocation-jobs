import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export default function ReferralWidget({ job }) {
  const active = Boolean(job.waiting_referral);
  const [open, setOpen] = useState(false);
  const [linkedin, setLinkedin] = useState((job.referral_linkedin_url || "").trim());
  const [busy, setBusy] = useState(false);
  const wrapRef = useRef(null);
  const popoverRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    setLinkedin((job.referral_linkedin_url || "").trim());
  }, [job.referral_linkedin_url]);

  useEffect(() => {
    const close = () => setOpen(false);
    document.addEventListener("referral-popover-close", close);
    return () => document.removeEventListener("referral-popover-close", close);
  }, []);

  useEffect(() => {
    if (!open) return undefined;

    const backdrop = document.getElementById("referralBackdrop");
    if (backdrop) {
      backdrop.hidden = false;
      backdrop.setAttribute("aria-hidden", "false");
    }

    const onBackdrop = () => setOpen(false);
    backdrop?.addEventListener("click", onBackdrop);

    const onDocClick = (e) => {
      if (popoverRef.current?.contains(e.target)) return;
      if (wrapRef.current?.contains(e.target)) return;
      setOpen(false);
    };

    const timer = window.setTimeout(() => {
      document.addEventListener("click", onDocClick);
      inputRef.current?.focus();
    }, 0);

    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("click", onDocClick);
      backdrop?.removeEventListener("click", onBackdrop);
      if (backdrop) {
        backdrop.hidden = true;
        backdrop.setAttribute("aria-hidden", "true");
      }
    };
  }, [open]);

  async function submit(waitingReferral, linkedinUrl = linkedin) {
    const save = window.relocationJobs?.saveWaitingReferral;
    if (!save) return;
    setBusy(true);
    try {
      const result = await save(job.country, job.company, job.url, waitingReferral, linkedinUrl);
      if (result) setOpen(false);
    } finally {
      setBusy(false);
    }
  }

  function toggleOpen(e) {
    e.stopPropagation();
    if (!open) window.relocationJobs?.closePanelPopovers?.();
    setOpen((prev) => !prev);
  }

  const dateSuffix = job.waiting_referral_date ? ` · ${job.waiting_referral_date}` : "";

  return (
    <>
      <div className="referral-wrap" ref={wrapRef}>
        <button
          type="button"
          className={`referral-btn${active ? " active" : ""}`}
          aria-expanded={open ? "true" : "false"}
          aria-haspopup="dialog"
          title={active ? "Edit referrer LinkedIn" : "Waiting for someone to refer you"}
          onClick={toggleOpen}
        >
          Waiting referral{active ? dateSuffix : ""}
        </button>
      </div>
      {open
        ? createPortal(
            <div
              ref={popoverRef}
              className="referral-popover"
              role="dialog"
              aria-label={`Referrer LinkedIn for ${job.title}`}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="referral-popover-head">
                <span className="referral-popover-title">Referrer LinkedIn</span>
                <button
                  type="button"
                  className="referral-close"
                  aria-label="Close"
                  onClick={() => setOpen(false)}
                >
                  ×
                </button>
              </div>
              <p className="referral-popover-hint">Profile of the person you asked to refer you.</p>
              <input
                ref={inputRef}
                type="url"
                className="referral-linkedin-input"
                placeholder="https://www.linkedin.com/in/username"
                value={linkedin}
                onChange={(e) => setLinkedin(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key !== "Enter") return;
                  e.preventDefault();
                  const url = linkedin.trim();
                  if (!url) {
                    window.relocationJobs?.toast?.("Paste the referrer's LinkedIn profile URL");
                    inputRef.current?.focus();
                    return;
                  }
                  void submit(true, url);
                }}
                spellCheck="false"
              />
              <div className="referral-popover-foot">
                <button
                  type="button"
                  className="referral-save-btn"
                  disabled={busy}
                  onClick={() => {
                    const url = linkedin.trim();
                    if (!url) {
                      window.relocationJobs?.toast?.("Paste the referrer's LinkedIn profile URL");
                      inputRef.current?.focus();
                      return;
                    }
                    void submit(true, url);
                  }}
                >
                  Save
                </button>
                {active ? (
                  <button
                    type="button"
                    className="referral-clear-btn link-btn"
                    disabled={busy}
                    onClick={() => void submit(false)}
                  >
                    Clear status
                  </button>
                ) : null}
              </div>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
