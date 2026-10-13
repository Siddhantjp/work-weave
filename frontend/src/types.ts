export interface Profile {
  desired_trades?: string[]; experience_months?: number | null; home_locality?: string | null; has_vehicle?: boolean | null;
  owns_tools?: boolean | null; latest_shift_end_hour?: number | null;
}
export interface Job {
  rank: number; title: string; employer: string; locality?: string | null; distance_km?: number | null; salary_text?: string | null;
  rationale?: string; url: string; acquired_at?: string | null; valid_through?: string | null;
  verdict?: { status: string; missing?: string[] };
  requirements?: { shift?: string; vehicle_required?: string; min_experience_months?: number | null } | null;
}
export interface SearchResult {
  ranked: Job[]; profile?: Profile | null; language?: string | null; refresh_failed?: string | null;
  removed_by_hard_limits?: { title: string; employer: string }[];
}
export interface Me { id: string; name: string; email: string; picture: string | null }
export interface HistoryRow { id: number; request: string; status: string; created_at: string; result: SearchResult | null }
