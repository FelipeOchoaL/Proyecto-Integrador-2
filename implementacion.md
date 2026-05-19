# Implementación de la Búsqueda Híbrida — Patentologos

Documento de referencia completa para entender qué se construyó, por qué se eligió cada pieza y cómo poner el sistema a funcionar de cero.

Acompaña a [`algoritmo.md`](./algoritmo.md) (diseño y justificación) y al [`README.md`](./README.md) (instalación general del proyecto).

---

## 0. Resumen ejecutivo (1 minuto)

El backend pasa de una búsqueda con `ILIKE '%texto%'` a una **búsqueda híbrida** que combina:

- **BM25** (Postgres Full-Text Search) → precisión léxica para términos exactos, números de patente, siglas CPC.
- **Sentence-BERT + KNN** (pgvector con índice HNSW) → recall semántico para sinónimos, parafraseo y bilingüismo ES/EN.
- **Reciprocal Rank Fusion (RRF)** → fusiona ambos rankings en una sola lista ordenada, sin entrenar nada.
- **K-means** sobre los embeddings → segundo algoritmo, para descubrimiento y "patentes similares".

Todo dentro de **Supabase (Postgres)**, sin añadir infraestructura nueva.

---

## 1. Pasos para correr el sistema completo (de cero a funcionando)

Tabla resumen para ejecutar el proyecto en orden y ver el algoritmo funcionando:

| # | Paso | Dónde se hace | Comando / Acción | Tiempo aprox | Verificación |
|---|------|---------------|------------------|--------------|--------------|
| 1 | Clonar repo y crear venv | Terminal en raíz del proyecto | `cd project/backend` → `python -m venv venv` → `.\venv\Scripts\Activate.ps1` | 1 min | Aparece `(venv)` en el prompt |
| 2 | Instalar dependencias Python | `project/backend/` con venv activo | `pip install --upgrade pip` → `pip install -r requirements.txt` | 3–8 min (descarga `torch` ~500 MB) | `pip list` muestra `sentence-transformers`, `scikit-learn`, `numpy`, `tqdm`, `fastapi`, etc. |
| 3 | Crear `.env` del backend | `project/backend/.env` | Pegar `SUPABASE_URL`, `SUPABASE_KEY`, `FRONTEND_ORIGIN=http://localhost:3000` | 1 min | El archivo existe |
| 4 | Correr migración 001 (extensiones + columnas + índices base) | Supabase → SQL Editor | Pegar y ejecutar `project/backend/migrations/001_enable_extensions_and_columns.sql` | < 30 s | `SELECT count(*) FROM patentes WHERE search_vector IS NOT NULL;` = total |
| 5 | Correr migración 003 (columnas nuevas: apc, pd, ww, lg_st + UNIQUE en pn + search_vector extendido) | Supabase → SQL Editor | Pegar y ejecutar `project/backend/migrations/003_new_columns_and_unique_pn.sql` | < 30 s | `SELECT conname FROM pg_constraint WHERE conname='patentes_pn_unique';` devuelve 1 fila |
| 6 | Correr migración 002 (RPCs `search_patentes_hybrid` y `patentes_similares`) | Supabase → SQL Editor | Pegar y ejecutar `project/backend/migrations/002_hybrid_search_function.sql` (ya con la firma nueva: apc/ww/lg_st/pd) | < 5 s | `SELECT proname FROM pg_proc WHERE proname IN ('search_patentes_hybrid','patentes_similares');` devuelve 2 filas |
| 6.5 | Cargar los Excel a Supabase | `project/backend/exel/` | Coloca los `ppulse-export*.xlsx` y `ppulse-desc*.xlsx` ahí dentro → `python convert_xlsx_to_csv.py` → `python upload_to_supabase.py` | 5–15 min | `SELECT count(*) FROM patentes;` muestra los nuevos. Re-ejecutar el upload no duplica filas. |
| 7 | Generar embeddings (offline, una vez) | `project/backend/` con venv activo | `python -m exel.generate_embeddings` | 5–20 min para ~10k patentes en CPU | `SELECT count(*) FROM patentes WHERE embedding IS NOT NULL;` = total |
| 8 | (Opcional) Calcular K-means | `project/backend/` con venv activo | `python -m exel.cluster_patentes` (o `$env:KMEANS_K="30"; python -m exel.cluster_patentes`) | 1–5 min | `SELECT cluster_id, count(*) FROM patentes GROUP BY cluster_id;` muestra 20 grupos |
| 9 | Levantar backend | `project/backend/` con venv activo | `python -m uvicorn app.main:app --reload` | < 5 s arranque | <http://127.0.0.1:8000/docs> abre Swagger |
| 10 | Probar búsqueda híbrida | Swagger UI | `POST /patentes/search/semantic` con body `{"query": "vehículo autónomo con cámara", "top_k": 20}` | Primera: 3–5 s (carga modelo). Siguientes: ~100 ms | Resultados con `rrf_score` decreciente |
| 11 | Probar patentes similares | Swagger UI | `GET /patentes/{id}/similares?top_k=10` con un id real | ~50 ms | 10 patentes con `distance` ascendente |
| 12 | Levantar frontend | Otra terminal en `project/frontend/` | `npm install` (la 1ra vez) → `npm run dev` | 30 s | <http://localhost:3000> abre la app |
| 13 | (Pendiente) Conectar frontend a los nuevos endpoints | `project/frontend/src/lib/api.ts` y componentes | Añadir cliente HTTP para `/search/semantic` y `/{id}/similares`, conectar al input de búsqueda y a la vista de detalle | — | El input de búsqueda devuelve resultados rankeados por `rrf_score` |

> **Estado actual del proyecto:** ya se hicieron los pasos 1–6. Lo que falta es del 7 en adelante.

---

## 2. Arquitectura general

```
┌─────────────────────────────────────────────────────────────┐
│  OFFLINE (corres una vez)                                   │
│                                                             │
│  ① upload_to_supabase.py  ──► tabla patentes (texto crudo)  │
│  ② generate_embeddings.py ──► UPDATE embedding (vector 384) │
│  ③ cluster_patentes.py    ──► UPDATE cluster_id             │
│                                                             │
│  search_vector se llena solo (columna GENERATED).           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  ONLINE (cada request del usuario)                          │
│                                                             │
│  POST /patentes/search/semantic                             │
│       │                                                     │
│       ▼                                                     │
│  routes/patents.py → PatentService.search_semantic(query)   │
│       │                                                     │
│       ├─ encode_query(query) ─► vector(384) en ~50 ms       │
│       │                                                     │
│       └─ supabase.rpc("search_patentes_hybrid", {...})      │
│              │                                              │
│              ▼ (todo dentro de Postgres)                    │
│         FTS rank ──┐                                        │
│                    ├──► RRF ──► top 20 por rrf_score        │
│         KNN rank ──┘                                        │
│                                                             │
│  GET /patentes/{id}/similares                               │
│       └─ supabase.rpc("patentes_similares", {...})          │
│              └─► KNN puro sobre embedding de esa patente    │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Algoritmo 1 — BM25 vía Postgres Full-Text Search

### 3.1 Qué es

Un ranking estadístico clásico de la familia TF-IDF. Cuenta cuántas veces aparece cada palabra de la query en cada documento, normaliza por la longitud del documento y por la rareza de cada palabra (palabras raras pesan más).

### 3.2 Por qué Postgres FTS y no Elasticsearch

Postgres trae `tsvector` + `tsquery` + `ts_rank_cd`, que es **muy parecido a BM25** y es **gratis** (ya está en Supabase). Para 10k–100k patentes va sobrado. Elasticsearch añadiría un servicio extra a mantener.

### 3.3 Cómo se implementó

En `migrations/001_enable_extensions_and_columns.sql` se agrega una columna **calculada automáticamente** (`GENERATED ALWAYS AS ... STORED`) que combina los cuatro campos textuales con pesos:

```sql
ALTER TABLE patentes
  ADD COLUMN IF NOT EXISTS search_vector tsvector
  GENERATED ALWAYS AS (
    setweight(to_tsvector('simple', coalesce(ti,'')),          'A') ||
    setweight(to_tsvector('simple', coalesce(ab,'')),          'B') ||
    setweight(to_tsvector('simple', coalesce(descripcion,'')), 'C') ||
    setweight(to_tsvector('simple', coalesce(claimen,'')),     'D')
  ) STORED;

CREATE INDEX IF NOT EXISTS idx_patentes_fts
  ON patentes USING GIN (search_vector);
```

Detalles importantes:

- **`'simple'` en vez de `'english'` o `'spanish'`:** porque tu corpus está mezclado ES/EN. `'english'` aplica stemming inglés que destroza palabras en español. `'simple'` no hace stemming, solo lowercases y separa por espacios. Es la opción segura para corpus bilingüe.
- **Pesos A>B>C>D**: el título cuenta más que el abstract, que cuenta más que la descripción, que cuenta más que las claims. Las claims suelen ser texto legal larguísimo; meterlas con peso D evita que dominen el ranking.
- **`STORED`**: el `tsvector` se materializa al insertar/actualizar, no se recalcula en cada query.
- **Índice GIN**: hace que `WHERE search_vector @@ query` sea de milisegundos en vez de segundos.

### 3.4 Para qué sirve y para qué no

**Sirve para:** números de patente (`US10123456B2`), siglas CPC (`A61K`), términos técnicos exactos. Latencia: 5–20 ms.

**No sirve para:** sinónimos, parafraseo, traducción ES↔EN. Si el usuario busca "carro" y la patente dice "vehículo", no hay match.

---

## 4. Algoritmo 2 — Sentence-BERT + pgvector + HNSW

Aquí está el cambio fuerte: representar cada patente como un **vector de 384 números** que codifica su significado, y buscar por **cercanía** entre vectores.

### 4.1 Modelo elegido: `paraphrase-multilingual-MiniLM-L12-v2`

| Característica | Valor | Por qué importa |
|---|---|---|
| **Multilingüe (50+ idiomas, ES y EN incluidos)** | Sí | Tu dataset está en español y en inglés. Un modelo monolingüe inglés (`all-MiniLM-L6-v2`) ignoraría el español. Este maneja ambos en el mismo espacio vectorial: una query en español puede recuperar una patente en inglés. |
| **Dimensión 384** | 384 floats | Sweet spot: suficientemente expresivo, suficientemente pequeño. Por eso la migración define `embedding vector(384)`. Si cambias de modelo, **tienes que cambiar este número** y re-correr todo. |
| **Tamaño** | ~120 MB | Cabe en RAM de cualquier laptop. Se descarga una sola vez. |
| **Velocidad** | 30–80 ms por query en CPU | No necesitas GPU. |
| **Arquitectura** | MiniLM L12 (12 capas Transformer destiladas de BERT) | Versión "pequeña" de BERT entrenada con destilación de conocimiento. Mantiene buena calidad y reduce mucho el cómputo. |
| **Entrenamiento** | Paráfrasis multilingüe (sentence pairs equivalentes) | Optimizado para que dos frases que significan lo mismo en idiomas distintos den vectores cercanos. Exactamente lo que necesitas. |

#### Alternativas consideradas y descartadas

- **`all-MiniLM-L6-v2`**: el "estándar" del mundo Sentence-BERT, pero solo inglés. Si el corpus fuera 100% inglés sería la opción.
- **`PatentSBERTa`**: fine-tuneado en patentes, dim 768, mejor calidad de dominio pero solo inglés y más pesado. Sería el upgrade si después detectas que la calidad semántica no alcanza.
- **`bge-small-en-v1.5`**: muy buen modelo pero también solo inglés.

### 4.2 Por qué `normalize_embeddings=True`

Tanto en `embedding_service.py` como en `generate_embeddings.py` se llama `model.encode(..., normalize_embeddings=True)`. Esto convierte cada vector a norma 1. Con vectores normalizados, la **distancia coseno** (`<=>` en pgvector) es equivalente al producto interno y queda en `[0, 2]` con interpretación clara: 0 = idénticos, 1 = ortogonales, 2 = opuestos. Esto matchea con el operador `vector_cosine_ops` que se usa en el índice HNSW.

### 4.3 pgvector y el índice HNSW

`pgvector` es la extensión de Postgres que añade el tipo `vector(N)` y los operadores `<=>` (coseno), `<->` (L2), `<#>` (producto interno).

```sql
CREATE INDEX IF NOT EXISTS idx_patentes_embedding
  ON patentes USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```

**HNSW (Hierarchical Navigable Small World)** es un grafo en capas que aproxima KNN en `O(log N)` en vez de `O(N)`. Comparado con la otra opción de pgvector (`IVFFlat`), HNSW da mejor recall y no necesita re-entrenar índice cuando cambia el dataset. Es más lento de construir pero más rápido de consultar.

- `m=16` y `ef_construction=64` son los valores por defecto recomendados por la documentación de pgvector para datasets de hasta cientos de miles de filas.

### 4.4 El otro índice: `pg_trgm` sobre `pn`

```sql
CREATE INDEX IF NOT EXISTS idx_patentes_pn_trgm
  ON patentes USING GIN (pn gin_trgm_ops);
```

`pg_trgm` indexa **trigramas** (subcadenas de 3 letras) y permite que `ILIKE '%US101%'` use índice. Útil para números de patente y siglas que el usuario puede teclear con typos o con/sin espacios. Es el respaldo del `PatentService.search()` clásico.

### 4.5 Lazy loading del modelo en el backend

El modelo Sentence-BERT pesa ~120 MB y tarda ~3 s en cargar. Por eso `embedding_service.py` lo guarda como **singleton** thread-safe:

- La primera request a `/search/semantic` paga ese coste.
- Las siguientes solo pagan el `encode` (~50 ms).
- Si quieres evitar la latencia inicial en producción, llama `get_model()` en el startup de FastAPI.

---

## 5. Reciprocal Rank Fusion (RRF) — el pegamento

### 5.1 El problema

Tienes dos rankings (uno léxico, uno semántico). Sus scores son **incomparables**: BM25 puede dar 0.0–10.0, coseno da 0.0–1.0. ¿Cómo se mezclan?

### 5.2 La fórmula

**Reciprocal Rank Fusion** (Cormack et al., 2009) combina **posiciones**, no scores:

```
                                1
RRF_score(doc) =     Σ      ─────────────
                 i ∈ {FTS,    k + rank_i(doc)
                     vector}
```

Para cada documento, suma `1 / (k + posición_que_ocupa_en_ese_ranking)` por cada ranking en el que aparezca. Se usa `k = 60` (valor estándar de la literatura).

### 5.3 Por qué funciona tan bien

Ejemplo concreto:

| Documento | Rank en FTS | Rank en semántico | Aporte FTS    | Aporte sem    | RRF total  |
|-----------|-------------|-------------------|---------------|---------------|------------|
| Doc A     | 1           | 5                 | 1/61 ≈ 0.0164 | 1/65 ≈ 0.0154 | **0.0318** |
| Doc B     | 1           | —                 | 1/61 ≈ 0.0164 | 0             | 0.0164     |
| Doc C     | —           | 1                 | 0             | 1/61 ≈ 0.0164 | 0.0164     |
| Doc D     | 30          | 30                | 1/90 ≈ 0.0111 | 1/90 ≈ 0.0111 | 0.0222     |

Por construcción RRF favorece documentos que aparecen **alto en ambos rankings** (Doc A gana sobre B y C). Y un documento que sale en los dos rankings, aunque no sea #1 en ninguno, puede ganarle a uno que es #1 solo en uno (Doc D le gana a B y C).

El parámetro `k=60` amortigua diferencias entre posiciones cercanas. Si bajaras `k`, la diferencia entre top posiciones se exagera.

### 5.4 Implementación SQL

Está toda en `migrations/002_hybrid_search_function.sql` dentro del RPC `search_patentes_hybrid`. Detalles que vale la pena explicar:

- **`websearch_to_tsquery`** (en vez de `to_tsquery` o `plainto_tsquery`): permite que el usuario escriba en lenguaje natural, con comillas para frases exactas (`"vehículo autónomo"`) y `-palabra` para excluir, sin tener que aprender la sintaxis raruna de Postgres con `&` y `|`.
- **`candidate_pool = 50`**: tomamos los 50 mejores de cada ranking antes de fusionar. Más alto = mejor recall pero más latencia. 50 es un valor balanceado.
- **`FULL OUTER JOIN`**: un documento puede estar solo en FTS, solo en semántico, o en ambos. El `CASE WHEN ... IS NOT NULL` garantiza que si el doc no apareció en uno de los dos rankings, ese término simplemente suma 0.
- **`COALESCE(fts.id, sem.id)`**: para no perder filas si un doc apareció solo en uno de los rankings.

Hay una **segunda función**, `patentes_similares(patent_id, top_k)`, que es solo KNN puro: recupera el embedding de la patente dada y devuelve las top-K más cercanas. Eso alimenta el endpoint "patentes similares".

---

## 6. Algoritmo 3 — K-means (descubrimiento)

### 6.1 Rol

K-means **no es para buscar**, es para **agrupar**. Se corre offline una sola vez (o periódicamente cuando el dataset cambia mucho). Lo que aporta:

1. Un mapa temático del corpus: "estas 200 patentes son de biotecnología, estas 150 de mecánica…"
2. Un canal de exploración alternativo en el frontend ("explorar por área").
3. Académicamente cumple con el requisito típico de la rúbrica de presentar **dos algoritmos** con roles distintos.

### 6.2 Implementación

`exel/cluster_patentes.py`:

- Trae todos los embeddings ya calculados desde Supabase.
- Usa `KMeans` de sklearn con `n_init="auto"` y `random_state=42` (reproducible).
- Para datasets grandes (≥50 000) cambia automáticamente a `MiniBatchKMeans`, que entrena por mini-lotes y es órdenes de magnitud más rápido a costo de inercia ligeramente peor.
- Imprime un resumen por cluster con 5 títulos. Eso es lo que tú lees para asignar **etiquetas humanas** a cada cluster (cluster 0 = "biotecnología", cluster 1 = "mecánica", etc.).

K=20 es un valor por defecto razonable para 10k patentes (~500 patentes por cluster en promedio). Si los temas se ven mezclados, sube K. Si se ven repetidos, baja K.

### 6.3 Por qué K-means y no otros algoritmos

- **DBSCAN/HDBSCAN**: detectan clusters de forma arbitraria y outliers, pero requieren tunear `eps` o `min_samples` y no escalan tan bien.
- **Clustering jerárquico**: te da un dendograma bonito pero es O(N²) en memoria, inviable para 10k+ patentes con vectores de 384 dim.
- **K-means**: O(N·K·D) por iteración, simple, robusto, y el algoritmo "estándar" que siempre se enseña. Para la sustentación es el más fácil de explicar.

K-means asume clusters esféricos en distancia euclídea. Como **normalizamos los embeddings**, todos los vectores viven en la esfera unidad y la distancia euclídea es monótona equivalente a la distancia coseno. Eso hace que K-means con vectores normalizados sea efectivamente "K-means esférico", la formulación correcta para embeddings semánticos.

---

## 7. Inventario de archivos creados/modificados

| Archivo | Estado | Rol |
|---|---|---|
| `algoritmo.md` | Nuevo | Documento de diseño/justificación (para la rúbrica). |
| `implementacion.md` | Nuevo (este archivo) | Guía de implementación + paso a paso. |
| `project/backend/requirements.txt` | Modificado | Añadidas `sentence-transformers`, `scikit-learn`, `numpy`, `tqdm`. |
| `project/backend/migrations/001_enable_extensions_and_columns.sql` | Nuevo | Activa pgvector y pg_trgm; agrega `search_vector`, `embedding`, `cluster_id` con índices. |
| `project/backend/migrations/002_hybrid_search_function.sql` | Nuevo | Define `search_patentes_hybrid` (BM25 + KNN + RRF) y `patentes_similares` (KNN puro) como RPCs. Devuelve también `apc`, `ww`, `lg_st`, `pd` y `cluster_id`. |
| `project/backend/migrations/003_new_columns_and_unique_pn.sql` | Nuevo | Migra al esquema actual: añade `apc`, `pd`, `ww`, `lg_st`; backfillea `ws→ww` y `ls→lg_st`; agrega `UNIQUE(pn)`; reconstruye `search_vector` para que indexe `ww` y `apc`; índices auxiliares. |
| `project/backend/exel/convert_xlsx_to_csv.py` | Reescrito | Detecta automáticamente todos los `ppulse-export*.xlsx` y `ppulse-desc*.xlsx`, normaliza los nombres viejos al esquema nuevo y hace LEFT JOIN por `pn`. Salida: `ppulse-merged.csv`. |
| `project/backend/exel/upload_to_supabase.py` | Reescrito | Pre-carga los `pn` ya en BD, filtra los duplicados y hace `upsert(on_conflict='pn')` por lotes. No toca `embedding`/`cluster_id` de filas existentes. |
| `project/backend/exel/generate_embeddings.py` | Nuevo | Script offline que calcula los 384 floats de cada patente y los sube a Supabase. |
| `project/backend/exel/cluster_patentes.py` | Nuevo | Script offline que agrupa con K-means y guarda `cluster_id`. |
| `project/backend/app/services/embedding_service.py` | Nuevo | Singleton thread-safe que carga el modelo Sentence-BERT y expone `encode_query(text)`. |
| `project/backend/app/services/patent_service.py` | Modificado | Añadidos `search_semantic(query, top_k)` y `get_similares(patent_id, top_k)` que invocan los RPCs. |
| `project/backend/app/routes/patents.py` | Modificado | Añadidos los endpoints `POST /patentes/search/semantic` y `GET /patentes/{id}/similares`. |
| `project/backend/app/models/patent.py` | Modificado | Añadidos los modelos Pydantic `SemanticSearchRequest`, `SemanticSearchResponse`, `SimilarPatentsResponse`, `SemanticSearchResult`, `SimilarPatent`. |

---

## 8. Endpoints disponibles después de levantar el backend

| Endpoint | Body / Query | Qué hace |
|---|---|---|
| `GET /patentes/?page=1&page_size=50` | — | Lista paginada de patentes. |
| `GET /patentes/?q=US10123456` | `q` en query string | Búsqueda léxica clásica con `ILIKE` (fallback rápido para matches exactos). |
| `GET /patentes/{id}` | — | Detalle completo de una patente. |
| `POST /patentes/search/semantic` | `{"query": "...", "top_k": 20}` | **Búsqueda híbrida BM25 + Sentence-BERT con RRF.** Devuelve `rrf_score`, `fts_rank`, `sem_rank` por resultado. |
| `GET /patentes/{id}/similares?top_k=10` | `top_k` en query string | KNN puro sobre embedding. Devuelve `distance` por resultado. |

Todos están documentados automáticamente en <http://127.0.0.1:8000/docs>.

---

## 9. Verificaciones rápidas en SQL

Ya que la mayoría del trabajo está en Postgres, aquí los SELECTs útiles:

```sql
-- ¿Cuántas patentes hay en total?
SELECT count(*) FROM patentes;

-- ¿Cuántas tienen search_vector llenado? (debe ser igual al total tras migración 001)
SELECT count(*) FROM patentes WHERE search_vector IS NOT NULL;

-- ¿Cuántas tienen embedding? (= 0 antes de correr generate_embeddings, = total después)
SELECT count(*) FROM patentes WHERE embedding IS NOT NULL;

-- ¿Cuántas tienen cluster? (= 0 antes de cluster_patentes, = total después)
SELECT count(*) FROM patentes WHERE cluster_id IS NOT NULL;

-- ¿Existen los RPCs?
SELECT proname FROM pg_proc
WHERE proname IN ('search_patentes_hybrid', 'patentes_similares');

-- Distribución de patentes por cluster (después de K-means)
SELECT cluster_id, count(*) AS n
FROM patentes
GROUP BY cluster_id
ORDER BY cluster_id;

-- Probar la búsqueda híbrida directamente desde SQL Editor
-- (requiere pasar un embedding manualmente; más fácil probar desde el endpoint)
SELECT * FROM search_patentes_hybrid(
  query_text := 'vehículo autónomo',
  query_embedding := array_fill(0.0, ARRAY[384])::vector,
  top_k := 10
);
```

---

## 10. Tropiezos comunes

1. **La primera request al endpoint semántico tarda 3–5 s** porque carga el modelo. Las siguientes son ~100 ms. Para producción, llamar `get_model()` en el startup de FastAPI.
2. **El modelo se descarga la primera vez** desde Hugging Face (~120 MB). Necesitas internet para esa primera ejecución; queda en `~/.cache/huggingface/`.
3. **El UPDATE fila por fila en `generate_embeddings.py` es la parte más lenta** (no el modelo). Para 10k patentes va bien; con 100k+ valdría reescribirlo con un `UPSERT` en bloque vía SQL.
4. **Si cambias de modelo** (ej. a `PatentSBERTa` que es 768 dim), tienes que: (a) `ALTER TABLE patentes ALTER COLUMN embedding TYPE vector(768)`, (b) re-correr `generate_embeddings.py`, (c) actualizar `EMBEDDING_DIM` en `embedding_service.py` y la firma del RPC `search_patentes_hybrid` en la migración 002.
5. **El idioma de la query no importa**: el modelo multilingüe mete query y documentos en el mismo espacio vectorial. Una query en español puede recuperar patentes en inglés y viceversa.
6. **Para "explicabilidad"**, el RPC ya devuelve `fts_rank` y `sem_rank`. En el frontend puedes mostrar "matched by: lexical + semantic" o solo uno de los dos.
7. **Recall vs latencia**: si subes `candidate_pool` de 50 a 200 mejoras un poco el recall pero la query pasa de ~30 ms a ~80 ms. 50 es el sweet spot para un dataset de tu tamaño.
8. **`ModuleNotFoundError: No module named 'exel'`** al correr los scripts: tienes que estar parado en `project/backend/` y usar la sintaxis `python -m exel.generate_embeddings`, no `python exel/generate_embeddings.py`.
9. **`KeyError: 'SUPABASE_URL'`** en los scripts: el `.env` no se está cargando. Confirma que existe `project/backend/.env` con `SUPABASE_URL` y `SUPABASE_KEY`.
10. **Supabase pausado** (plan gratuito pausa proyectos inactivos): da error de DNS al conectar. Reactivar en <https://app.supabase.com>.

---

## 11. Costos y rendimiento esperado (para ~10k patentes)

| Métrica | Solo ILIKE (antes) | Solo BM25 | Solo embeddings | **Híbrido (actual)** |
|---|---|---|---|---|
| Latencia búsqueda | 500–2000 ms | 5–20 ms | 10–30 ms | 30–60 ms |
| Calidad términos exactos | Media | **Alta** | Baja | **Alta** |
| Calidad sinónimos/parafraseo | Muy baja | Baja | **Alta** | **Alta** |
| Calidad bilingüe (ES↔EN) | Muy baja | Baja | **Alta** | **Alta** |
| Storage extra | 0 | +30% (search_vector) | +~15 MB (384 floats × 10k) | +30% + 15 MB |
| Costo de cómputo offline | 0 | 0 | ~10 min CPU (1 vez) | ~10 min CPU (1 vez) |
| Dependencias nuevas | 0 | 0 (Postgres nativo) | pgvector + sentence-transformers | pgvector + sentence-transformers |

---

## 12. Qué viene después (roadmap natural)

Una vez funcionando los pasos 1–13:

- **Sprint siguiente — Frontend**: vista de "patentes similares" en el detalle, filtro por cluster, mostrar `rrf_score` como badge "lexical+semantic".
- **Visualización de clusters**: proyectar los embeddings con UMAP o t-SNE a 2D, colorear por `cluster_id`, mostrar como "mapa temático" del corpus.
- **RAG (cuando se agregue IA)**: el pipeline híbrido **es** el "Retrieval" de RAG. Solo falta tomar los top-5, armar un prompt y llamar a un LLM (OpenAI, Claude, Gemini, o uno local). La recuperación ya está resuelta.
- **Pruebas automáticas** (ver `pruebas.md`): tests que validen que (a) la búsqueda léxica recupera match exacto de `pn`, (b) la búsqueda semántica recupera parafraseo, (c) `/similares` no devuelve la propia patente.

---

## 13. Recarga de datos con los nuevos exports

El esquema cambió en la migración 003. Los exports recientes de Patent Pulse traen:

- `ppulse-export*.xlsx` con columnas `pn, apc, cpc, ic, ww, pd, lg_st, ti, ab, claimen*, espacenet`.
- `ppulse-desc*.xlsx` con columnas `pn, desc, espacenet` (descripciones HTML aparte porque pesan).

### 13.1 Mapeo viejo ↔ nuevo

| Antes (CSV viejo) | Ahora (xlsx nuevos) | Acción que hace `convert_xlsx_to_csv.py` |
|---|---|---|
| `pn` | `pn` | Igual. Se usa como clave para JOIN y deduplicación. |
| `pc` (citas) | — | Se descarta: en los exports nuevos no existe y no era equivalente a `apc`. |
| `cpc` | `cpc` | Igual. |
| `ic` | `ic` | Igual. |
| `ws` (categoría amplia) | `ww` (categoría granular) | Renombre: `ws → ww`. |
| `ls` (estado legal) | `lg_st` | Renombre: `ls → lg_st`. |
| — | `apc` | Nueva columna: empresa solicitante. |
| — | `pd` | Nueva columna: fecha de publicación. |
| `ti`, `ab`, `claimen*`, `espacenet` | iguales | Idénticas. |
| `desc` (mismo archivo) | `desc` (archivo aparte) | Se hace LEFT JOIN por `pn`; si la `desc` aparte tiene contenido, gana. Termina en la columna `descripcion`. |

### 13.2 Flujo recomendado para refrescar la BD

1. Copia los xlsx nuevos a `project/backend/exel/` (cualquier nombre que matchee `ppulse-export*.xlsx` y `ppulse-desc*.xlsx` sirve, los paréntesis y espacios del nombre original están bien).
2. Aplica las migraciones en este orden si vienes de la versión anterior: `001` → `003` → `002` (003 trae el esquema nuevo y `UNIQUE(pn)`; 002 redefine los RPCs para devolver los campos nuevos).
3. Genera el CSV unificado:
   ```powershell
   cd project/backend
   .\venv\Scripts\Activate.ps1
   python -m exel.convert_xlsx_to_csv
   ```
   Salida: `project/backend/exel/ppulse-merged.csv`. El script imprime cuántas filas trajo de cada archivo y verifica round-trip.
4. Sube a Supabase con dedup automática:
   ```powershell
   python -m exel.upload_to_supabase
   ```
   Imprime cuántos `pn` ya estaban en BD (los ignora) y cuántos son nuevos. Es seguro re-correrlo: nunca duplica filas y nunca pisa `embedding`/`cluster_id` de las que ya estaban.
5. (Re)genera embeddings y clusters de las filas nuevas:
   ```powershell
   python -m exel.generate_embeddings
   python -m exel.cluster_patentes
   ```
   `generate_embeddings` solo procesa filas con `embedding IS NULL`, así que solo paga el coste de las nuevas. Ahora también incluye la categoría `ww` en el texto a embeber, lo que ayuda a que el clustering separe mejor los temas.

### 13.3 Cómo se garantiza "ningún duplicado"

Triple red de seguridad:

- **Constraint en BD**: `UNIQUE (pn)` (migración 003). Si algo se cuela, Postgres rechaza.
- **Pre-fetch en cliente**: `upload_to_supabase.py` trae todos los `pn` ya presentes y filtra el lote antes de mandar nada.
- **Upsert con `on_conflict="pn"`**: si por race condition o por re-corrida el `pn` ya está, se hace UPDATE de los campos planos (apc, cpc, ic, ww, pd, lg_st, ti, ab, descripcion, claimen, espacenet) sin tocar `embedding` ni `cluster_id`.

### 13.4 Por qué esto da "varios temas" en la BD

El export nuevo (`ppulse-export (2).xlsx`) trae 3.078 patentes repartidas en categorías muy distintas: ~498 de electrical machinery, ~393 de engines/pumps/turbines, ~290 de machine tools, ~269 de medical technology, ~143 de measurement, ~117 de pharmaceuticals, etc. Esa diversidad es exactamente lo que necesita el K-means para encontrar clusters separados (uno por área temática), y lo que hace que la búsqueda híbrida tenga sentido: si el usuario teclea "vacuna mRNA" o "wind turbine blade", existen patentes lo suficientemente distintas en el corpus como para que el ranking importe.

---

## 14. Documentos relacionados

- [`algoritmo.md`](./algoritmo.md) — Estrategia y justificación del diseño (BM25 + Sentence-BERT + K-means).
- [`README.md`](./README.md) — Instalación general del proyecto y arquitectura del repo.
- [`pruebas.md`](./pruebas.md) — Estrategia de pruebas automáticas y protocolo de usabilidad.
