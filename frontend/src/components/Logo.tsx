/** WorkWeave mark: two strands (a worker and a job) woven into a "W". */
export default function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="9" fill="#166a4d" />
      <path d="M6 9 12 23.5 18 9" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M14 9 20 23.5 26 9" fill="none" stroke="#166a4d" strokeWidth="6.4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M14 9 20 23.5 26 9" fill="none" stroke="#f0ad1c" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
