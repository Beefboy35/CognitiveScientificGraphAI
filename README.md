# CognitiveBaseAI — Evidence-based Scientific Reasoning Engine

[![CI](https://github.com/Beefboy35/CognitiveBaseAI/actions/workflows/ci.yml/badge.svg)](https://github.com/Beefboy35/CognitiveBaseAI/actions/workflows/ci.yml)
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

## Раздел «Лаб.» — что это и как пользоваться

Lab — это **полный цикл работы со знаниями** в одном экране: понять как извлекаются знания (3), сравнить как они ищутся (1), увидеть как формируется ответ (2), скорректировать качество (4).

```
        Извлечение из публикации
                  ↓
   ┌── Реестр сущностей + связей (3) ──┐
   ▼                                    ▼
Сравнение режимов поиска (1) ──► RAG ответ + reasoning trace (2)
                                        │
                                        ▼ feedback от юзера
                              Очередь проверки (4)
                                        │ approve / reject
                                        ▼
                              обновление весов claim'ов
                                        │
                                        └─► улучшает следующий RAG-ответ
```

### 1. Сравнение режимов поиска

Четыре режима отвечают на один вопрос — «найди в корпусе самые релевантные фрагменты для запроса» — но используют разные источники сигнала.

| Режим | Источник сигнала | Как считается score | Когда полезен |
|---|---|---|---|
| **Ключевой** ([search_keyword](backend/app/features/scientific_kb/search.py)) | Точное совпадение слов запроса в тексте chunk'ов и claim'ов (с расширением через `ALIASES`) | `overlap / max(1, len(query_tokens))` | Когда пользователь уже знает термин («JOIN», «двоичный поиск») |
| **Семантический** ([search_semantic](backend/app/features/scientific_kb/search.py)) | Cosine similarity между 384-dim векторами вопроса и chunk'а через `pgvector` HNSW | `cosine_similarity` от 0 до 1 | Когда вопрос задан «своими словами» без точной терминологии |
| **Графовый** ([search_graph](backend/app/features/scientific_kb/search.py)) | `activation_index[token]` → активированные claim'ы + их соседи по рёбрам SUPPORTS/CONTRADICTS/EXTENDS/LIMITS | `0.45 + relation_bonus / 4.0` | «Покажи всё, что связано с X» — graph подтянет cluster |
| **Гибридный** ([search_hybrid](backend/app/features/scientific_kb/search.py)) | Объединение всех трёх + 4 компонента качества | См. формулу ниже | Production — это итоговый score, остальные три для дебага |

**Полная hybrid-формула** (TT.md §3.7):
```
hybrid_score = α·keyword + β·semantic + γ·(graph + 0.5·activation)
             + δ·claim_confidence + ε·evidence_strength + ζ·source_reliability
             − η·contradiction_risk

веса по умолчанию: α=0.15, β=0.35, γ=0.20, δ=0.10, ε=0.15, ζ=0.05, η=0.10
```

`ScoreBreakdown` в Lab разбивает финальный score на 7 слагаемых — видно, какой канал сильнее всего вытянул конкретный hit.

### 2. RAG с reasoning trace

Обычный LLM-чат отвечает «откуда-то», и проверить ответ нельзя. RAG ([rag.py:ask_with_evidence](backend/app/features/scientific_kb/rag.py)) сначала **ищет**, потом **отвечает на основе найденного**, и **показывает все источники**.

**7 этапов цепочки**:
1. **Question** — сам вопрос пользователя
2. **Activation keys** — токены вопроса + синонимы из ALIASES
3. **Entities** — сущности онтологии, активированные этими токенами
4. **Claims** — утверждения, упоминающие эти сущности
5. **Evidence** — chunk'и из публикаций, на которых основаны claim'ы (с указанием публикации и страниц)
6. **Aggregation / Contradiction disclosure** — сбор top-4 claim'ов + явное упоминание найденных противоречий
7. **Grounded answer** — финальный ответ + раздел Limitations (что НЕ покрыто)

**Honest refusal**: если `strong_hits < 2` или `coverage < 0.16`, RAG отказывается отвечать. Это защита от галлюцинаций — лучше «недостаточно данных», чем выдуманный ответ.

**Evaluation**: кнопка «Оценить» считает 8 метрик (faithfulness, hallucination_rate, citation_correctness, contradiction_awareness, и др.) и автоматически создаёт feedback_event для каждого source-claim'а.

### 3. Реестр сущностей и связей

Полный аудит того, что система извлекла из корпуса:

- **Сущности** (`ScientificEntity`): канонические понятия из ontology с aliases (`Method` / `Model` / `Tool` / `Metric` / `Task` / `Dataset` / `ResearchField`).
- **Связи** (`ClaimRelation`): направленные рёбра claim ↔ claim четырёх типов:
  - **SUPPORTS** — определение/метод из разных публикаций согласуются
  - **EXTENDS** — один claim явно развивает идею другого (text marker «развивает / опирается на»)
  - **LIMITS** — limitation-claim ограничивает применимость method/conclusion
  - **CONTRADICTS** — противоположные значения метрики или text marker «в отличие от / противоречит»

Каждая связь хранит `created_by ∈ {rule, llm, manual}` для аудита. Связи генерируются **строго по evidence** — никаких искусственных для покрытия онтологии.

### 4. Очередь human-in-the-loop проверки

Автоматическое извлечение не идеально. Пользователь должен иметь возможность отбраковать плохие claim'ы, чтобы они не портили будущие ответы.

**Как claim попадает в очередь** ([feedback_service.py](backend/app/features/scientific_kb/feedback_service.py)):
1. `evaluate_rag_answer` показал `faithfulness < 0.8` для конкретного source-claim → `signal=review_required`
2. Пользователь жмёт 👎 на ответ RAG → создаётся такое же событие
3. Event сохраняется в `scikb_feedback_events`, target claim попадает в `scikb_review_queue`

**Что делает пользователь**:
- **Approve** → `claim.confidence_score += 0.05`
- **Reject** → `claim.confidence_score -= 0.10`
- Изменённый confidence учитывается hybrid-формулой через `δ·claim_confidence` — отвергнутые claim'ы падают в ранжировании, одобренные растут.

---

## Сценарий: пользователь ищет «двоичный поиск» в разделе Лаб.

Допустим, пользователь открыл `/lab`, режим `hybrid` (по умолчанию), вводит `двоичный поиск` и жмёт **Найти**.

### Шаг 1 — Frontend → Backend

`LabPage.tsx:runSearch` → `searchHybrid("двоичный поиск", 8)` → `POST /v1/search/hybrid {"query":"двоичный поиск","top_k":8}`.

### Шаг 2 — Backend разбор запроса

В [search.py:search_hybrid](backend/app/features/scientific_kb/search.py) запускаются **все три** канала с `top_k*3 = 24` кандидатов в каждом + activation:

**Keyword channel** ([_expanded_query_tokens](backend/app/features/scientific_kb/utils.py)):
```
tokens: ["двоичный", "поиск"]
expanded (через ALIASES): ["двоичный", "поиск", "бинарный", "поиск перебором"]
→ Counter overlap с каждым chunk/claim
```
Высший keyword-score получают claim'ы с буквальной фразой «двоичный поиск» (около 8-10 в корпусе).

**Semantic channel** (pgvector HNSW):
```
vec = embed("двоичный поиск")  # 384-dim
SELECT chunk_id FROM scikb_embeddings
WHERE target_kind = 'chunk'
ORDER BY embedding <=> :vec  -- cosine distance
LIMIT 24;
```
Высший semantic-score — у chunk'ов из всех 4 статей кластера «Поиск» + bridge-статей («Сортировка как предусловие», «Индекс работает по принципу двоичного поиска») — близкий вектор по теме.

**Graph channel**:
```
activation_keys("двоичный поиск") → ["двоичный", "поиск", ...]
activation_index["двоичный"] → {claim_ids: [claim_A, claim_B, ...]}
+ neighbors через SUPPORTS/EXTENDS/LIMITS → ещё claim_ids
```

**Activation step** дополнительно поднимает activation_bonus=1.0 для claim'ов, явно активированных вопросом.

### Шаг 3 — Подсчёт 7-компонентного score для каждого hit

Для одного найденного claim'а (например, `claim_b1e5...` = «Двоичный поиск — это алгоритм поиска значения в отсортированном массиве…»):

| Компонент | Значение | Вес | Вклад |
|---|---|---|---|
| keyword (точное совпадение «двоичный поиск») | 1.0 | α=0.15 | 0.150 |
| semantic (cosine similarity вектора) | 0.91 | β=0.35 | 0.319 |
| graph (+ activation_bonus 0.5) | 0.65 | γ=0.20 | 0.130 |
| claim_confidence | 0.78 | δ=0.10 | 0.078 |
| evidence_strength | 0.82 | ε=0.15 | 0.123 |
| source_reliability | 0.75 | ζ=0.05 | 0.038 |
| − contradiction_risk | 0.05 | η=0.10 | −0.005 |
| **Итог** | | | **0.833** |

Все 7 компонент вернутся в `score_breakdown` каждого hit'а.

### Шаг 4 — Что увидит пользователь

В Lab откроется два колонки:

**Слева — список 8 hits**:
```
[CLAIM] 0.833  Двоичный поиск
        Двоичный поиск — это алгоритм поиска значения в отсортированном…

[CLAIM] 0.812  Двоичный поиск в отсортированном массиве
        Алгоритм работает так: программа берёт средний элемент массива…

[CHUNK] 0.798  Двоичный поиск в отсортированном массиве / Метод
        Алгоритм работает так: программа берёт средний элемент массива…
...
```

**Справа — ScoreBreakdown выбранного hit**: stacked bar chart с 7 компонентами + явные веса α/β/γ/δ/ε/ζ/η. Видно, какой канал больше всего сделал ранжирование.

### Шаг 5 — Что произойдёт с весами при approve/reject

В Lab'е секции «Найти» нет approve/reject — это про **поиск**, не про обратную связь. Approve/reject доступны двумя путями:

**Путь A — через RAG-ответ.** Пользователь вводит в секции «Спросить» вопрос «Что такое двоичный поиск?» и нажимает 👎. Тогда:

```
1) submit_feedback({
     target_id: top_source_claim_id (например, claim_b1e5...),
     signal: "review_required",
     payload: {rag_answer_id: rag.id}
   })

2) apply_feedback_event(event):
   - claim.confidence_score = max(0.05, claim.confidence_score - 0.05)
   - claim.evidence_strength = max(0.05, claim.evidence_strength - 0.025)
   - все его SUPPORTS-рёбра: weight = max(0.05, weight - 0.015)

3) Если signal == "review_required":
   review_queue["rv_xxx"] = {
     item_type: "claim",
     item_id: claim_b1e5...,
     status: "open",
     reason: "RAG-feedback signal: review_required"
   }
```

**Путь B — через очередь проверки.** Открыв секцию «Очередь проверки», пользователь видит `claim_b1e5...` со статусом `open`. Жмёт **Approve** или **Reject**:

| Действие | Что меняется в Neo4j (`update_claim_properties`) |
|---|---|
| **Approve** | `confidence_score = min(0.99, confidence + 0.05)` · `evidence_strength = min(0.99, evidence_strength + 0.025)` · `review_queue.status = "resolved"` |
| **Reject** | `confidence_score = max(0.05, confidence − 0.10)` · все исходящие SUPPORTS-рёбра: `weight = max(0.05, weight − 0.05)` · `review_queue.status = "rejected"` |

### Шаг 6 — Эффект на следующий поиск

Тот же запрос `двоичный поиск` после **reject** этого claim'а:

| Компонент | До reject | После reject | Изменение |
|---|---|---|---|
| keyword | 1.0 | 1.0 | — |
| semantic | 0.91 | 0.91 | — |
| graph | 0.65 | 0.61 | SUPPORTS-вес снизился → graph бонус меньше |
| **claim_confidence** | **0.78** | **0.68** | **−0.10** |
| evidence_strength | 0.82 | 0.82 | — |
| **Итог** | **0.833** | **0.815** | **−0.018** |

Reject сдвигает claim вниз в выдаче, и в следующем RAG-ответе он попадёт в evidence только если выше нет альтернатив. Несколько rejects подряд → claim становится «токсичным» для системы и эффективно выпадает из поиска.

Approve работает наоборот: рост confidence медленный (+0.05 за раз), но устойчивый — это защита от спам-голосования.

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
