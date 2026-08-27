import type { Term } from './types';

export const GEOM = { CARD_W: 170, CARD_H: 56, COL_GAP: 28, ROW_GAP: 72, ROW_IN_GAP: 16, PAD: 24, BAND_PAD: 22, LABEL_W: 120 };
export const DEGREE_CREDITS = 120;
export const COLS = 5;

export const rowsOf = (count: number) => Math.max(1, Math.ceil(count / COLS));
export const bandH = (count: number) => rowsOf(count) * GEOM.CARD_H + (rowsOf(count) - 1) * GEOM.ROW_IN_GAP + GEOM.BAND_PAD * 2;

/** Cards wrap into rows of COLS inside a band starting at `top`; the grid is centred horizontally within `width`. */
export const pos = (top: number, i: number, count: number, width: number) => {
  const cols = Math.min(COLS, Math.max(1, count)), col = i % COLS, row = Math.floor(i / COLS);
  return {
    x: GEOM.LABEL_W + (width - GEOM.LABEL_W) / 2 + (col - (cols - 1) / 2) * (GEOM.CARD_W + GEOM.COL_GAP) - GEOM.CARD_W / 2,
    y: top + GEOM.BAND_PAD + row * (GEOM.CARD_H + GEOM.ROW_IN_GAP),
  };
};

/** Next term after the approved ones: Fall 1, Spring 1, (Summer 1), Fall 2 ... */
export function nextTerm(terms: Term[], breaks: boolean): Term {
  const last = terms[terms.length - 1];
  const year = (k: string) => Number(k.split(' ')[1]);
  if (!last) return { name: 'Fall 1', kind: 'Fall', courses: [] };
  const y = year(last.name);
  const seq: Record<Term['kind'], [Term['kind'], number]> = breaks
    ? { Fall: ['Winter', y], Winter: ['Spring', y], Spring: ['Summer', y], Summer: ['Fall', y + 1] }
    : { Fall: ['Spring', y], Spring: ['Fall', y + 1], Winter: ['Spring', y], Summer: ['Fall', y + 1] };
  const [kind, n] = seq[last.kind];
  return { name: `${kind} ${n}`, kind, courses: [] };
}
