# Текущие user stories и функциональность приложения


Проверенные источники:

- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/api.ts`
- `frontend/src/features/auth/{AuthPage.tsx, model/authStore.ts, model/useAuthSession.ts, types.ts}`
- `frontend/src/features/workspace/WorkPage.tsx`
- `frontend/src/features/lab/LabPage.tsx`
- `frontend/src/features/graph/{GraphPage.tsx, BrainGraph3D.tsx, model/buildBrainGraph.ts}`
- `frontend/src/features/manage/ManagePage.tsx`
- `frontend/src/shared/api/scientificKb.ts`
- `frontend/src/shared/i18n/{dictionary.ts, labels.ts}`
- `frontend/src/shared/theme/useTheme.ts`
- `frontend/src/shared/ui/{ScoreBreakdown.tsx, ReasoningTrace.tsx, Primitives.tsx}`
- `frontend/src/styles/{tokens.css, base.css, auth.css, workspace.css, graph.css, lab.css, responsive.css}`
- `frontend/src/shared/types/scientific-kb.ts`
- `frontend/package.json`
- `backend/app/main.py`
- `backend/app/api/{auth.py, scientific_kb.py, common.py}`
- `backend/app/features/auth/{service.py, dependencies.py}`
- `backend/app/features/scientific_kb/*.py`
- `backend/app/features/scientific_kb/persistence/{manager.py, postgres_adapter.py, neo4j_adapter.py, pgvector_adapter.py}`
- `backend/alembic/versions/*.py`
- `backend/tests/test_demo_coverage.py`
- `docker-compose.yml`, `docker-compose.override.yml`, `.env.example`

## Краткое состояние

Приложение — рабочий прототип «Evidence-based Scientific Reasoning Engine»:

- React 19 / TypeScript 5.9 / Vite 7 SPA с маршрутизацией через `react-router-dom@7`;
- FastAPI backend (~60 endpoint'ов в 13 группах);
- **Neo4j-first архитектура**: Neo4j 5.26 — единственный источник истины графа знаний (Publication, ScientificClaim, ScientificEntity, DocumentChunk, ResearchField и все рёбра). Все read-endpoints (`/v1/graph/*`, `/v1/publications`, `/v1/knowledge/*`) читают из Neo4j через Cypher. PostgreSQL 15 + `pgvector` хранит operational данные (jobs, runs, RAG history, evaluations, feedback, review, users) и одну таблицу векторов `scikb_embeddings(target_kind, target_id, embedding vector(384))` со ссылками на id узлов Neo4j;
- LLM-извлечение через OpenRouter (по умолчанию `openai/gpt-4o-mini`), активно при наличии `OPENROUTER_API_KEY`;
- 12-шаговый pipeline обработки публикаций с retry/idempotency и persistence на каждом шаге;
- **Strict evidence-based extraction**: связи между claims создаются ТОЛЬКО при наличии evidence (text marker / opposite values / same claim_type cross-publication). Никаких искусственных связей «для покрытия онтологии»;
- **Density cap**: не более 20 связей на claim после bootstrap'а (`_prune_relations_per_claim`);
- **Orphan-prune**: после bootstrap'а из Neo4j удаляются все isolated nodes любого типа (`prune_orphan_nodes`), а из in-memory state — entities без mentions;
- JWT-аутентификация (access + refresh) с auto-refresh на 401 во frontend;
- **Компактный демо-корпус**: 20 русскоязычных школьных статей в 5 тематических кластерах (поиск, сортировка, таблицы, индексы, школьная математика);
- 3D-граф через `three` (InstancedMesh + instanced pulses, без fog) с resize канваса перетаскиванием нижнего края, фокус-режимом и селектором глубины BFS.

Qdrant и Redis удалены из проекта: векторный поиск перенесён в pgvector,
активация и кэш — в процесс приложения.

## Текущие демо-данные

При инициализации `ScientificKnowledgeBase` загружается `DEMO_CORPUS` из
[backend/app/features/scientific_kb/demo.py](backend/app/features/scientific_kb/demo.py).
Корпус — **20 русскоязычных статей в 5 тематических кластерах**:

1. **Поиск в массиве** (4 статьи) — линейный, двоичный, сравнение, ограничения;
2. **Сортировка** (4) — пузырьком, слиянием, сравнение, сортировка как предусловие двоичного поиска (bridge → кластер 1);
3. **Таблицы и ключи** (5) — таблица, PK, FK, WHERE, JOIN;
4. **Индексы** (4) — определение, ускорение SELECT, индекс на двоичном поиске (bridge → кластер 1), когда индекс мешает;
5. **Школьная математика** (3) — линейная функция, квадратное уравнение, производная.

Каждая статья имеет 3-5 секций (а не принудительные 11), один главный
`subject_entity` и явные cross-references на смежные статьи. В `seed.py`
зафиксировано 24 курируемых цитирования.

После старта backend в `/v1/scientific/health` отдаёт (реальный замер, dev-стек с LLM):

- 20 публикаций;
- 12 авторов, 6 организаций, 24 цитирования;
- 73 фрагмента;
- 15 канонических сущностей (orphan-сущности отфильтрованы);
- 68 научных утверждений с эмбеддингами в pgvector;
- **~190 связей между утверждениями** (avg degree ~5, max degree 10 — в разреженной зоне);
- режимы: `postgres_mode=real`, `graph_query_engine=neo4j`, `vector_search_mode=pgvector`,
  `llm_active=true` (при заданном `OPENROUTER_API_KEY`).

**Профиль качества графа** (после strict-refactor от мая 2026):
- Avg edges per claim ~5 (раньше было ~137 → 27× менее плотный, более содержательный);
- Каждая связь имеет `created_by ∈ {rule, llm, manual}` для аудита;
- Связь создаётся только при evidence: cross-publication same `claim_type` (SUPPORTS), explicit text marker «развивает / в отличие от / только если» (EXTENDS / CONTRADICTS / LIMITS), opposite metric values (CONTRADICTS).

В `/v1/graph/scientific` граф содержит только узлы, имеющие хотя бы одно
ребро. У каждого ребра есть `weight`, у claim-relation-рёбер дополнительно
`confidence_score` и `evidence_strength`.

## Реально доступные роли

### Зарегистрированный пользователь через UI

После регистрации или входа (`/v1/auth/register` или `/v1/auth/login`) пользователь
получает JWT-токены, которые `apiFetch` автоматически добавляет в заголовок
`Authorization` каждого запроса. При истечении access-токена `apiFetch`
прозрачно вызывает `/v1/auth/refresh` и повторяет оригинальный запрос.

Пользователь может:

- зарегистрироваться и войти с email + паролем (минимум 8 символов, буквы и цифры);
- работать с материалами (вкладка `Работа` `/`);
- использовать расширенный поиск и RAG (вкладка `Лаб.` `/lab`);
- смотреть 3D-граф (вкладка `Граф` `/graph`);
- управлять данными (вкладка `Управление` `/manage`): удалять публикации, обрабатывать очередь проверки, видеть историю вопросов, экспортировать граф в JSON и результаты поиска в CSV;
- переключать тему светлая ↔ тёмная (☀ / ☾ в topbar);
- переключать язык RU ↔ EN;
- выйти из системы (токены удаляются из localStorage).

### API-клиент

Все 53 endpoint'а доступны без авторизации, кроме `/v1/auth/me` и
`/v1/auth/logout` (требуют Bearer access token). Защита остальных
scientific_kb endpoint'ов JWT-зависимостью — потенциальное расширение.

### Администратор

Отдельной admin-роли в `users.role` нет — `role` хранит `user` для всех
зарегистрированных. CRUD-операции из вкладки `Управление` доступны
любому залогиненному пользователю.

## Frontend: общая структура

Точка входа [frontend/src/main.tsx](frontend/src/main.tsx) оборачивает `App` в
`<BrowserRouter>` из `react-router-dom`.

[frontend/src/App.tsx](frontend/src/App.tsx) содержит:

- хук `useAuthSession()` — при mount вызывает `GET /v1/auth/me`, при 401 пробует refresh;
- хук `useTheme()` — управление светлой/тёмной темой через CSS-переменные;
- состояние `locale: 'ru' | 'en'`, поисковый запрос, вопрос, выбранную публикацию, jobs, graph и другие операционные значения.

Маршрутизация через `<Routes>`:

| **Путь**     | **Страница**       | **Компонент**                                  |
|--------------|--------------------|------------------------------------------------|
| `/`          | Работа             | `WorkPage`                                     |
| `/lab`       | Лаб.               | `LabPage`                                      |
| `/graph`     | Граф               | `GraphPage` + `BrainGraph3D`                   |
| `/manage`    | Управление         | `ManagePage`                                   |

Topbar (всегда виден после логина): кнопка `KB` (на `/`), `NavLink`-вкладки,
кнопка темы, переключатель RU/EN, кнопка обновления данных, кнопка выхода.

Если пользователь не залогинен, рендерится `AuthPage` с переключением
login/register.

После структурного рефакторинга frontend разложен по зонам ответственности:

- `App.tsx` — состояние, эффекты, роутинг;
- `features/auth/` — AuthPage + authStore + useAuthSession + types;
- `features/workspace/WorkPage.tsx` — рабочий экран;
- `features/lab/LabPage.tsx` — расширенный поиск, ReasoningTrace, ScoreBreakdown, очередь проверки;
- `features/graph/` — GraphPage + BrainGraph3D + buildBrainGraph;
- `features/manage/ManagePage.tsx` — библиотека публикаций, review queue, история вопросов, экспорт;
- `shared/api/scientificKb.ts` — клиент scientific_kb;
- `shared/i18n/*` — словарь и labels;
- `shared/theme/useTheme.ts` — light/dark;
- `shared/ui/{ScoreBreakdown.tsx, ReasoningTrace.tsx, Primitives.tsx}`;
- `shared/types/scientific-kb.ts`;
- `styles/{tokens.css, base.css, auth.css, workspace.css, graph.css, lab.css, responsive.css}`.

## Frontend user stories

### US-FE-001. Авторизация по email/паролю с JWT

Как пользователь, я хочу зарегистрироваться или войти, чтобы работать с приложением.

Реализовано:

- `AuthPage` с режимами `login` и `register`;
- валидация имени, email, длины пароля и соответствия `password === confirmPassword`;
- `loginUser` / `registerUser` вызывают `POST /v1/auth/login` или `/register`;
- JWT access + refresh сохраняются в `localStorage`;
- `useAuthSession()` при mount пытается восстановить сессию через `/v1/auth/me`;
- автоматический refresh-интерсептор в `apiFetch`: при 401 пробует обновить токен и повторяет запрос ровно один раз;
- кнопка `Выйти` стирает токены и редиректит на `/`.

### US-FE-002. Маршрутизация страниц

Как пользователь, я хочу переходить между разделами по URL.

Реализовано:

- `BrowserRouter` оборачивает `App`;
- четыре маршрута: `/`, `/lab`, `/graph`, `/manage`;
- `NavLink` в topbar подсвечивает активную вкладку;
- кнопка `KB` (логотип) переходит на `/`.

### US-FE-003. Светлая и тёмная темы

Как пользователь, я хочу переключать тему интерфейса.

Реализовано:

- `useTheme()` хранит выбор в `localStorage` ключом `kb.theme`;
- кнопка ☀/☾ в topbar переключает CSS-переменные через атрибут `data-theme` на `<html>`;
- все компоненты используют CSS-переменные из [tokens.css](frontend/src/styles/tokens.css).

### US-FE-004. Переключение языка

Как пользователь, я хочу переключать интерфейс RU ↔ EN.

Реализовано:

- состояние `locale: 'ru' | 'en'` в `App.tsx`;
- кнопка `RU` / `EN`;
- словарь `i18n` в [frontend/src/shared/i18n/dictionary.ts](frontend/src/shared/i18n/dictionary.ts);
- демо-вопрос и демо-поиск меняются при смене языка, если пользователь их не редактировал вручную;
- `document.documentElement.lang` обновляется.

### US-FE-005. Просмотр сводки базы

Как пользователь, я хочу видеть размер базы и статусы хранилищ.

Реализовано:

- frontend вызывает `/v1/scientific/health` и `/v1/auth/me`;
- показываются: число публикаций, фрагментов, сущностей, claims, relations, activation keys;
- статусы стораджей: `postgres_mode`, `graph_mode`, `vector_search_mode`, `llm_provider`, `llm_active`.

### US-FE-006. Выбор материала

Как пользователь, я хочу выбрать публикацию из списка.

Реализовано:

- список публикаций загружается через `/v1/publications`;
- выбранная публикация хранится в `selectedPublicationId`;
- при выборе загружаются фрагменты через `/v1/publications/{publication_id}/chunks`;
- factы фильтруются на frontend по `publication_id`.

### US-FE-007. Добавление текстового материала

Как пользователь, я хочу вставить текст и отправить на разбор.

Реализовано:

- textarea + поле названия;
- проверка минимальной длины текста 40 символов;
- `POST /v1/publications` с `run_pipeline: true`;
- сразу после успеха выбирается новая публикация и обновляются данные.

### US-FE-008. Загрузка файла

Как пользователь, я хочу загрузить PDF/TXT.

Реализовано:

- file input с `accept=".pdf,.txt,.md"`;
- `FormData` в `POST /v1/publications/upload`;
- backend извлекает текст через `pypdf` или fallback-декодирование `utf-8/cp1251/latin-1`;
- если LLM-извлечение включено (`EXTRACTION_MODE=hybrid` или `llm`), для каждого чанка вызывается OpenRouter и результаты сливаются с rule-based;
- после загрузки публикация выбирается, данные обновляются.

### US-FE-009. Восстановление демо-данных

Как пользователь, я хочу вернуть демо-состояние.

Реализовано:

- кнопка `Демо`;
- `POST /v1/scientific/demo/reset`;
- сбрасываются поисковые результаты, RAG-ответ и оценка;
- toast о восстановлении.

### US-FE-010. Гибридный поиск

Как пользователь, я хочу найти релевантные фрагменты и факты.

Реализовано:

- поле поискового запроса;
- `POST /v1/search/hybrid` с `{ query, top_k }`;
- в ответе `items` с `score_breakdown` и `weights`;
- отображаются тип хита, итоговый score и текст;
- вкладка `Лаб.` дополнительно показывает stacked-bar-chart по 7 компонентам через `ScoreBreakdown.tsx`.

### US-FE-011. Расширенный поиск во вкладке Lab

Как пользователь, я хочу сравнить четыре режима поиска.

Реализовано:

- `LabPage` имеет вкладки `keyword` / `semantic` / `graph` / `hybrid`;
- каждый вызывает соответствующий endpoint `/v1/search/{mode}`;
- семантический режим автоматически использует pgvector через backend, если он активен;
- при выборе hit показывается ScoreBreakdown с весами α/β/γ/δ/ε/ζ/η.

### US-FE-012. Вопрос с reasoning trace

Как пользователь, я хочу задать вопрос и видеть всю цепочку вывода.

Реализовано:

- `POST /v1/rag/ask-with-evidence` с `{ question, top_k, language }`;
- ответ содержит `answer`, `sources`, `used_claims`, `used_entities`, `reasoning_trace`, `limitations`;
- `ReasoningTrace.tsx` отображает 7 этапов: question → activation keys → entities → claims → evidence → contradiction_disclosure | evidence_aggregation → grounded_answer;
- если `status: insufficient_evidence` — выводится честный отказ и причины;
- ответ можно оценить через `evaluateRagAnswer` (`POST /v1/evaluation/rag-answer/{id}`), который возвращает 8 метрик.

### US-FE-013. Просмотр фактов и фрагментов выбранной публикации

Реализовано:

- блок `Для занятия` показывает до 6 утверждений с типом, evidence_strength и confidence_score;
- блок `Фрагменты` показывает до 4 chunks с указанием секции и страниц.

### US-FE-014. Просмотр шагов pipeline

Реализовано:

- блок `Готовность` показывает шаги последнего job в памяти frontend;
- backend endpoint `GET /v1/pipeline/jobs?publication_id=...` доступен для получения всех jobs.

### US-FE-015. 3D-граф (оптимизированный)

Реализовано в `BrainGraph3D.tsx` (после rewrite):

- Three.js scene с тёмным фоном, **без fog** (узлы не растворяются при отдалении);
- **InstancedMesh для узлов** — один draw call для всех 100+ узлов;
- **LineSegments для рёбер** — один buffer для всех рёбер вместо N×TubeGeometry;
- **Цветовой градиент source→target** на рёбрах: source-конец насыщенный, target-конец темнее → визуальное направление;
- **InstancedMesh для импульсов** (instanced pulses): анимированные светящиеся точки движутся source→target, показывают направление в динамике;
- `OrbitControls` с `minDistance=80, maxDistance=4500` — можно сильно отдалить колесом;
- Heavy-mode при >400 узлах или >1500 рёбрах — выключаются antialias/autoRotate/pulses;
- `ResizeObserver` + единый `requestAnimationFrame`;
- Throttled raycaster (60ms) для cursor-hover;
- Imperative handle `centerOn(nodeId)` / `resetCamera()` — управление камерой из родителя без пересоздания сцены.

### US-FE-016. Фильтр графа по типам узлов

Реализовано:

- фильтры `Все`, `Публикации`, `Факты`, `Понятия`;
- состояние `graphFilter`;
- `buildBrainGraph()` строит видимые узлы и рёбра по фильтру.

### US-FE-017. Лимит узлов в графе (top-N)

Реализовано:

- дропдаун `Узлов` в тулбаре: `100 / 200 / 500 / 1000 / 2000 / Все`;
- по умолчанию 500;
- логика отбора — top-N по степени (самые связные узлы остаются), затем фильтруются их рёбра;
- дизейблится в режиме фокуса (там подграф ограничен иначе).

### US-FE-018. Фокус-режим: подграф связанных узлов

Как пользователь, я хочу кликнуть по узлу и увидеть только связанные с ним.

Реализовано:

- клик по узлу → запускается BFS по узлам, достижимым из выбранного;
- сегментный переключатель направления: `↔ всё связанное` (default) / `→ исходящие` / `← входящие` — граф ориентированный, BFS уважает направление;
- селектор глубины: `1 — соседи / 2 — окружение / 3 — расширенное / ∞ — всё`. Default 2, потому что на плотных графах ∞ возвращает почти всё;
- баннер «Режим фокуса · Показано N узлов из M» + кнопка `Весь граф ←` для выхода;
- при клике по узлу ВНУТРИ подграфа фокус переключается на новый узел.

### US-FE-019. Размах графа

Реализовано:

- slider `Размах` от 160 до 620, шаг 20;
- состояние `graphSpacing` влияет на позиционирование узлов и генерацию neural fibers.

### US-FE-020. Изменение высоты канваса перетаскиванием края

Как пользователь, я хочу растягивать канвас, потянув за его нижний край.

Реализовано:

- зона захвата 24px вдоль нижнего края с явным `pointer-events: auto`;
- видимая ручка-grip с подписью «↕ изменить высоту» при hover;
- `onMouseDown` запускает drag, document-уровневые `mousemove/mouseup` обновляют `canvasHeight`;
- допустимый диапазон 360–2200px;
- `dblclick` сбрасывает высоту на 680px;
- значение передаётся в CSS custom property `--graph-canvas-height`.

### US-FE-021. Тулбар графа

Реализовано:

- `Центрировать` — фокусирует камеру на выбранном узле через `BrainGraph3DHandle.centerOn`;
- `Сбросить вид` — `resetCamera()`;
- `Связи: вкл/выкл` — переключает рёбра и импульсы;
- `Панель: вкл/выкл` — скрывает правую панель (канвас занимает все 12 колонок grid);
- `Как управлять` — раскрывает help-панель с горячими клавишами.

### US-FE-022. Pipeline / provenance в правой панели

При клике по узлу подгружается «откуда взято» в зависимости от типа узла:

- **Claim** → `📄 Публикация → ✂️ Фрагмент (с цитатой) → 📌 Утверждение → 🏷️ Сущности → 🧠 Pipeline 12 шагов`;
- **Publication** → `📄 Сама публикация → 📊 Артефакты (N чанков/claims/entities) → 🧠 Pipeline`;
- **Entity** → `🏷️ Сущность с aliases → 📄 Публикации (топ-5) → 📌 Утверждения (топ-5)`.

Реализовано в `NodePipeline.tsx`. Использует endpoint'ы `getPublication`,
`getClaimEvidence`, `getEntity`. Поддерживает `cancelled`-флаг для быстрых
переключений между узлами.

### US-FE-023. Связи на простом языке (RelationsBlock)

Реализовано в `RelationsBlock.tsx`:

- группировка связей по типу: `Подтверждения / Развития / Ограничения / Противоречия`;
- цветные chip'ы (зелёный/синий/оранжевый/красный);
- словесная сила связи: `сильная` (≥70%) / `средняя` (40-70%) / `слабая` (<40%);
- стрелка направления: `→` исходящая, `←` входящая;
- человекочитаемые подписи: «это утверждение **подтверждает** другое», «**развивается в** другое»;
- help-tooltips для каждого типа связи и для силы;
- свёртывание длинных списков (показ топ-3 + кнопка «Показать ещё N»);
- контекст связи (если есть) — italic-цитата под пунктом.

### US-FE-024. Технические поля скрыты в «Дополнительно»

В правой панели свойств узла под раскрывающейся секцией:

- ID узла;
- raw kind (тип из Neo4j);
- publication_id;
- research_field;
- claim_type;
- status.

Это уберегает обычного пользователя от технического шума, но даёт доступ
к raw-данным разработчику.

### US-FE-022. Управление данными во вкладке Manage

Реализовано в `ManagePage.tsx`:

- вкладка `Библиотека` — список публикаций с кнопкой удаления (`DELETE /v1/publications/{id}`);
- вкладка `Очередь` (review queue) — `GET /v1/review/queue` и `POST /v1/review/queue/{id}/resolve {action: approve|reject}`;
- вкладка `История` — `GET /v1/rag/answers` со списком прошлых вопросов, ответов, confidence и числа источников;
- вкладка `Экспорт` — кнопки скачать `graph.json` через `GET /v1/export/graph.json` и `search.csv` через `POST /v1/export/search.csv` (CSV с BOM, открывается в Excel).

### US-FE-023. Адаптивность

Реализовано в [App.css](frontend/src/App.css):

- media queries для `1160px`, `860px`, `680px`, `420px`;
- перестройка layout в одну колонку;
- сетки карточек сжимаются;
- toolbar графа переносится.

## Backend API

Полный набор endpoints. Все запросы возвращают JSON; ошибки имеют единый
формат `ApiError` (см. [backend/app/api/common.py](backend/app/api/common.py)).

### Системные

| Метод | Путь | Описание |
|---|---|---|
| GET | `/health` | Статус: openrouter, neo4j, persistence (postgres, neo4j, pgvector), embedding_provider |
| GET | `/metrics` | Prometheus-метрики |
| GET | `/docs`, `/redoc` | OpenAPI UI |

### Auth (JWT)

| Метод | Путь | Описание |
|---|---|---|
| POST | `/v1/auth/register` | `{email, password, name}` → access + refresh + user |
| POST | `/v1/auth/login` | `{email, password}` → access + refresh + user |
| POST | `/v1/auth/refresh` | `{refresh_token}` → новая пара |
| GET  | `/v1/auth/me` | Bearer access → user |
| POST | `/v1/auth/logout` | Bearer access → `{status: ok}` (stateless) |

### Scientific KB · мета

| Метод | Путь | Описание |
|---|---|---|
| GET  | `/v1/scientific/health` | Сводка корпуса + persistence modes + llm |
| GET  | `/v1/scientific/ontology` | Все типы сущностей, claims, relations, pipeline_steps, aliases |
| GET  | `/v1/scientific/hybrid-weights` | Текущие α/β/γ/δ/ε/ζ/η |
| POST | `/v1/scientific/demo/reset` | Пересоздать демо-корпус |

### Publications

| Метод | Путь | Описание |
|---|---|---|
| POST   | `/v1/publications` | Создать из текста (+ опц. запуск pipeline) |
| POST   | `/v1/publications/upload` | Загрузить PDF/TXT |
| GET    | `/v1/publications?research_field=&status=&year=&search=` | Список с фильтрами |
| GET    | `/v1/publications/{id}` | Карточка + chunks + claims + entities + jobs + citations |
| GET    | `/v1/publications/{id}/chunks` | Chunks публикации |
| PATCH  | `/v1/publications/{id}` | Обновить title/abstract/metadata |
| DELETE | `/v1/publications/{id}` | Каскадно удалить из PG + Neo4j |
| GET    | `/v1/authors` | Все авторы + организации |
| GET    | `/v1/citations` | Все цитирования |

### Pipeline

| Метод | Путь | Описание |
|---|---|---|
| POST | `/v1/pipeline/publications/{id}/run` | Запустить полный pipeline (12 шагов) |
| POST | `/v1/pipeline/publications/{id}/steps/{step}/retry` | Перезапуск одного шага |
| GET  | `/v1/pipeline/jobs?publication_id=` | Список jobs |
| GET  | `/v1/pipeline/jobs/{job_id}` | Job + steps + publication |

### Knowledge

| Метод | Путь | Описание |
|---|---|---|
| POST   | `/v1/knowledge/extract/{publication_id}` | Алиас на pipeline.run |
| GET    | `/v1/knowledge/entities?entity_type=&search=&limit=` | Реестр сущностей |
| GET    | `/v1/knowledge/entities/{id}` | Сущность + claims + publications |
| GET    | `/v1/knowledge/claims?publication_id=&claim_type=&min_confidence=&min_evidence_strength=&limit=` | Claims с фильтрами |
| GET    | `/v1/knowledge/claims/{id}` | Claim + relations + related_claims |
| GET    | `/v1/knowledge/claims/{id}/evidence` | Evidence block (claim + chunk + publication) |
| GET    | `/v1/knowledge/claims/{id}/usage` | **UserFacingKnowledge**: `can_be_used_in`, `retrieval_priority`, `explanation_for_user`, `pipeline_trace` |
| GET    | `/v1/knowledge/relations?relation_type=&limit=` | Все ClaimRelations |
| PATCH  | `/v1/knowledge/claims/{id}` | Обновить любое поле claim |
| DELETE | `/v1/knowledge/claims/{id}` | Удалить claim + связанные relations |

### Activation + Search

| Метод | Путь | Описание |
|---|---|---|
| POST | `/v1/activation/keys` | Activation keys по вопросу + activated entities/claims/chunks |
| POST | `/v1/search/keyword` | Keyword-режим |
| POST | `/v1/search/semantic` | Semantic через pgvector (с in-process fallback) |
| POST | `/v1/search/graph` | Обход графа от активированных claims |
| POST | `/v1/search/hybrid` | 7-компонентная формула + `weights` + `activation` |

### RAG

| Метод | Путь | Описание |
|---|---|---|
| POST | `/v1/rag/ask-with-evidence` | Ответ с reasoning trace, sources, limitations |
| GET  | `/v1/rag/answers?limit=` | История ответов |
| GET  | `/v1/rag/answers/{id}` | Один ответ |

### Graph

| Метод | Путь | Описание |
|---|---|---|
| GET | `/v1/graph/scientific` | Полный граф |
| GET | `/v1/graph/publication/{id}` | Подграф публикации |
| GET | `/v1/graph/entity/{id}?depth=` | Подграф вокруг сущности |
| GET | `/v1/graph/claim/{id}?depth=` | Подграф вокруг claim'а |

Типы рёбер: `CONTAINS_CLAIM`, `BELONGS_TO_FIELD`, `CITES`, `MENTIONS_ENTITY`,
`SUBJECT`, `OBJECT`, `EVALUATED_BY`, `supports`, `contradicts`, `limits`,
`extends`. Все имеют `weight`.

### Evaluation + Feedback + Review

| Метод | Путь | Описание |
|---|---|---|
| POST | `/v1/evaluation/rag-answer/{id}` | 8 метрик + автоматические feedback events |
| GET  | `/v1/evaluation/records?limit=` | История оценок |
| GET  | `/v1/evaluation/aggregate` | Средние по 8 метрикам |
| POST | `/v1/feedback/events` | `{event_type, target_id, signal, weight_delta, payload, apply_now}` |
| GET  | `/v1/feedback/events?limit=` | Лента событий |
| POST | `/v1/feedback/apply-pending` | Применить отложенные события |
| GET  | `/v1/review/queue` | Очередь ручной проверки |
| POST | `/v1/review/queue/{id}/resolve` | `{action: approve|reject|edit, note}` |

### Export

| Метод | Путь | Описание |
|---|---|---|
| GET  | `/v1/export/graph.json` | Полный граф (~10 MB на демо-корпусе) |
| POST | `/v1/export/search.csv` | CSV с BOM + UTF-8 |

## Backend: модель данных

`ScientificKnowledgeBase` ([service.py](backend/app/features/scientific_kb/service.py))
держит in-memory копию состояния и одновременно пишет изменения в
**Neo4j** (единый источник истины для графа) и **PostgreSQL** (операционные
данные + embeddings) через `PersistenceManager`. In-memory — это горячий
кэш + fallback при недоступности БД; при cache miss read-операции достают
данные из Neo4j через Cypher batch-fetch (`fetch_chunks_by_ids` и т.д.).

### PostgreSQL: 11 операционных таблиц `scikb_*` + `users` + `scikb_embeddings`

После Neo4j-first рефакторинга PostgreSQL содержит только **операционные**
данные. Графовые таблицы (publications, document_chunks, scientific_claims,
claim_relations, scientific_entities, entity_aliases/mentions, и т.д.)
удалены — их роль выполняет Neo4j.

Создаются миграциями [backend/alembic/versions/](backend/alembic/versions/):

- `7e9424fcd3ae_initial_schema.py` — таблица `users` и базовые системные таблицы;
- `2026051502_scientific_kb_schema.py` — исходные 22 `scikb_*` таблицы (исторически, до рефакторинга);
- `2026051603_pgvector_embeddings.py` — `CREATE EXTENSION vector`, HNSW-индексы;
- **`2026051704_neo4j_first.py`** — DROP'ает 13+ графовых таблиц и создаёт
  единую `scikb_embeddings(target_kind, target_id, model, embedding vector(384))`
  с HNSW по cosine_ops; `target_id` ссылается на id узла Neo4j.

Текущий набор PG-таблиц (11 операционных): `scikb_processing_jobs`,
`scikb_processing_steps`, `scikb_extraction_runs`, `scikb_user_queries`,
`scikb_rag_answers`, `scikb_rag_answer_sources`, `scikb_retrieval_experiments`,
`scikb_answer_evaluations`, `scikb_feedback_events`, `scikb_review_queue`,
`scikb_embeddings`. Плюс системная `users`.

Ограничения на типы (`claim_type` ∈ 9 значений, `relation_type` ∈ 4 значений,
`status` ∈ 12 значений) перенесены в Pydantic-схемы API и `Literal[...]`
типы dataclass'ов ([models.py](backend/app/features/scientific_kb/models.py)).

### Neo4j: единый источник истины для графа

Уникальные constraint'ы на `id` для узлов создаются автоматически на старте
([neo4j_adapter.py](backend/app/features/scientific_kb/persistence/neo4j_adapter.py)).

Типы узлов: `Publication`, `ScientificClaim`, `ScientificEntity`,
`DocumentChunk`, `ResearchField`. Авторы и организации хранятся как поля
Publication (массивы).

**`ResearchField` — особый узел**: это **отдельный тип** в Neo4j, а не
запись в реестре `ScientificEntity`. Используется как тематическая
группировка публикаций (12 школьных областей из
[ontology.py](backend/app/features/scientific_kb/ontology.py): «Алгоритмы
и структуры данных», «Базы данных для начинающих», «Школьная математика»
и т.д.). Идентификатор узла — **сама строка-название** (`id = name`),
а не stable_id-хеш. Создаётся при `upsert_publication` через
`MERGE (f:ResearchField {name})` на основе `publication.metadata.research_field`.
Endpoint `/v1/knowledge/entities/{id}` для `ResearchField` не работает
(возвращает 404) — для деталей области нужен
`GET /v1/publications?research_field=<name>`. Подробнее: [data_model.md §4.1](docs/data_model.md).

Рёбра: `CONTAINS_CHUNK`, `CONTAINS_CLAIM`, `BELONGS_TO_FIELD`, `CITES`,
`MENTIONS_ENTITY`, `EVALUATED_BY`, и взвешенные claim↔claim связи
`SUPPORTS`, `CONTRADICTS`, `LIMITS`, `EXTENDS` с атрибутами `weight`,
`confidence_score`, `evidence_strength`, `source_reliability`.

**Stable content-hash IDs**: все id формата `pub_<16hex>` / `chunk_<16hex>` /
`claim_<16hex>` / `ent_<16hex>` / `rel_<16hex>` детерминированно
генерируются через `_stable_id(prefix, *parts)` ([utils.py](backend/app/features/scientific_kb/utils.py))
как SHA256-хеш контентных полей. Cypher MERGE по этим id идемпотентен:
повторные bootstrap'ы не создают дубликатов.

### Cypher batch-fetch (cache-miss fallback)

[Neo4jAdapter](backend/app/features/scientific_kb/persistence/neo4j_adapter.py)
содержит batch-fetch методы для cache-miss path'а:

- `fetch_chunks_by_ids(ids) -> dict[id, payload]`
- `fetch_claims_by_ids(ids) -> dict[id, payload]`
- `fetch_entities_by_ids(ids) -> dict[id, payload]`
- `fetch_publications_by_ids(ids) -> dict[id, payload]`

Это критично для семантического поиска через pgvector: HNSW возвращает
`target_id`, который при miss in-memory достаётся через Cypher одним
запросом.

### pgvector: единая таблица embeddings со ссылкой на Neo4j-id

`PgVectorAdapter` ([pgvector_adapter.py](backend/app/features/scientific_kb/persistence/pgvector_adapter.py))
реализует:

- `upsert_chunk_embeddings(pairs)` / `upsert_claim_embeddings(pairs)` — INSERT с CAST к `vector`, `ON CONFLICT (target_kind, target_id) DO UPDATE`;
- `search_similar_chunks(vec, top_k)` / `search_similar_claims(vec, top_k)` — `WHERE target_kind = ... ORDER BY embedding <=> :vec LIMIT :k`;
- `find_near_duplicate_claim(vec, threshold=0.93)` — используется pipeline'ом для дедупликации claims на upload: при близком существующем claim создаётся `SUPPORTS`-связь вместо дубликата.

### In-memory структуры

```text
ScientificKnowledgeBase (in-memory)
├── publications        ← теневая копия PG.scikb_publications
├── chunks              ← теневая копия PG.scikb_document_chunks
├── entities            ← теневая копия Neo4j ScientificEntity
├── claims              ← теневая копия Neo4j ScientificClaim
├── relations           ← теневая копия Neo4j claim-relations
├── jobs/steps          ← теневая копия PG.scikb_processing_*
├── rag_answers         ← теневая копия PG.scikb_rag_answers
├── evaluations/...     ← теневая копия PG.scikb_answer_evaluations
├── feedback_events     ← теневая копия PG.scikb_feedback_events
├── review_queue        ← теневая копия PG.scikb_human_review_queue
├── _entity_by_canonical (perf-cache, нужен)
├── activation_index    (inverted index token→claims, нужен)
└── persistence         PersistenceManager (PG + Neo4j + pgvector)
```

**Честная оговорка про in-memory.** Эти dict'ы — теневые копии БД. Источник
истины:

- Для графа (узлы Publication / ScientificClaim / ScientificEntity / ResearchField и рёбра CONTAINS_CLAIM / SUPPORTS / CONTRADICTS / LIMITS / EXTENDS / CITES / MENTIONS_ENTITY / EVALUATED_BY) — **Neo4j**. `/v1/graph/*` endpoints читают через Cypher; in-memory остаётся как fallback.
- Для всего операционного (jobs/steps/runs/rag/eval/feedback/review) и для embeddings — **PostgreSQL с pgvector**.

Сейчас `search.py`, `rag.py`, `extraction.py`, `feedback_service.py`
читают и мутируют в in-memory dict'ах, а изменения **затем** мирорятся в БД.
Это технический долг — `search_keyword`/`search_semantic`/`rag` могли бы
читать прямо из PG. Из-за этого:

- IDs нестабильны между рестартами (`uuid.uuid4()`);
- демо-корпус перетирает Neo4j на старте (`MATCH (n) DETACH DELETE n` в bootstrap_persistence) — иначе накапливаются дубликаты от старых runs;
- пользовательские публикации, добавленные через `/v1/publications`, при рестарте теряются.

## Backend: декомпозиция scientific_kb

```
backend/app/features/scientific_kb/
├── service.py            # ScientificKnowledgeBase агрегат + summary
├── pipeline.py           # 12 шагов с retry/idempotency
├── extraction.py         # entity + claim extraction (rule-based + LLM-merge)
├── llm_extractor.py      # OpenRouter client (sanitisation + cache + retry)
├── search.py             # keyword / semantic / graph / hybrid
├── rag.py                # ask_with_evidence + evaluate + refusal logic
├── feedback_service.py   # apply_feedback_event + review queue
├── graph.py              # graph_all / graph_for_*
├── embedding_service.py  # sentence-transformer + детерминированный fallback
├── ontology.py           # русскоязычная школьная онтология (200+ канонических имён)
├── seed.py               # 12 авторов, 6 организаций, 24 курируемых цитирования
├── demo.py               # 20 русских школьных статей в 5 тематических кластерах
├── models.py             # dataclass-модели (ClaimRelation.created_by для аудита)
├── orm.py                # 11 операционных SQLAlchemy 2 таблиц scikb_*
├── serialization.py      # dump()
├── singleton.py          # глобальный scientific_kb + bootstrap_persistence
├── utils.py              # deterministic_embedding, токенизация, сходство
└── persistence/
    ├── manager.py        # PersistenceManager (fan-out)
    ├── postgres_adapter.py
    ├── neo4j_adapter.py
    └── pgvector_adapter.py
```

## Backend: pipeline

Шаги (`PIPELINE_STEPS` в [ontology.py](backend/app/features/scientific_kb/ontology.py)):

1. `upload`
2. `text_extraction`
3. `section_detection` (русские и английские заголовки секций)
4. `semantic_chunking`
5. `embeddings`
6. `entity_extraction`
7. `entity_normalization`
8. `claim_extraction_v2`
9. `claim_relations`
10. `weighted_graph`
11. `activation_index`
12. `ready`

Каждый шаг оборачивается в `_run_step` с retry (до 2 попыток с backoff
`[0, 0.5, 1.5]` секунд). Статусы пишутся в `scikb_processing_steps`.
`extraction_run_id` (UUID) фиксируется на каждом claim для версионирования.

Шаг `claim_extraction_v2` при `EXTRACTION_MODE=hybrid` или `llm` дополнительно
вызывает `LLMExtractor`: отправляет каждый chunk в OpenRouter, парсит JSON-ответ
(entities + claims + relations), кэширует in-process по
`(model, prompt_version, sha256(text))`. Если LLM упал или вернул невалидный
JSON — rule-based извлечение остаётся safety-net'ом.

## Backend: извлечение знаний (strict)

[extraction.py](backend/app/features/scientific_kb/extraction.py):

- детекция claim-маркеров для девяти типов (русские + английские regex), расширенные patterns для учебных конструкций («работает только если», «мы определяем», «для массива длины N»);
- определение subject/object по позиции упомянутых сущностей;
- расчёт `confidence_score` (численные значения, число сущностей, модальные слова);
- расчёт `evidence_strength` (section_weight × claim_type_weight × extraction_w × source_reliability);
- расчёт `source_reliability` по секции и типу claim;

**Strict `_build_claim_relations` — связь создаётся ТОЛЬКО при evidence:**

1. **LLM-proposed relations** (created_by='llm') — модель явно указала тип связи в JSON-ответе;
2. **Rule-based group-by-subject** (created_by='rule'): группируем claims по нормализованному `subject_entity`, и внутри группы для каждой пары из РАЗНЫХ публикаций пробуем `_infer_relation_strict`:
   - **CONTRADICTS**: одинаковая `metric` + opposite values, ИЛИ текстовый маркер противоречия (`в отличие от`, `противоречит`, ...);
   - **LIMITS**: один из claims имеет `claim_type='limitation'` И второй имеет `claim_type ∈ {method, conclusion, experimental_result, definition}`, ИЛИ текстовый маркер ограничения;
   - **EXTENDS**: explicit маркер расширения (`развивает`, `опирается на`, `extends`, `based on`), ИЛИ пара `method_description + experimental_result`;
   - **SUPPORTS**: одинаковый `claim_type ∈ {definition, conclusion, experimental_result, method_description, replication_note}` из РАЗНЫХ публикаций.
3. Связи внутри одной публикации не создаются;
4. Каждая связь имеет `created_by ∈ {rule, llm, manual}` для аудита.

**Density cap**: после bootstrap'а `_prune_relations_per_claim(max_per_claim=20)`
оставляет top-20 связей на узел по `weight × confidence × evidence_strength`.

**Near-duplicate dedup**: при добавлении claim ищется похожий (cosine ≥ 0.96 + тот же `claim_type` + другая публикация) → создаётся `SUPPORTS`-связь. Порог поднят с 0.93 → 0.96 чтобы исключить шум от шаблонных фраз.

**Orphan prune**: после bootstrap'а удаляются:
- из in-memory: entities без mentions (`_prune_orphan_entities`);
- из Neo4j: все isolated nodes любого типа (`prune_orphan_nodes`).

Activation index перестраивается после каждого upload по токенам сущностей + chunks + claims.

## Backend: поиск

[search.py](backend/app/features/scientific_kb/search.py) реализует:

- `search_keyword` — overlap токенов;
- `search_semantic` — pgvector (если активен), иначе in-process cosine;
- `search_graph` — обход от активированных claims с учётом весов связей;
- `search_hybrid` — комбинация по 7-компонентной формуле:

```
hybrid_score = α·keyword
             + β·semantic
             + γ·(graph + 0.5·activation_bonus)
             + δ·claim_confidence
             + ε·evidence_strength
             + ζ·source_reliability
             − η·contradiction_risk
```

Веса по умолчанию: α=0.15, β=0.35, γ=0.20, δ=0.10, ε=0.15, ζ=0.05, η=0.10.
Все 7 компонент явно присутствуют в `score_breakdown` ответа.

## Backend: RAG

[rag.py](backend/app/features/scientific_kb/rag.py):

- `ask_with_evidence(question, top_k, language)` запускает hybrid search, собирает evidence, считает coverage;
- если `strong_hits < 2` или `coverage < 0.16` — возвращает `insufficient_evidence` с честным текстом отказа на нужном языке;
- иначе формирует ответ из топ-4 claims или фрагментов, явно перечисляет противоречия;
- сохраняет `RagAnswer` в `rag_answers` и пишет в `scikb_rag_answers` через PG-адаптер;
- `evaluate_rag_answer(id)` считает 8 метрик: `faithfulness`, `source_coverage`, `hallucination_rate`, `answer_completeness`, `citation_correctness`, `limitation_honesty`, `reasoning_trace_quality`, `contradiction_awareness`;
- автоматически создаёт `feedback_event` для каждого source-claim с `signal=positive` или `review_required` в зависимости от faithfulness.

## Backend: feedback и review queue

[feedback_service.py](backend/app/features/scientific_kb/feedback_service.py):

- `submit_feedback({event_type, target_id, signal, weight_delta, payload})` сохраняет событие и сразу применяет его;
- `apply_feedback_event(event)` действительно обновляет `claim.confidence_score`, `claim.evidence_strength` и `weight` SUPPORTS-связей claim'а;
- если `signal=review_required`, claim попадает в `scikb_human_review_queue`;
- `resolve_review_item(id, action)`:
  - `approve` → `claim.confidence_score += 0.05`;
  - `reject` → `claim.confidence_score -= 0.10`;
- `apply_pending_feedback()` применяет все ещё не применённые события батчем.

## Backend: граф

[graph.py](backend/app/features/scientific_kb/graph.py):

- `graph_all()` — все Publication, ScientificClaim, связанные ScientificEntity, все рёбра;
- `graph_for_publication(id)` — подграф публикации (chunks, claims, entities, relations + цитирования);
- `graph_for_entity(id, depth)` — BFS вокруг сущности;
- `graph_for_claim(id, depth)` — BFS вокруг claim'а.

Orphan-сущности не попадают в `graph_all`. У каждого ребра есть `weight`;
claim-relation-рёбра дополнительно несут `confidence_score` и `evidence_strength`.

## Frontend: 3D-граф

[BrainGraph3D.tsx](frontend/src/features/graph/BrainGraph3D.tsx) реализует:

- Three.js scene с темным фоном, fog, perspective camera, WebGLRenderer, OrbitControls;
- ambient light + point lights;
- сферы узлов, halo, TubeGeometry для рёбер, анимированные pulse-сферы;
- neural fibers как дополнительные светящиеся линии;
- dust particles;
- raycaster для выбора узлов;
- ResizeObserver для динамической смены размера canvas;
- requestAnimationFrame loop;
- очистка renderer/controls/geometries/materials при unmount.

[buildBrainGraph.ts](frontend/src/features/graph/model/buildBrainGraph.ts):

- фильтрует узлы по `filter`;
- оставляет только рёбра между видимыми узлами;
- DAG-like раскладка: публикации в одном слое, claims в среднем, entities в нижнем;
- учитывает `graphSpacing`;
- назначает цвета и радиусы по типу узла;
- генерирует `fibers` для светящихся связей.

## Frontend API-клиент

[frontend/src/api.ts](frontend/src/api.ts):

- класс `HttpError`;
- `apiFetch<T>(path, init)`:
  - читает access token из `localStorage[kb.auth.access_token]`;
  - добавляет `Authorization: Bearer <token>` (если не auth-endpoint);
  - при HTTP 401 пробует обновить access через `/v1/auth/refresh`, повторяет оригинальный запрос ровно один раз;
  - единый in-flight refresh защищает от параллельных запросов на refresh;
  - при провале refresh — очищает токены.

[frontend/src/shared/api/scientificKb.ts](frontend/src/shared/api/scientificKb.ts) —
обёртки для всех endpoint'ов scientific_kb.

## Docker-конфигурация

[docker-compose.yml](docker-compose.yml) (после очистки) содержит:

- `frontend`, `frontend-dev`, `frontend-prod-hot`;
- `fastapi`, `fastapi-dev`;
- `postgres` (`pgvector/pgvector:pg15`);
- `neo4j` (5.26);
- `prometheus`, `grafana` (опц.);
- `traefik` (prod-профиль);
- `adminer` (PostgreSQL UI).

`qdrant` и `redis` удалены из compose-файлов.

[docker-compose.override.yml](docker-compose.override.yml) для dev-профиля
открывает порты postgres и neo4j наружу.

## Тесты

[backend/tests/test_demo_coverage.py](backend/tests/test_demo_coverage.py) —
quality-gate для компактного корпуса (`pytest -m "not integration"` исключает
интеграционные тесты, которые требуют живые Neo4j+PG):

1. **`test_corpus_size_is_compact`**: 18 ≤ публикаций ≤ 30 (защита от расширения без намерения);
2. **`test_global_corpus_covers_core_entity_types`**: глобально присутствуют `Method` и `Model`;
3. **`test_global_corpus_covers_core_claim_types`**: глобально присутствуют `definition`, `method_description`, `limitation`, `conclusion`;
4. **`test_at_least_two_relation_types_present`**: ≥2 типа связей (не требуем все 4 — strict-extractor может не найти CONTRADICTS в учебном корпусе);
5. **`test_graph_is_sparse_not_hairball`** — главная защита: avg degree ≤ 20 (защита от регресса к hairball);
6. **`test_no_relation_exceeds_per_claim_cap`**: max degree ≤ 20 (cap соблюдается);
7. **`test_citations_seeded`**: ≥15 курируемых цитирований;
8. **`test_authors_and_organizations_attached`**: ≥6 авторов, ≥3 организации, у каждой публикации есть `author_ids`;
9. **`test_relations_have_provenance`**: у каждой связи `created_by ∈ {rule, llm, manual}`;
10. **`test_claim_user_facing_view_returns_pipeline`**: endpoint `/v1/knowledge/claims/{id}/usage` возвращает корректный `pipeline_trace`.

Все 16 тестов (10 coverage + 6 unit) проходят на актуальном корпусе.

Интеграционные тесты ([tests/integration/test_neo4j_first.py](backend/tests/integration/test_neo4j_first.py))
запускаются командой `pytest -m integration` — проверяют bootstrap-идемпотентность,
Cypher batch-fetch, pgvector search через живые сервисы.

## Чего сейчас нет

Список того, что **действительно** не реализовано:

- WebSocket-прогресс pipeline;
- async-очередь pipeline (`arq` установлен, но не интегрирован после удаления Redis);
- роли пользователей (`role` в таблице `users` всегда `user`; admin-операции доступны любому залогиненному);
- защита scientific_kb endpoint'ов JWT-зависимостью (сейчас защищены только `/v1/auth/me` и `/v1/auth/logout`);
- автоматическое слежение за качеством LLM-извлечения и автоматический pull-обратно к rule-based при деградации;
- экспорт графа в RDF/OWL/Cypher-dump (есть только JSON-выгрузка структуры).

## Frontend-зависимости

Из [frontend/package.json](frontend/package.json):

Runtime:

- `react@^19.2.0`
- `react-dom@^19.2.0`
- `react-router-dom@^7` (для маршрутизации)
- `three@^0.184.0` (3D-граф)

Dev:

- Vite, TypeScript 5.9, ESLint 9
- `@types/react`, `@types/react-dom`, `@types/three`, `@types/node`
- Playwright (для будущих e2e)

Redux, D3, vis-network, React Flow, Vitest не используются.
