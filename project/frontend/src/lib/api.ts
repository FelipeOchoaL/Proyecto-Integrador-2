const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface PatentSummary {
  id: number;
  pn: string;
  pc: string;
  cpc: string;
  ic: string;
  ws: string;
  ls: string;
  ti: string;
  ab: string;
  espacenet: string;
}

export interface Patent extends PatentSummary {
  descripcion: string;
  claimen: string;
}

export interface PaginatedResponse {
  data: PatentSummary[];
  count: number;
  page: number;
  page_size: number;
}

export async function fetchPatents(
  page = 1,
  pageSize = 20,
  query?: string
): Promise<PaginatedResponse> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (query) params.set("q", query);

  const res = await fetch(`${API_URL}/patentes/?${params}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Error ${res.status}`);
  return res.json();
}

export async function fetchPatentById(id: number): Promise<Patent> {
  const res = await fetch(`${API_URL}/patentes/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Error ${res.status}`);
  return res.json();
}
