import type { Term } from './types';

export const GEOM = { CARD_W: 170, CARD_H: 56, COL_GAP: 28, ROW_GAP: 72, PAD: 24, BAND_PAD: 22, LABEL_W: 120 };
export const DEGREE_CREDITS = 120;

/** Level = semester band (top to bottom); a band's courses are centred horizontally within `width`. */
export const pos = (level: number, i: number, count: number, width: number) => ({
  x: GEOM.LABEL_W + (width - GEOM.LABEL_W) / 2 + (i - (count - 1) / 2) * (GEOM.CARD_W + GEOM.COL_GAP) - GEOM.CARD_W / 2,
  y: GEOM.PAD + GEOM.BAND_PAD + level * (GEOM.CARD_H + GEOM.BAND_PAD * 2 + GEOM.ROW_GAP),
});
export const bandH = GEOM.CARD_H + GEOM.BAND_PAD * 2;

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
