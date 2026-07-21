const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(path, API_BASE);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
    });
  }
  const res = await fetch(url.toString());
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.error?.message || `API error ${res.status}`);
  }
  return res.json();
}

export interface Unit {
  id: string;
  name: string;
  type: string;
  as_of: string;
  officials_count?: number;
  latest_fy?: number;
  next_meeting?: string;
  website?: string;
  population?: number;
  has_spend_detail?: boolean;
  has_meetings?: boolean;
  latest_afr_year?: number;
  latest_afr_filed_on_time?: boolean;
}

export interface Official {
  role: string;
  name: string;
  email?: string;
  phone?: string;
  term_end?: string;
  certainty: string;
  source_url: string;
  as_of: string;
}

export interface AFRYear {
  fiscal_year: number;
  total_revenues: number;
  total_expenditures: number;
  fund_balance?: number;
  total_debt?: number;
  fund_detail?: Record<string, Record<string, number>>;
  filed_on_time?: boolean;
  source_url: string;
  per_capita_expenditures?: number;
  per_capita_revenues?: number;
}

export interface Meeting {
  id: number;
  unit_name: string;
  body: string;
  meeting_ts: string;
  status: string;
  agenda_url?: string;
}

export interface Provenance {
  source_url: string;
  as_of: string;
  certainty: string;
  note?: string;
}

export async function findGovernments(address: string) {
  return fetchAPI<{
    matched_address: string;
    point: { lat: number; lng: number };
    units: Unit[];
    provenance: Provenance;
  }>("/governments", { address });
}

export async function listUnits(type?: string, query?: string) {
  return fetchAPI<{ units: Unit[] }>("/units", { type: type || "", query: query || "" });
}

export async function getUnit(unitId: string) {
  return fetchAPI<Unit & { provenance: Provenance }>(`/units/${unitId}`);
}

export async function getOfficials(unitId: string) {
  return fetchAPI<{ unit_id: string; officials: Official[]; provenance: Provenance }>(
    `/units/${unitId}/officials`
  );
}

export async function getFinances(unitId: string, yearsBack = 3) {
  return fetchAPI<{ unit_id: string; years: AFRYear[]; provenance: Provenance }>(
    `/units/${unitId}/finances`,
    { years_back: String(yearsBack) }
  );
}

export async function compareUnits(unitIds: string[], metric: string, fiscalYear?: number) {
  return fetchAPI<{
    metric: string;
    results: { unit_id: string; name: string; fiscal_year: number; value: number | null }[];
    provenance: Provenance;
  }>("/compare", {
    unit_ids: unitIds.join(","),
    metric,
    fiscal_year: fiscalYear ? String(fiscalYear) : "",
  });
}

export async function getFreshness(unitId?: string) {
  return fetchAPI<Record<string, { rows: number; as_of?: string; latest_fy?: number }>>(
    "/freshness",
    unitId ? { unit_id: unitId } : {}
  );
}
