# CognitiveBaseAI — Evidence-based Scientific Reasoning Engine

[![License: Non-Commercial](https://img.shields.io/badge/license-Non--Commercial-orange)](LICENSE)

> Интеллектуальная база знаний научных публикаций, которая преобразует
> неструктурированный текст в проверяемые **scientific claims**, evidence и
> взвешенный граф знаний, а затем отвечает на вопросы со ссылкой на источники,
> ограничения и противоречия.

| Слой | Технологии |
|------|------------|
| Backend | FastAPI · SQLAlchemy 2 · Alembic · Pydantic v2 · Neo4j Python driver · sentence-transformers (опц.) |
| Storage | **Neo4j 5** — единственный источник истины графа знаний (Publication / ScientificClaim / ScientificEntity / DocumentChunk / ResearchField и все рёбра); `/v1/graph/*`, `/v1/publications`, `/v1/knowledge/*` читают через Cypher. **PostgreSQL 15 + pgvector** — operational таблицы (jobs / runs / RAG history / evaluations / feedback / review / users) и одна таблица `scikb_embeddings(target_kind, target_id, embedding vector(384))` с HNSW для векторного поиска. Активация и горячий кэш — in-process. |
| Frontend | React 19 · TypeScript 5.9 · Vite 7 · Three.js (3D-граф) · custom design system с light/dark темами и i18n RU/EN |
| Infra | Docker Compose · Traefik · Prometheus + Grafana · Adminer · Alembic-миграции в entrypoint |

---

## Что было сделано в этой ветке

1. **Neo4j-first архитектура** ([orm.py](backend/app/features/scientific_kb/orm.py),
   миграция [2026051704_neo4j_first.py](backend/alembic/versions/2026051704_neo4j_first.py)):
   граф знаний живёт в Neo4j (единый источник истины), PostgreSQL хранит
   **11 операционных таблиц** `scikb_*` + системную `users` + единую
   `scikb_embeddings(target_kind, target_id, embedding vector(384))`.
2. **Persistence-адаптеры** ([backend/app/features/scientific_kb/persistence/](backend/app/features/scientific_kb/persistence/))
   для Neo4j (Cypher MERGE + batch fetch) и PostgreSQL (операционные данные
   + pgvector) с graceful fallback на in-memory.
3. **EmbeddingService** ([embedding_service.py](backend/app/features/scientific_kb/embedding_service.py))
   — sentence-transformers + детерминированный fallback.
4. **Pipeline Orchestrator с retry/idempotency**
   ([pipeline.py](backend/app/features/scientific_kb/pipeline.py)) и
   per-step персистенс.
5. **Полная hybrid-формула 7-компонентного scoring** (TZ §3.7)
   в [search.py](backend/app/features/scientific_kb/search.py).
6. **Feedback Loop** ([feedback_service.py](backend/app/features/scientific_kb/feedback_service.py))
   — события реально применяются к claims/relations/queue.
7. **+16 API endpoints** ([api/scientific_kb.py](backend/app/api/scientific_kb.py))
   — pipeline, knowledge, activation, 4 режима search, graph subgraphs,
   evaluation, feedback, review queue.
8. **53 русскоязычные демо-публикации школьного уровня** ([demo.py](backend/app/features/scientific_kb/demo.py)) +
   **seed-данные** ([seed.py](backend/app/features/scientific_kb/seed.py)): 12 авторов,
   6 организаций (МГУ, СПбГУ, ИТМО, школьные кафедры), 38 цитирований.
9. **Quality gate** ([tests/test_demo_coverage.py](backend/tests/test_demo_coverage.py))
   — 10 pytest-проверок: ≥50 публикаций, ≥3/7 entity types на пуб, ≥5/9 claim types на пуб,
   все типы глобально, все 4 типа relation, ≥20 citations.
10. **Lab UI** ([LabPage.tsx](frontend/src/features/lab/LabPage.tsx)) —
    4 режима поиска (keyword/semantic/graph/hybrid), ReasoningTrace,
    ScoreBreakdown, feedback, review queue, метрики, **светлая и тёмная темы**.
11. **JWT-аутентификация** ([api/auth.py](backend/app/api/auth.py),
    [features/auth/](frontend/src/features/auth/)) — register/login/refresh/me/logout,
    bcrypt + PyJWT, auto-refresh при 401 во frontend.
12. **pgvector вместо Qdrant** — векторы 384-dim хранятся в **единой**
    таблице `scikb_embeddings(target_kind, target_id, embedding vector(384))`
    с HNSW-индексом по cosine_ops. `target_id` ссылается на id узла Neo4j;
    in-process кэш активации заменил Redis. Стек сокращён до
    **2 хранилищ** (Neo4j + PostgreSQL).
13. **React Router 7** + `/`, `/lab`, `/graph`, `/manage`. `ManagePage` имеет
    четыре вкладки: библиотека публикаций (CRUD + delete), очередь проверки
    (approve/reject), история RAG-ответов, экспорт графа (JSON) и
    результатов поиска (CSV).
14. **Resize канваса графа перетаскиванием нижнего края** (вместо slider'а
    «Высота»). Hover показывает grip-ручку, dblclick сбрасывает на 680px.

---

## Быстрый старт

### Docker (рекомендуется)

```bash
cp .env.example .env
docker compose --profile dev up -d
```

После запуска:

- **Frontend (UI)**: http://localhost:5173
- **Backend (FastAPI)**: http://localhost:8000/docs
- **Neo4j Browser**: http://localhost:7474 (login: `neo4j` / см. `.env`)
- **Adminer (PostgreSQL)**: http://localhost:8080
- **Prometheus / Grafana**: http://localhost:9090 / http://localhost:3000 (профиль `monitoring`)

При первом запуске backend:

1. Alembic применяет миграции:
   - `2026051502_scientific_kb_schema.py` — изначальные 22 `scikb_*` таблицы (исторически);
   - `2026051603_pgvector_embeddings.py` — `CREATE EXTENSION vector` + HNSW-индексы;
   - **`2026051704_neo4j_first.py`** — drop'ает 13+ графовых таблиц и
     создаёт единую `scikb_embeddings(target_kind, target_id, vec384)`
     с HNSW по cosine_ops.
2. FastAPI lifespan запускает `bootstrap_persistence()` — MERGE'ит
   in-memory демо-корпус (53 публикации, 583 chunks, 497 claims, 103 entities)
   в Neo4j через stable content-hash ID's; embeddings — в `scikb_embeddings`.
   Благодаря stable IDs, повторные старты идемпотентны.

### Локальная разработка (без Docker)

```bash
cd backend
pip install -r requirements.txt
PYTHONPATH=. uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

При отсутствии PostgreSQL/Neo4j адаптеры логируют warning и продолжают работу
с in-memory хранилищем — пайплайн остаётся полностью работоспособным.

---

## Архитектура

```
PDF / Text Upload
   │
   ▼
Pipeline Orchestrator (12 steps, retry, idempotency, extraction_run_id)
   │
   ├──► Text Extraction ──► Section Detection ──► Semantic Chunking
   │
   ├──► Embeddings (sentence-transformers | deterministic) ──► pgvector (HNSW)
   │
   ├──► Entity Extraction ──► Entity Normalization Registry (aliases)
   │
   ├──► Claim Extraction v2  (subject-predicate-object-condition,
   │                          9 типов: definition · method_description ·
   │                          experimental_result · comparison · limitation ·
   │                          hypothesis · conclusion · contradiction_candidate ·
   │                          replication_note)
   │
   ├──► Claim Relations (supports / contradicts / limits / extends)
   │
   ├──► Weighted Knowledge Graph (Neo4j: nodes + weighted edges)
   │
   └──► Activation Index (in-process cache)

User Question
   ▼
Query Understanding ──► Activation Keys ──► Hybrid Retrieval (7-component)
   ▼
Evidence Builder ──► RAG Service (grounded answer · reasoning trace · refusal)
   ▼
Evaluation (8 метрик) ──► Feedback Loop (applies deltas + review queue)
```

Подробнее: [docs/architecture.md](docs/architecture.md), [docs/data_model.md](docs/data_model.md).

---


| # | Требование | Где реализовано |
|---|---|---|
| 1 | Pipeline Orchestrator с retry/idempotency и extraction_run_id | [pipeline.py](backend/app/features/scientific_kb/pipeline.py) |
| 2 | Claims v2: SPOC + evidence + confidence + evidence_strength + source_reliability + contradiction_risk | [models.py](backend/app/features/scientific_kb/models.py), [orm.py](backend/app/features/scientific_kb/orm.py) |
| 3 | Weighted Neo4j graph с supports/contradicts/limits/extends | [persistence/neo4j_adapter.py](backend/app/features/scientific_kb/persistence/neo4j_adapter.py) |
| 4 | Activation Index и activation keys | [search.py](backend/app/features/scientific_kb/search.py), in-process cache |
| 5 | Hybrid search с 7-компонентным score breakdown | [search.py](backend/app/features/scientific_kb/search.py) |
| 6 | Evidence Strength Model (section-weighted, citation-aware) | [extraction.py](backend/app/features/scientific_kb/extraction.py) |
| 7 | Entity Normalization Registry с aliases + merge candidates | [ontology.py](backend/app/features/scientific_kb/ontology.py), [extraction.py](backend/app/features/scientific_kb/extraction.py) |
| 8 | Feedback Loop от evaluation к обновлению весов / review queue | [feedback_service.py](backend/app/features/scientific_kb/feedback_service.py) |
| 9 | Reasoning trace: question → activation → entities → claims → evidence → answer | [rag.py](backend/app/features/scientific_kb/rag.py), [ReasoningTrace.tsx](frontend/src/shared/ui/ReasoningTrace.tsx) |
| 10 | Demonstration of refusal when evidence is insufficient | [rag.py — `_refusal_answer`](backend/app/features/scientific_kb/rag.py) |
| 11 | Метрики faithfulness, source_coverage, hallucination_rate, citation_correctness, contradiction_awareness | [rag.py — `evaluate_rag_answer`](backend/app/features/scientific_kb/rag.py) |

---

## Тесты

```bash
cd backend
python -m pytest tests/test_demo_coverage.py -v
```

Ожидаемо: 8 passed.

```bash
cd frontend
npx tsc --noEmit
npm run build
```

Ожидаемо: TypeScript без ошибок, vite build успешен.

---

## Безопасность

- Все секреты — только через переменные окружения (`.env`, не в git).
- `.env.example` содержит **только placeholder'ы** ("changeme_*").
- Backend в `unhandled_exception_handler` не раскрывает внутренние переменные.
- `detect-secrets` запускается в CI ([\.github/workflows/ci.yml](.github/workflows/ci.yml))
  перед merge.

---

## Документация

- [docs/architecture.md](docs/architecture.md) — компонентная диаграмма + sequence
- [docs/data_model.md](docs/data_model.md) — ER PostgreSQL + Neo4j schema
- [docs/api.md](docs/api.md) — справочник 35+ endpoints с curl-примерами
