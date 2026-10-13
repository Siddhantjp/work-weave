import Logo from "./Logo";

/** Logo + wordmark. "Work" upright, "Weave" in italic green, set in the display serif. */
export default function Brand({ size = 34, className = "" }: { size?: number; className?: string }) {
  return (
    <span className={`flex items-center gap-2.5 whitespace-nowrap font-display text-[1.35rem] font-semibold leading-none tracking-tight sm:gap-3 sm:text-2xl ${className}`}>
      <Logo size={size} />
      <span>Work<em className="text-brand">Weave</em></span>
    </span>
  );
}
