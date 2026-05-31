# API Reference

> Документация повторяет содержимое OpenAPI (`/docs`, `/redoc`). Все endpoints
> возвращают JSON; ошибки — единый формат `ApiError`
> (см. [backend/app/api/common.py](../backend/app/api/common.py)).

База: `http://localhost:8000`.

## System

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Статус: openrouter, neo4j, persistence (postgres, neo4j, pgvector), embedding_provider |
| GET | `/metrics` | Prometheus-метрики |
| GET | `/docs` · `/redoc` | OpenAPI UI |

## Auth (JWT)

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/v1/auth/register` | `{email, password, name}` → 201 + access + refresh + user |
| POST | `/v1/auth/login` | `{email, password}` → access + refresh + user |
| POST | `/v1/auth/refresh` | `{refresh_token}` → новая пара |
| GET  | `/v1/auth/me` | Bearer access → user |
| POST | `/v1/auth/logout` | Bearer access → `{status: ok}` (stateless) |

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"u1@ex.com","password":"Demo12345"}' | jq -r .access_token)

curl -s http://localhost:8000/v1/auth/me -H "Authorization: Bearer $TOKEN"
```

## Scientific KB · мета

| Метод | Путь | Описание |
|-------|------|----------|
| GET  | `/v1/scientific/health` | Сводка корпуса + persistence modes + llm |
| GET  | `/v1/scientific/ontology` | Все типы сущностей/claims/relations/pipeline_steps/aliases |
| GET  | `/v1/scientific/hybrid-weights` | Текущие α/β/γ/δ/ε/ζ/η |
| POST | `/v1/scientific/demo/reset` | Пересоздать демо-корпус и стораджи |

## Publications

| Метод | Путь | Описание |
|-------|------|----------|
| POST   | `/v1/publications` | Создать из текста + опц. запуск pipeline |
| POST   | `/v1/publications/upload` | Загрузить PDF/TXT — pipeline автозапускается |
| GET    | `/v1/publications?research_field=&status=&year=&search=` | Список с фильтрами |
| GET    | `/v1/publications/{id}` | Карточка + chunks + claims + entities + jobs + citations |
| GET    | `/v1/publications/{id}/chunks` | Chunks конкретной публикации |
| PATCH  | `/v1/publications/{id}` | `{title?, abstract?, metadata?}` |
| DELETE | `/v1/publications/{id}` | Каскадно удаляет из PG + Neo4j |
| GET    | `/v1/authors` | Все авторы + организации |
| GET    | `/v1/citations` | Все цитирования |

## Pipeline

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/v1/pipeline/publications/{id}/run` | Запустить полный pipeline |
| POST | `/v1/pipeline/publications/{id}/steps/{step}/retry` | Перезапустить шаг |
| GET  | `/v1/pipeline/jobs?publication_id=` | Список jobs |
| GET  | `/v1/pipeline/jobs/{job_id}` | Job + steps + publication |

## Knowledge

| Метод | Путь | Описание |
|-------|------|----------|
| POST   | `/v1/knowledge/extract/{publication_id}` | Алиас на pipeline.run |
| GET    | `/v1/knowledge/entities?entity_type=&search=&limit=` | Реестр сущностей |
| GET    | `/v1/knowledge/entities/{id}` | Сущность + связанные claims/publications |
| GET    | `/v1/knowledge/claims?publication_id=&claim_type=&min_confidence=&min_evidence_strength=&limit=` | Claims с фильтрами |
| GET    | `/v1/knowledge/claims/{id}` | Claim + relations + related_claims |
| GET    | `/v1/knowledge/claims/{id}/evidence` | Evidence-block |
| GET    | `/v1/knowledge/relations?relation_type=&limit=` | ClaimRelations |
| PATCH  | `/v1/knowledge/claims/{id}` | Обновить любое поле claim |
| DELETE | `/v1/knowledge/claims/{id}` | Удалить claim + связанные relations |

## Activation + Search

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/v1/activation/keys` | Activation keys по вопросу + activated entities/claims/chunks |
| POST | `/v1/search/keyword` | Только keyword |
| POST | `/v1/search/semantic` | Семантический поиск через pgvector (in-process fallback) |
| POST | `/v1/search/graph` | Обход графа от активированных claims |
| POST | `/v1/search/hybrid` | 7-компонентная формула + `weights` + `activation` |

```bash
curl -X POST http://localhost:8000/v1/search/hybrid \
  -H 'Content-Type: application/json' \
  -d '{"query":"двоичный поиск в учебной базе","top_k":6}' \
  | jq '.items[0].score_breakdown'
```

## RAG

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/v1/rag/ask-with-evidence` | Ответ с reasoning trace, sources, limitations |
| GET  | `/v1/rag/answers?limit=` | История ответов |
| GET  | `/v1/rag/answers/{id}` | Один ответ |

```bash
curl -X POST http://localhost:8000/v1/rag/ask-with-evidence \
  -H 'Content-Type: application/json' \
  -d '{"question":"Как ускорить поиск в учебной таблице?","language":"ru","top_k":6}'
```

## Graph

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/v1/graph/scientific` | Полный граф (nodes + edges + summary) |
| GET | `/v1/graph/publication/{id}` | Подграф публикации |
| GET | `/v1/graph/entity/{id}?depth=` | Подграф вокруг сущности |
| GET | `/v1/graph/claim/{id}?depth=` | Подграф вокруг claim'а |

Типы рёбер: `CONTAINS_CLAIM`, `BELONGS_TO_FIELD`, `CITES`, `MENTIONS_ENTITY`,
`SUBJECT`, `OBJECT`, `EVALUATED_BY`, `supports`, `contradicts`, `limits`,
`extends`. У всех есть `weight`.

## Evaluation + Feedback + Review

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/v1/evaluation/rag-answer/{id}` | 8 метрик + автоматические feedback events |
| GET  | `/v1/evaluation/records?limit=` | История оценок |
| GET  | `/v1/evaluation/aggregate` | Средние по 8 метрикам |
| POST | `/v1/feedback/events` | `{event_type, target_id, signal, weight_delta, payload, apply_now}` |
| GET  | `/v1/feedback/events?limit=` | Лента событий |
| POST | `/v1/feedback/apply-pending` | Применить отложенные события |
| GET  | `/v1/review/queue` | Очередь ручной проверки |
| POST | `/v1/review/queue/{id}/resolve` | `{action: approve|reject|edit, note?}` |

8 метрик evaluation: `faithfulness`, `source_coverage`, `hallucination_rate`,
`answer_completeness`, `citation_correctness`, `limitation_honesty`,
`reasoning_trace_quality`, `contradiction_awareness`.

Подробное описание каждой метрики (что измеряет, формула, диапазон,
интерпретация, пример полного расчёта) — в [evaluation_metrics.md](evaluation_metrics.md).

## Export

| Метод | Путь | Описание |
|-------|------|----------|
| GET  | `/v1/export/graph.json` | Полный граф (~10 MB на демо-корпусе) |
| POST | `/v1/export/search.csv` | CSV с BOM + UTF-8, Excel-совместимо |

## Score breakdown (7 компонент)

Каждый `SearchHit` и `RagSource` несёт `score_breakdown` со всеми 7 компонентами:

```json
{
  "keyword": 0.12,
  "semantic": 0.43,
  "graph": 0.18,
  "activation": 1.0,
  "claim_confidence": 0.84,
  "evidence_strength": 0.81,
  "source_reliability": 0.78,
  "contradiction_risk": 0.05,
  "weights": {
    "alpha": 0.15, "beta": 0.35, "gamma": 0.20,
    "delta": 0.10, "epsilon": 0.15, "zeta": 0.05, "eta": 0.10
  }
}
```
