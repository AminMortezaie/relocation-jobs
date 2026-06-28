export default function PinJobButton({ pinned = false }) {
  return (
    <button
      type="button"
      className={`pin-job-btn${pinned ? " is-pinned" : ""}`}
      title={pinned ? "Pinned to top of board" : "Pin role and company to the top"}
      aria-label={pinned ? "Pinned to top" : "Pin to top"}
      aria-pressed={pinned}
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H8c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1.03-1 1.03 1v-7H19v-2c-1.66 0-3-1.34-3-3z" />
      </svg>
    </button>
  );
}
