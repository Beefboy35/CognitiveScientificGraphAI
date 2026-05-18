# Scientific KB Architecture (краткая выжимка)

> Полная архитектура: [docs/architecture.md](architecture.md). Модель данных:
> [docs/data_model.md](data_model.md). API: [docs/api.md](api.md).

## Кратко

**Evidence-based Scientific Reasoning Engine** — научная база знаний с
**Neo4j-first** архитектурой:

- **Neo4j** — единый источник истины для графа: Publication, ScientificClaim,
  ScientificEntity, DocumentChunk, ResearchField и все рёбра (CONTAINS_CLAIM,
  CITES, MENTIONS_ENTITY, SUPPORTS/CONTRADICTS/LIMITS/EXTENDS).
- **PostgreSQL** — операционные таблицы (auth, processing jobs,
  RAG history, evaluations, feedback) + единая `scikb_embeddings` (pgvector
  HNSW) для семантического поиска.
- **In-memory state** — горячий кэш + graceful-degradation fallback при
  недоступности БД.

## Реализованный flow

```text
Upload / demo publication
-> Pipeline Orchestrator (12 шагов, retry × 2)
-> Text extraction & section detection
-> Semantic chunking
-> Embeddings (sentence-transformers/all-MiniLM-L6-v2 или deterministic)
-> Entity extraction (rule-based + LLM через OpenRouter)
-> Entity normalization (registry с aliases)
-> ScientificClaim v2 extraction (9 типов)
-> Weighted claim graph (SUPPORTS/CONTRADICTS/LIMITS/EXTENDS)
-> Activation index (in-process)
-> Hybrid search (7-component scoring)
-> Evidence builder + Cypher batch-fetch
-> RAG answer with honest refusal
-> Evaluation (8 metrics) → Feedback events → applied weight deltas
```

## Backend

Основные модули в [backend/app/features/scientific_kb/](../backend/app/features/scientific_kb/):

| Файл | Назначение |
|---|---|
| `service.py` | Доменный engine, агрегирует все mixin'ы |
| `pipeline.py` | 12-шаговый orchestrator с retry/idempotency |
| `extraction.py` | Rule-based + LLM extraction (OpenRouter `openai/gpt-4o-mini`) |
| `search.py` | Hybrid retrieval + Cypher fallback при cache miss |
| `rag.py` | RAG service + honest refusal |
| `feedback_service.py` | Применение feedback delta к claim.confidence + SUPPORTS-весам |
| `ontology.py` | Типы сущностей/claims/relations + aliases |
| `models.py` | Dataclass'ы (DocumentChunk, ScientificClaim, ClaimRelation, …) |
| `utils.py` | `_stable_id` — content-hash IDs |
| `persistence/neo4j_adapter.py` | Cypher MERGE + batch fetch + delete/update |
| `persistence/postgres_adapter.py` | SQLAlchemy ORM upserts (только операционные таблицы) |
| `persistence/pgvector_adapter.py` | Векторный поиск через `scikb_embeddings` |
| `singleton.py` | Bootstrap демо-корпуса + persistence |
| `demo.py`, `seed.py` | 53 русскоязычные школьные публикации |

API: [backend/app/api/scientific_kb.py](../backend/app/api/scientific_kb.py).
Полная карта endpoints — в [docs/api.md](api.md).

## Frontend

[frontend/src/](../frontend/src/) — React 19 + Vite + TypeScript +
react-router-dom 7 со страницами:

- `/` (Work) — каталог публикаций, фильтры, детали;
- `/lab` (Lab) — Activation Keys, Hybrid Search со ScoreBreakdown,
  Reasoning Trace, Feedback Queue;
- `/graph` (Graph) — 3D-визуализация Neo4j-графа через Three.js;
- `/manage` (Manage) — CRUD-операции, PATCH/DELETE публикаций.

## Demo Scenario (см. [docs/defense_script.md](defense_script.md))

1. `docker-compose --env-file .env.dev --profile dev up -d`
2. Открыть `http://localhost:5173`, залогиниться демо-пользователем.
3. Show: 53 публикации в Work, граф с 1898 activation keys, hybrid-search
   на запрос "двоичный поиск", reasoning trace на вопрос "что такое связь
   между таблицами?".
4. Эвалюация ответа → feedback events → claim.confidence обновился в Neo4j.

## MVP Boundaries

- Расширенное LLM-извлечение использует OpenRouter (`EXTRACTION_MODE=hybrid|llm`);
  rule-based path остаётся fallback'ом.
- PDF-парсинг через `pypdf`; OCR для сканов вне MVP.
- Async-очередь pipeline не интегрирована (синхронный orchestrator).
- Корпус — синтетические русскоязычные школьные статьи (50+); реальные
  публикации можно загружать через `/v1/publications/upload`.
