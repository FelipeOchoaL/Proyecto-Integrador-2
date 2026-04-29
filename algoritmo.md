# Estrategia de Búsqueda Semántica — Patentologos

Plan para implementar una búsqueda semántica efectiva sobre el corpus de patentes usando **dos algoritmos combinados** (BM25 + Sentence-BERT con fusión RRF) más K-means como segundo algoritmo de descubrimiento.

---

## 1. Análisis de opciones

Para el dataset de patentes (`ti`, `ab`, `descripcion`, `claimen`, `cpc`, etc.):

| Técnica | ¿Sirve aquí? | Rol ideal |
|---|---|---|
| **Índice invertido / BM25** (Full-Text Search de Postgres) | Sí, muy bien | **Búsqueda léxica:** matches exactos, números de patente, siglas CPC/IC, términos técnicos. Rápido (ms), offline, barato. |
| **Sentence-BERT (embeddings)** | Sí, el núcleo semántico | **Búsqueda semántica:** encuentra "vehículo autónomo" cuando buscas "carro que se maneja solo". Captura sinónimos y parafraseo. |
| **KNN** | Sí, pero no es un algoritmo de búsqueda por sí solo | Es el **método de recuperación** sobre los embeddings de Sentence-BERT. Con `pgvector` ya viene incluido (HNSW/IVFFlat). |
| **K-means clustering** | No para buscar, sí para descubrir | Útil para agrupar patentes ("muéstrame clusters temáticos") o para **navegación/exploración**, no para responder una query. Buen extra, no el motor principal. |
| **RAG** | Después, no ahora | RAG = "recuperar docs + pasar a un LLM". La búsqueda híbrida **es** el "R" de RAG. Cuando se agregue IA para análisis, ya estará lista la base. |
| **Consultas SQL `ILIKE`** | Insuficiente | Es lo que hay hoy en `PatentService.search`. Solo hace `LIKE '%texto%'`. No entiende sinónimos, no rankea, lento con millones de filas. |

---

## 2. Recomendación: búsqueda híbrida BM25 + Sentence-BERT

Arquitectura estándar en Elasticsearch, Weaviate, Vespa, y motores de patentes como Google Patents y Lens.org. Combina:

- **Léxico (BM25)** → precisión en términos exactos y siglas.
- **Semántico (embeddings + KNN)** → recall en significado.
- **Fusión de rankings (RRF)** → une ambos resultados en una sola lista ordenada.

### Por qué es ideal para patentes

Las patentes tienen dos naturalezas mezcladas:

1. **Jerga técnica y códigos:** `CPC=A61K`, `PN=US10123456B2`. BM25 las encuentra perfecto, los embeddings no.
2. **Descripciones en lenguaje natural:** "método para sintetizar un compuesto que inhibe…". Los embeddings capturan significado, BM25 falla si el usuario usa sinónimos.

Usar solo uno pierde la mitad de los casos. La fusión RRF soluciona esto.

---

## 3. Arquitectura concreta

Se aprovecha **Supabase (Postgres)**: soporta ambas técnicas sin añadir infraestructura.

```
┌─────────────────────────────────────────────────┐
│  Supabase (Postgres)                            │
│                                                 │
│  tabla patentes                                 │
│    ├─ ti, ab, descripcion, claimen (texto)      │
│    ├─ search_vector  tsvector  ← índice GIN     │  BM25 / FTS
│    └─ embedding      vector(384) ← índice HNSW  │  Semántico
│                                                 │
└─────────────────────────────────────────────────┘
                ▲                ▲
                │                │
        consulta FTS       KNN vectorial
                │                │
                └────── RRF ─────┘
                        │
                     resultados
```

### (A) Postgres Full-Text Search para BM25 (léxico)

Postgres trae `tsvector` + `tsquery` + `ts_rank_cd` (similar a BM25). Se activa la extensión `pg_trgm` para matching fuzzy de strings cortos (números de patente, siglas).

```sql
ALTER TABLE patentes ADD COLUMN search_vector tsvector
  GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(ti,'')), 'A') ||
    setweight(to_tsvector('english', coalesce(ab,'')), 'B') ||
    setweight(to_tsvector('english', coalesce(descripcion,'')), 'C') ||
    setweight(to_tsvector('english', coalesce(claimen,'')), 'D')
  ) STORED;

CREATE INDEX idx_patentes_fts ON patentes USING GIN (search_vector);
```

El `setweight` le da más peso al título y abstract que a las claims.

### (B) pgvector + Sentence-BERT (semántico)

Supabase soporta `pgvector` nativamente. Se agrega una columna `embedding vector(384)` y un índice HNSW.

El modelo Sentence-BERT se corre offline una sola vez sobre las patentes y se guarda el vector. Opciones gratuitas recomendadas:

| Modelo | Dim | Idioma | Uso |
|---|---|---|---|
| **`all-MiniLM-L6-v2`** | 384 | Inglés | Rápido, ligero, excelente baseline |
| **`paraphrase-multilingual-MiniLM-L12-v2`** | 384 | Multilingüe (ES/EN) | Si las patentes son bilingües |
| **`BAAI/bge-small-en-v1.5`** | 384 | Inglés | Mejor calidad que MiniLM, misma dim |
| **`PatentSBERTa`** | 768 | Inglés, fine-tuneado en patentes | Top de gama, específico del dominio |

**Recomendación pragmática:** empezar con `all-MiniLM-L6-v2` (384 dim, corre en CPU en segundos). Si después hay problemas de calidad, subir a `PatentSBERTa`.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE patentes ADD COLUMN embedding vector(384);
CREATE INDEX idx_patentes_embedding ON patentes
  USING hnsw (embedding vector_cosine_ops);
```

### (C) Fusión con Reciprocal Rank Fusion (RRF)

No hace falta ML para combinar. **RRF** es una fórmula simple que pondera posiciones, no scores (que son incomparables entre BM25 y coseno):

```
RRF_score(doc) = Σ  1 / (k + rank_i(doc))
                  i∈{FTS, vector}
```

Con `k=60` (valor estándar). En SQL:

```sql
WITH fts AS (
  SELECT id, ROW_NUMBER() OVER (ORDER BY ts_rank_cd(search_vector, query) DESC) AS r
  FROM patentes, to_tsquery('english', :q) query
  WHERE search_vector @@ query
  LIMIT 50
),
sem AS (
  SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> :query_embedding) AS r
  FROM patentes
  ORDER BY embedding <=> :query_embedding
  LIMIT 50
)
SELECT p.*, SUM(1.0 / (60 + COALESCE(fts.r, 1000)) +
                 1.0 / (60 + COALESCE(sem.r, 1000))) AS score
FROM patentes p
LEFT JOIN fts ON fts.id = p.id
LEFT JOIN sem ON sem.id = p.id
WHERE fts.id IS NOT NULL OR sem.id IS NOT NULL
GROUP BY p.id
ORDER BY score DESC
LIMIT 20;
```

---

## 4. K-means como segundo algoritmo

La combinación ganadora para la rúbrica académica es:

**Algoritmo 1: BM25 + Sentence-BERT con RRF** → motor de búsqueda principal.

**Algoritmo 2: K-means sobre los embeddings** → features de exploración/descubrimiento:

- "Patentes similares a esta" (mostrar las 10 más cercanas en el cluster de la patente abierta).
- "Mapa temático" de patentes (visualización con UMAP/t-SNE y colores por cluster).
- Etiquetado automático: darle al cluster 0 el nombre "biotecnología" después de inspeccionar.

K-means es barato (`sklearn.cluster.KMeans(n_clusters=20).fit(embeddings)`) y entrega un feature visual potente para la sustentación. Académicamente suma porque demuestra dos técnicas con roles distintos.

---

## 5. Flujo de implementación paso a paso

### Fase 1 — Indexación (offline, una sola vez al cargar)

1. Cargar patentes a Supabase (ya se hace con `upload_to_supabase.py`).
2. Script Python que recorra las patentes, concatene `ti + ab + descripcion`, genere embeddings con `sentence-transformers`:

   ```python
   from sentence_transformers import SentenceTransformer
   model = SentenceTransformer("all-MiniLM-L6-v2")
   text = f"{patent.ti}. {patent.ab}"
   embedding = model.encode(text, normalize_embeddings=True).tolist()
   ```

3. `UPDATE patentes SET embedding = :emb WHERE id = :id`.
4. `search_vector` se genera solo (columna `GENERATED`).
5. K-means offline: `labels = KMeans(20).fit_predict(embeddings)`, guardar la etiqueta en una columna `cluster_id`.

### Fase 2 — Endpoint de búsqueda (online)

En `PatentService.search(query: str)`:

1. Calcular embedding de la query en vivo (~50ms en CPU con MiniLM).
2. Ejecutar el SQL híbrido con RRF (arriba).
3. Retornar los top-20 ordenados.

### Fase 3 — Features semánticas extra

1. Endpoint `GET /patentes/{id}/similares` → KNN puro sobre el embedding de esa patente.
2. Endpoint `GET /patentes/clusters` → devuelve las agrupaciones para un mapa visual.

### Fase 4 — Cuando se agregue IA para análisis (después)

Ya está el "R" de RAG. Solo falta:

1. Tomar los top-5 resultados de la búsqueda híbrida.
2. Armar un prompt: "Analiza estas 5 patentes y responde: {pregunta_usuario}".
3. Llamar a un LLM (OpenAI, Claude, Gemini, o uno local tipo Llama).

Esto es RAG "puro" y el salto es pequeño porque la recuperación ya está resuelta.

---

## 6. Comparativa: costos y rendimiento

Para ~10k patentes (tamaño del dataset `ppulse-export`):

| Métrica | Solo ILIKE (hoy) | Solo BM25 | Solo embeddings | **Híbrido (recomendado)** |
|---|---|---|---|---|
| Latencia búsqueda | 500–2000ms | 5–20ms | 10–30ms | 30–60ms |
| Calidad términos exactos | Media | **Alta** | Baja | **Alta** |
| Calidad sinónimos/parafraseo | Muy baja | Baja | **Alta** | **Alta** |
| Storage extra | 0 | +30% | +~15MB (384 floats × 10k) | +30% + 15MB |
| Costo de cómputo | 0 | 0 | ~1 hora CPU para indexar | ~1 hora CPU indexar |
| Dependencias nuevas | 0 | 0 (Postgres nativo) | `pgvector` + `sentence-transformers` | `pgvector` + `sentence-transformers` |

---

## 7. Resumen ejecutivo

- **Dos algoritmos principales: BM25 (FTS de Postgres) + Sentence-BERT con pgvector.** Se combinan con RRF.
- **K-means como segundo entregable** para clustering/descubrimiento y "patentes similares".
- **Todo dentro de Supabase**, sin añadir infraestructura. Activar `pg_trgm` y `pgvector`.
- **Sentence-BERT recomendado:** `all-MiniLM-L6-v2` (general) o `PatentSBERTa` (mejor calidad, dominio específico).
- **RAG queda para después:** el pipeline híbrido ya es el "Retrieval"; solo hay que enchufar el LLM cuando llegue esa fase.

---

## 8. Entregables concretos cuando se implemente

- Migración SQL (`pgvector` + columna `embedding` + `tsvector` + índices GIN/HNSW).
- Script Python de indexación con Sentence-BERT (`project/backend/exel/generate_embeddings.py`).
- Endpoint `POST /patentes/search/semantic` con RRF en `project/backend/app/routes/patents.py`.
- Endpoint `GET /patentes/{id}/similares` (KNN).
- Script de K-means + columna `cluster_id`.
- Tests automáticos que validen: (a) búsqueda léxica recupera match exacto de `pn`, (b) búsqueda semántica recupera parafraseo.
