export type Course = {
  id: string; code: string; subject: string; name: string; credits: number;
  offered: string; description: string; prereq_text?: string; departments: string[];
};
export type Program = { id: string; name: string; degree: string; description: string };
/** courseId -> list of OR-groups (all groups required) */
export type Prereqs = Record<string, string[][]>;

export type Term = { name: string; kind: 'Fall' | 'Spring' | 'Summer' | 'Winter'; courses: string[] };
/** verified=false: a 200+ course with no prerequisite found in any source — confirm with an advisor */
export type Suggestion = { id: string; reason: string; unlocks: string[]; verified: boolean; source: string | null };
export type Violation = { id: string; term: number; missing: string[] };
export type Progress = {
  credits: number;
  major: { name: string; have: number; need: number; unit: string; set: string | null; missing: string[][] }[];
  pathways: { slot: string; label: string; course: string | null }[];
};
export type SuggestResponse = {
  suggested: Suggestion[]; candidates: Suggestion[]; progress: Progress; source: 'gemini' | 'heuristic'; violations: Violation[];
};
