type BrandMarkProps = {
  size?: "default" | "compact";
};

const BIRD_SRC = "/static/icons/kuchup-bird.png";

export function BrandMark({ size = "default" }: BrandMarkProps) {
  const box =
    size === "compact"
      ? "h-[2.15rem] w-[2.15rem] rounded-[10px] p-[0.22rem]"
      : "h-[2.65rem] w-[2.65rem] rounded-xl p-[0.28rem]";

  return (
    <span
      className={`flex shrink-0 items-center justify-center overflow-hidden bg-white shadow-[0_6px_18px_rgba(15,23,42,0.18)] ${box}`}
      aria-hidden="true"
    >
      <img
        src={BIRD_SRC}
        alt=""
        className="h-full w-full object-contain"
        width={64}
        height={60}
      />
    </span>
  );
}
