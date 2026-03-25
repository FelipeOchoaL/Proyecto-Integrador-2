from supabase import Client

SUMMARY_COLUMNS = "id,pn,pc,cpc,ic,ws,ls,ti,ab,espacenet"
ALL_COLUMNS = "*"


class PatentService:
    def __init__(self, client: Client):
        self._client = client
        self._table = "patentes"

    def get_all(self, page: int = 1, page_size: int = 50) -> tuple[list[dict], int]:
        offset = (page - 1) * page_size

        count_resp = self._client.table(self._table).select("id", count="exact").execute()
        total = count_resp.count or 0

        data_resp = (
            self._client.table(self._table)
            .select(SUMMARY_COLUMNS)
            .order("id")
            .range(offset, offset + page_size - 1)
            .execute()
        )

        return data_resp.data, total

    def get_by_id(self, patent_id: int) -> dict | None:
        resp = (
            self._client.table(self._table)
            .select(ALL_COLUMNS)
            .eq("id", patent_id)
            .single()
            .execute()
        )
        return resp.data

    def search(self, query: str, page: int = 1, page_size: int = 50) -> tuple[list[dict], int]:
        offset = (page - 1) * page_size

        count_resp = (
            self._client.table(self._table)
            .select("id", count="exact")
            .or_(f"ti.ilike.%{query}%,ab.ilike.%{query}%,pn.ilike.%{query}%")
            .execute()
        )
        total = count_resp.count or 0

        data_resp = (
            self._client.table(self._table)
            .select(SUMMARY_COLUMNS)
            .or_(f"ti.ilike.%{query}%,ab.ilike.%{query}%,pn.ilike.%{query}%")
            .order("id")
            .range(offset, offset + page_size - 1)
            .execute()
        )

        return data_resp.data, total
