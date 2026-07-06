export const HIDE_REASONS = [
  { id: "not_for_me", label: "Not for me", desc: "Role doesn't fit your goals", tone: "not-for-me" },
  { id: "expired", label: "Expired", desc: "Posting closed or no longer available", tone: "expired" },
  { id: "wrong_location", label: "Wrong location", desc: "City or region isn't relevant", tone: "wrong-location" },
  { id: "no_relocation", label: "No relocation", desc: "No visa or relocation support", tone: "no-relocation" },
];

export function notForMeReasonMeta(reason) {
  const hit = HIDE_REASONS.find((r) => r.id === reason);
  if (hit) return { label: hit.label, badgeCls: hit.tone };
  return { label: HIDE_REASONS[0].label, badgeCls: HIDE_REASONS[0].tone };
}
