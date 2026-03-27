/**
 * Export screening hits at or above a fuzzy-score threshold with certainty notes.
 * Scores are string-similarity only — not legal proof of identity.
 */
import type { ScreeningNameSearchResponse, ScreeningSource } from '../services/api';

export const SCREENING_SCORE_EXPORT_MIN = 0.8;

type SectionRecord = Record<string, unknown> | null;

/** Heuristic: very common given names → higher homonym risk */
const COMMON_GIVEN = new Set(
  [
    'john',
    'james',
    'david',
    'michael',
    'robert',
    'william',
    'richard',
    'thomas',
    'mary',
    'patricia',
    'jennifer',
    'maria',
    'susan',
    'linda',
    'mohammed',
    'muhammad',
    'ali',
    'ahmed',
    'anna',
    'jose',
    'carlos',
  ]
);

function normaliseToken(t: string): string {
  return t
    .toLowerCase()
    .replace(/[^a-z]/g, '');
}

function hasCommonGivenName(queryName: string): boolean {
  const parts = queryName.trim().split(/\s+/).map(normaliseToken).filter(Boolean);
  return parts.some((p) => COMMON_GIVEN.has(p));
}

export type CertaintyExport = {
  false_positive_risk: 'Lower' | 'Medium' | 'Higher';
  certainty_summary: string;
  investigator_notes: string;
};

/**
 * Plain-language guidance: we never claim "true positive" from fuzzy score alone.
 * Risk bands combine score + DOB presence + common-name heuristic.
 */
export function assessCertainty(
  fuzzyScore: number,
  queryName: string,
  queryDob: string | null | undefined,
  source: ScreeningSource
): CertaintyExport {
  const dobSupplied = !!(queryDob && queryDob.trim());
  const commonName = hasCommonGivenName(queryName);

  let false_positive_risk: CertaintyExport['false_positive_risk'] = 'Medium';
  if (fuzzyScore >= 0.95 && dobSupplied && !commonName) {
    false_positive_risk = 'Lower';
  } else if (fuzzyScore < 0.85 || commonName || !dobSupplied) {
    false_positive_risk = 'Higher';
  }

  const lines: string[] = [];

  lines.push(
    `Name fuzzy score ${fuzzyScore.toFixed(4)} measures string similarity between your query and the returned label — it is not a statistical probability of being the same person.`
  );

  if (dobSupplied) {
    lines.push(
      'DOB was entered on the query: compare any birth date shown on the upstream record; agreement supports identity; mismatch suggests a different individual or data error.'
    );
  } else {
    lines.push(
      'No DOB on the query: homonyms are common — treat hits as leads until corroborated (DOB, address, ID, or official list reference).'
    );
  }

  if (commonName) {
    lines.push(
      'Common given name: higher chance of unrelated namesakes even when the fuzzy score is high.'
    );
  }

  if (source === 'opensanctions') {
    lines.push(
      'OpenSanctions: a hit means the indexed entity resembles your query; confirm entity ID, datasets, and programme (sanctions/PEP) before relying on it for compliance decisions.'
    );
  } else if (source === 'aleph') {
    lines.push(
      'Aleph: results come from investigative material; similar names may refer to different people — read the underlying entity and documents.'
    );
  } else {
    lines.push(
      'Sayari: corporate and network records; natural-person matches may be directors or shareholders — verify jurisdiction and role.'
    );
  }

  lines.push(
    'True positive (same individual as intended) vs false positive (wrong person or weak relevance) cannot be determined from this UI alone; manual adjudication is required.'
  );

  let certainty_summary: string;
  if (false_positive_risk === 'Lower') {
    certainty_summary = 'Stronger string match with fewer collision signals — still verify identity.';
  } else if (false_positive_risk === 'Higher') {
    certainty_summary = 'Weaker match or higher name-collision risk — treat as tentative.';
  } else {
    certainty_summary = 'Moderate match — corroborate with DOB or official identifiers.';
  }

  return {
    false_positive_risk,
    certainty_summary,
    investigator_notes: lines.join(' '),
  };
}

export type ScreeningCsvRow = {
  query_name: string;
  query_dob: string;
  source: ScreeningSource;
  fuzzy_score: number;
  matched_label: string;
  record_id: string;
  schema: string;
  datasets_or_collection: string;
  extra: string;
  false_positive_risk: string;
  certainty_summary: string;
  investigator_notes: string;
};

function extractRow(
  source: ScreeningSource,
  row: Record<string, unknown>,
  queryName: string,
  queryDob: string | null | undefined
): ScreeningCsvRow | null {
  const raw = row.score;
  const score = typeof raw === 'number' ? raw : Number.parseFloat(String(raw ?? ''));
  if (!Number.isFinite(score) || score < SCREENING_SCORE_EXPORT_MIN) {
    return null;
  }
  const label =
    (row.caption as string) ||
    (row.label as string) ||
    (row.name as string) ||
    '';
  const id = row.id != null ? String(row.id) : '';
  const schema = row.schema != null ? String(row.schema) : '';
  const ds = row.datasets;
  const datasetsOrCollection = Array.isArray(ds)
    ? ds.join('; ')
    : row.collection != null
      ? String(row.collection)
      : '';
  const extraParts: string[] = [];
  if (row.entity_url) extraParts.push(String(row.entity_url));
  if (row.countries) extraParts.push(JSON.stringify(row.countries));
  if (row.type) extraParts.push(`type:${String(row.type)}`);
  if (row.sanctioned != null) extraParts.push(`sanctioned:${String(row.sanctioned)}`);
  if (row.pep != null) extraParts.push(`pep:${String(row.pep)}`);

  const c = assessCertainty(score, queryName, queryDob, source);

  return {
    query_name: queryName,
    query_dob: queryDob?.trim() ?? '',
    source,
    fuzzy_score: score,
    matched_label: label,
    record_id: id,
    schema,
    datasets_or_collection: datasetsOrCollection,
    extra: extraParts.join(' | '),
    false_positive_risk: c.false_positive_risk,
    certainty_summary: c.certainty_summary,
    investigator_notes: c.investigator_notes,
  };
}

function collectMatches(section: SectionRecord): Record<string, unknown>[] {
  if (!section || section.ok !== true) return [];
  const m = section.matches;
  return Array.isArray(m) ? (m as Record<string, unknown>[]) : [];
}

/** Collect all matches ≥ threshold across sources into flat rows. */
export function buildScreeningExportRows(
  data: ScreeningNameSearchResponse,
  queryName: string,
  queryDob: string | null | undefined
): ScreeningCsvRow[] {
  const out: ScreeningCsvRow[] = [];
  const q = queryName.trim();
  for (const source of ['opensanctions', 'aleph', 'sayari'] as const) {
    const sec = data[source] as SectionRecord;
    for (const row of collectMatches(sec)) {
      const r = extractRow(source, row, q, queryDob);
      if (r) out.push(r);
    }
  }
  out.sort((a, b) => b.fuzzy_score - a.fuzzy_score);
  return out;
}

function escapeCsvCell(value: string): string {
  if (value.includes('"') || value.includes(',') || value.includes('\n') || value.includes('\r')) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

const CSV_HEADER: (keyof ScreeningCsvRow)[] = [
  'query_name',
  'query_dob',
  'source',
  'fuzzy_score',
  'matched_label',
  'record_id',
  'schema',
  'datasets_or_collection',
  'extra',
  'false_positive_risk',
  'certainty_summary',
  'investigator_notes',
];

/** Build CSV text (UTF-8) with header row. */
export function screeningMatchesToCsv(rows: ScreeningCsvRow[]): string {
  const header = CSV_HEADER.join(',');
  const lines = rows.map((row) =>
    CSV_HEADER.map((k) => escapeCsvCell(String(row[k] ?? ''))).join(',')
  );
  return [header, ...lines].join('\r\n');
}

/** Trigger browser download of CSV. */
export function downloadScreeningCsv(rows: ScreeningCsvRow[], filenameBase: string): void {
  const csv = screeningMatchesToCsv(rows);
  // UTF-8 BOM so Excel on Windows recognises encoding
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const safe = filenameBase.replace(/[^a-z0-9_-]+/gi, '_').slice(0, 80) || 'screening';
  a.href = url;
  a.download = `${safe}_matches_ge_0.8.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
