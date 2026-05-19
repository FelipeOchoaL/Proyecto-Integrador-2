from fastapi import FastAPI
from app.database import supabase

app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None):
    return {"item_id": item_id, "q": q}

@app.get("/patentes")
def get_patents():
    try:
        response = supabase.table("patentes_prueba").select("*").execute()
        return response.data
    except Exception as e:
        return {"error": str(e)}