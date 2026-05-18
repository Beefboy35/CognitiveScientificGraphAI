# Сценарий защиты курсовой

> Пошаговый сценарий на 12–15 минут. Все шаги выполняются после
> `cp .env.example .env.dev && docker compose --env-file .env.dev --profile dev up -d`.

## 0. Подготовка (за 5 минут до доклада)

1. Поднять стек:
   ```bash
   cp .env.example .env.dev
   # При необходимости вписать OPENROUTER_API_KEY для LLM-извлечения
   docker-compose --env-file .env.dev --profile dev up -d
   ```
2. Дождаться `healthy`. Открыть в браузере:
   - http://localhost:5173 — фронтенд (Auth / Work / Lab / Graph / Manage);
   - http://localhost:8000/docs — Swagger UI;
   - http://localhost:7474 — Neo4j Browser (login: `neo4j` / см. `.env.dev`);
   - http://localhost:8080 — Adminer (PostgreSQL).

## 1. Постановка задачи (1 мин)

«Веб-приложение **Evidence-based Scientific Reasoning Engine** — интеллектуальная
база знаний для русскоязычных школьных публикаций. Преобразует текст в
проверяемые научные утверждения с ссылкой на источник, силой доказательства
и взвешенными связями. Реализовано на двух хранилищах: PostgreSQL с
расширением pgvector + Neo4j».

Открыть [TT.md](../TT.md), показать таблицу из §1.

## 2. Архитектура (2 мин)

Открыть [docs/architecture.md](architecture.md) → mermaid-диаграмму.
Прокомментировать:

- **Зачем pgvector**: векторы (384-dim sentence-transformer) хранятся прямо
  в `scikb_document_chunks.embedding` и `scikb_scientific_claims.embedding`
  с HNSW-индексом по cosine_ops. Отдельный Qdrant не нужен.
- **Зачем Neo4j**: многоходовые Cypher-запросы по weighted relations
  (`supports`, `contradicts`, `limits`, `extends`) проще, чем recursive CTE.
- **Graceful degradation**: каждый адаптер при первом обращении пытается
  подключиться, при ошибке логирует warning и переходит в `disabled`,
  pipeline продолжает работу с in-memory копией.

## 3. Health & persistence (30 сек)

```bash
curl http://localhost:8000/health | jq
```

Ожидаемо:
```json
{
  "openrouter": true,
  "neo4j": true,
  "persistence": {"postgres": true, "neo4j": true, "pgvector": true},
  "embedding_provider": "sentence-transformer"
}
```

```bash
curl http://localhost:8000/v1/scientific/health | jq
```

53 публикации · 583 chunks · 103 entities · 497 claims · ~67k relations ·
1898 activation keys · `vector_search_mode: pgvector` · `llm_active: true`.

## 4. Демо-корпус (1 мин)

В Adminer → таблица `scikb_publications` → видно 53 русскоязычные публикации
школьного уровня. В Neo4j Browser:

```cypher
MATCH (p:Publication) RETURN count(p);
MATCH (n) RETURN labels(n)[0] AS kind, count(*) ORDER BY count(*) DESC;
MATCH ()-[r]->() RETURN type(r) AS rel, count(r) ORDER BY count(r) DESC LIMIT 10;
```

Подсветить:

- темы корпуса: алгоритмы поиска/сортировки, базы данных для начинающих, графы, школьная математика, теория вероятностей;
- все 4 типа relation присутствуют: `SUPPORTS`, `CONTRADICTS`, `LIMITS`, `EXTENDS`.

## 5. Аутентификация JWT (1 мин)

На http://localhost:5173 — `AuthPage`. Зарегистрироваться:
`student@school.ru` / `Demo12345` / Иван Иванов.

После регистрации видно topbar с именем пользователя.

В Adminer показать таблицу `users`: bcrypt-хэш в `password_hash`, role=`user`.

В DevTools → Application → Local Storage → `kb.auth.access_token` и
`kb.auth.refresh_token` (JWT). При истечении access frontend автоматически
обновит токен через `/v1/auth/refresh`.

## 6. Загрузка PDF (1 мин)

Во вкладке **Работа** → Upload PDF → выбрать любую короткую публикацию.
Показать processing_job в списке. Дождаться статуса `ready`.

В Adminer → `scikb_processing_steps` отфильтровать по `job_id` — все 12
шагов со статусом `completed` и `attempts` (показывает retry/idempotency).
В `scikb_scientific_claims` появились новые строки с заполненной
колонкой `embedding` (pgvector).

## 7. Lab — 4 режима поиска (2 мин)

Перейти во вкладку **Лаб.**. В поисковом блоке поочерёдно нажать:
`keyword` → `semantic` → `graph` → `hybrid`.

Кликнуть на top-hit → справа открывается **ScoreBreakdown** с 7 компонентами
и формулой:

```
hybrid_score = α·keyword + β·semantic + γ·(graph + 0.5·activation)
             + δ·claim_confidence + ε·evidence_strength
             + ζ·source_reliability − η·contradiction_risk
```

Прокомментировать, как `contradiction_risk` снижает итоговый score для
противоречивых claims.

## 8. RAG со reasoning trace (2 мин)

В Lab задать вопрос «Как ускорить поиск в учебной таблице?».

Открывается **ReasoningTrace**:

1. ❓ Question
2. 🔑 Activation keys (chips)
3. 📦 Entities (`Двоичный поиск`, `Поиск по индексу`, ...)
4. 📌 Claims (карточки с evidence_strength bar)
5. 📄 Evidence (chunks с pages)
6. ⚖️ Contradiction disclosure (если есть claims с `contradiction_risk > 0.3`)
7. 💬 Grounded answer

Внизу показать **Limitations** — система честно перечисляет ограничения.

## 9. Honest refusal (30 сек)

Задать вопрос вне темы: «Кто выиграл чемпионат мира по футболу?».

Ожидаемо: `status: insufficient_evidence`. ReasoningTrace показывает
`question → activation_keys → insufficient_entities_or_claims → honest_refusal`.

«Система не придумывает ответ при недостатке доказательств».

## 10. Evaluation + Feedback Loop (1 мин)

Нажать **Evaluate**. Появляются 8 метрик с прогресс-барами: faithfulness,
source_coverage, hallucination_rate, answer_completeness, citation_correctness,
limitation_honesty, reasoning_trace_quality, contradiction_awareness.

Нажать **👎** — создаётся `feedback_event` с `signal=review_required`. Claim
попадает в очередь проверки.

Перейти во вкладку **Управление → Очередь** — увидеть этот элемент.
Нажать **Reject** — в Adminer `scikb_scientific_claims` у целевого claim
уменьшился `confidence_score`.

## 11. Manage — CRUD, история, экспорт (2 мин)

Во вкладке **Управление**:

- **Библиотека**: удалить публикацию → подтвердить в Adminer, что строка ушла из `scikb_publications` и каскадно из `scikb_document_chunks`/`scikb_scientific_claims`. Открыть Neo4j Browser → `MATCH (p:Publication {id: 'pub_...'}) RETURN p` — узла нет.
- **История**: показать прошлые RAG-ответы со confidence и source-count.
- **Экспорт**:
  - `Скачать граф (JSON)` → файл `graph_2026-05-17.json` ~10MB с nodes+edges+summary;
  - `Экспорт поиска (CSV)` → CSV с BOM, открывается в Excel со столбцами kind/id/score/title/page_start/page_end/text.

## 12. 3D-граф с resize (1 мин)

Вкладка **Граф**. Покрутить 3D-сцену (53 публикации, 497 claims, тысячи
связей). Отфильтровать по `Публикации` / `Факты` / `Понятия`.

Подвести курсор к нижнему краю канваса — появляется ручка-grip и
курсор меняется на `ns-resize`. Потянуть вниз — канвас растягивается.
Двойной клик по ручке — высота возвращается к 680px.

«Старого слайдера «Высота» больше нет — заменили на drag-by-edge resize».

## 13. Светлая ↔ тёмная тема (15 сек)

Кликнуть ☀/☾ в topbar — все компоненты меняют тему через CSS-переменные.
Кликнуть RU/EN — переключение языка во всех страницах.

## 14. Quality gate (30 сек)

```bash
cd backend
python -m pytest tests/test_demo_coverage.py -v
```

10/10 passed. Подчеркнуть: тест гарантирует, что весь корпус покрывает все
9 типов claims, все 7 типов сущностей и все 4 типа relation, у каждой
публикации есть author_ids и research_field.

## 15. Итоги (1 мин)

Открыть [README.md](../README.md) → таблицу соответствия ТЗ. Назвать:

- **Что реализовано**: 4 хранилища ужаты до 2 (PG+pgvector+Neo4j); JWT-auth с auto-refresh; LLM-извлечение через OpenRouter; гибридный поиск с 7 компонентами; reasoning trace; honest refusal; feedback loop с реальным применением деlta; CRUD + экспорт; React Router; resize канваса перетаскиванием.
- **Сознательные ограничения**: синтетический корпус, отсутствие WebSocket-прогресса, отсутствие async-очереди (Redis убрали).
- **Направления развития**: bootstrap состояния из PostgreSQL при старте, async-очередь pipeline, роли пользователей, обучение весов гибридной формулы под пользовательский фидбек.

---

## Чек-лист готовности к защите

- [x] Стек поднимается одной командой `docker-compose --env-file .env.dev --profile dev up -d`
- [x] Все 10 quality-gate тестов проходят (`pytest tests/test_demo_coverage.py`)
- [x] 53 русскоязычные публикации, понятные ученику 10–11 класса
- [x] PostgreSQL с pgvector — реальный source-of-truth, embeddings заполнены
- [x] Neo4j — реальный граф знаний с 4 типами relation
- [x] Гибридный поиск с 7-компонентным `score_breakdown`
- [x] RAG с reasoning trace и honest refusal
- [x] Feedback loop реально применяет deltas
- [x] JWT-аутентификация end-to-end (register → login → me → refresh → logout)
- [x] CRUD на публикациях и claims
- [x] Экспорт графа (JSON) и результатов поиска (CSV)
- [x] React Router маршрутизация
- [x] 3D-граф с resize по нижнему краю
- [x] Светлая и тёмная темы, RU/EN
- [x] Документация TT.md, architecture.md, data_model.md, api.md, defense_script.md
- [x] `.env.example` без секретов
