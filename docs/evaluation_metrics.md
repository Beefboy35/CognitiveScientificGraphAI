# Метрики оценки качества RAG-ответов

Когда пользователь нажимает **«Оценить»** в Lab или внешняя система вызывает
`POST /v1/evaluation/rag-answer/{rag_answer_id}`, backend запускает
[`evaluate_rag_answer`](../backend/app/features/scientific_kb/rag.py)
и считает 8 метрик качества. Все метрики в диапазоне `[0, 1]` (1.0 —
идеально, кроме `hallucination_rate`, где идеал — `0.0`).

Результат сохраняется в `scikb_answer_evaluations` (PostgreSQL) и в
in-memory `evaluations`. На основе метрик автоматически создаются
`feedback_event`-ы для каждого source-claim'а ответа: при `faithfulness ≥ 0.8`
— `signal=positive` с `weight_delta=+0.03`, иначе — `signal=review_required`
с `weight_delta=-0.05`.

## Сводная таблица

| # | Метрика | Что измеряет | Формула | Идеал |
|---|---|---|---|---|
| 1 | **faithfulness** | Насколько ответ верен источникам (анти-выдумка) | `0.55 + 0.25·strong_ratio + 0.20·evidence_mean`, capped at `0.97` | `≥ 0.85` |
| 2 | **source_coverage** | Достаточно ли источников было использовано | `min(1.0, source_count / 4)` | `≥ 0.75` (≥3 источника) |
| 3 | **hallucination_rate** | Доля «выдуманного» в ответе | `max(0, 1 − faithfulness)`, `0.0` при honest refusal | `≤ 0.15` |
| 4 | **answer_completeness** | Полнота ответа по числу использованных claims | `min(1.0, claim_count / 3)`, `0.0` при refusal | `≥ 0.67` (≥2 claims) |
| 5 | **citation_correctness** | Есть ли вообще ссылки на источники | `1.0` если sources непуст, иначе `0.0` | `1.0` |
| 6 | **limitation_honesty** | Указаны ли ограничения ответа | `0.98` если `limitations` непуст, иначе `0.5` | `0.98` |
| 7 | **reasoning_trace_quality** | Полнота 7-этапной цепочки вывода | `min(1.0, len(reasoning_trace) / 7)` | `1.0` |
| 8 | **contradiction_awareness** | Заметила ли система противоречия в evidence и упомянула ли их | `1.0` (refusal) · `0.7` (нет противоречий) · `1.0` (есть + упомянуты) · `0.5` (есть и не упомянуты) | `≥ 0.7` |

## Подробно по каждой метрике

### 1. faithfulness — верность источникам

**Что**: главная анти-галлюцинационная метрика. Высокая faithfulness
означает, что ответ построен на сильных, подтверждённых evidence.

**Формула**:
```python
if rag.status == "insufficient_evidence":
    return 1.0          # отказ — это правильное поведение, кредит доверия
if not rag.sources:
    return 0.4          # ответ без источников — подозрительно
strong_sources = [s for s in rag.sources if s["score"] >= 0.30]
strong_ratio = len(strong_sources) / max(1, len(rag.sources))
evidence_mean = mean(s["evidence_strength"] for s in rag.sources)
return min(0.97, 0.55 + 0.25 * strong_ratio + 0.20 * evidence_mean)
```

- `0.55` — стартовый уровень доверия для любого ответа с источниками;
- `0.25 · strong_ratio` — бонус за долю источников с `hybrid_score ≥ 0.30`;
- `0.20 · evidence_mean` — бонус за среднюю силу доказательств;
- Cap `0.97` — никогда не даём 100% (всегда есть остаточная неопределённость).

**Эффект**: `faithfulness ≥ 0.8` ⇒ автоматически создаются positive
feedback events для всех source-claim'ов → их `confidence_score` растёт
на `+0.03`. В обратном случае — `review_required` → `confidence_score −= 0.05`.

### 2. source_coverage — достаточность источников

**Что**: ответ на сложный вопрос должен опираться на несколько публикаций,
а не на одну. 4 источника — это «полное» покрытие.

**Формула**:
```python
source_coverage = min(1.0, source_count / 4)
```

| `source_count` | `source_coverage` |
|---|---|
| 0 | 0.00 |
| 1 | 0.25 |
| 2 | 0.50 |
| 3 | 0.75 |
| ≥ 4 | 1.00 |

### 3. hallucination_rate — уровень выдумки

**Что**: обратная сторона faithfulness. Прямой индикатор «выдуманного».

**Формула**:
```python
hallucination_rate = max(0.0, 1.0 - faithfulness) if rag.status == "answered" else 0.0
```

При honest refusal эта метрика всегда `0.0` — система не выдумала ничего.

### 4. answer_completeness — полнота ответа

**Что**: ответ должен опираться минимум на 3 разных claim'а. Меньше — повод
для review.

**Формула**:
```python
if rag.status == "insufficient_evidence":
    return 0.0          # отказ — ответ ничего не объясняет
return min(1.0, claim_count / 3)
```

| `claim_count` | `answer_completeness` |
|---|---|
| 0 | 0.00 |
| 1 | 0.33 |
| 2 | 0.67 |
| ≥ 3 | 1.00 |

### 5. citation_correctness — наличие цитирований

**Что**: бинарная метрика. Если в ответе нет ссылок на источники — система
работает как чёрный ящик, что недопустимо для научной базы.

**Формула**:
```python
citation_correctness = 1.0 if source_count else 0.0
```

В текущей реализации эта метрика всегда `1.0` для статуса `answered`
(потому что без источников ответ не строится) и `0.0` для refusal.
В будущем сюда можно добавить проверку, что цитирования **корректны**
(claim_id из sources действительно соответствуют тексту ответа).

### 6. limitation_honesty — честность про ограничения

**Что**: проверяет, заполнено ли поле `rag.limitations[]`. Хороший ответ
RAG всегда говорит, **чего он не покрывает**.

**Формула**:
```python
limitation_honesty = 0.98 if rag.limitations else 0.5
```

- `0.98` если в `limitations` есть хотя бы одна строка;
- `0.5` если поле пустое — серединка, не штрафуем сильно, но и не одобряем.

Не `1.0`, чтобы оставить место для будущей детальной проверки качества
самих limitations (например, что они конкретные, а не общие фразы).

### 7. reasoning_trace_quality — полнота цепочки вывода

**Что**: эталонная RAG-цепочка имеет 7 шагов:

1. `question` — сам вопрос
2. `activation_keys` — токены вопроса + синонимы из ALIASES
3. `entities` — сущности из ontology
4. `claims` — релевантные утверждения
5. `evidence_builder` — конкретные chunk'и
6. `contradiction_disclosure` ИЛИ `evidence_aggregation`
7. `grounded_answer` — финальный ответ

**Формула**:
```python
reasoning_trace_quality = min(1.0, len(reasoning_trace) / 7)
```

При honest refusal trace имеет 4 шага → метрика `4/7 ≈ 0.57`, что
адекватно: отказ короче, но всё равно прозрачен.

### 8. contradiction_awareness — заметность противоречий

**Что**: если в evidence есть противоречащие друг другу claim'ы
(`contradiction_risk > 0.3`), система должна **явно упомянуть** об этом
в ответе.

**Формула**:
```python
if rag.status != "answered":
    return 1.0          # отказ не врёт про противоречия

contradicting = sum(1 for s in rag.sources if s["contradiction_risk"] > 0.3)
if contradicting == 0:
    return 0.7          # противоречий нет — но и доказать честность нечем

mentioned = "противореч" in rag.answer.lower() or "contradict" in rag.answer.lower()
return 1.0 if mentioned else 0.5
```

| Сценарий | Метрика |
|---|---|
| Refusal | 1.0 |
| Ответ + нет противоречий в evidence | 0.7 |
| Ответ + противоречия + упомянуты явно («противоречит / contradict») | 1.0 |
| Ответ + противоречия + НЕ упомянуты | 0.5 (предупреждение комиссии) |

## Полный пример расчёта

Запрос: **«Что лучше — линейный или двоичный поиск?»**

После RAG:
- `status = "answered"`
- `sources` = 5 штук, у 4 из них `score ≥ 0.30`
- `evidence_strength` каждого source ∈ {0.70, 0.85, 0.78, 0.82, 0.65}
- `used_claims` = 4
- `reasoning_trace` = 7 шагов
- `limitations` = 2 строки
- 1 source имеет `contradiction_risk = 0.42`
- В тексте ответа есть слово «противоречит»

**Расчёт**:

| Метрика | Промежуточные значения | Формула | Значение |
|---|---|---|---|
| faithfulness | `strong_ratio=4/5=0.8`, `evidence_mean=(0.70+0.85+0.78+0.82+0.65)/5=0.76` | `0.55 + 0.25·0.8 + 0.20·0.76` | **0.902** |
| source_coverage | `source_count=5` | `min(1.0, 5/4)` | **1.000** |
| hallucination_rate | — | `max(0, 1−0.902)` | **0.098** |
| answer_completeness | `claim_count=4` | `min(1.0, 4/3)` | **1.000** |
| citation_correctness | `source_count=5>0` | — | **1.000** |
| limitation_honesty | `limitations≠[]` | — | **0.980** |
| reasoning_trace_quality | `len(trace)=7` | `min(1.0, 7/7)` | **1.000** |
| contradiction_awareness | `contradicting=1`, `mentioned=True` | — | **1.000** |

**Итог**: `faithfulness = 0.902 ≥ 0.8` → создаётся **5 positive feedback events**, по одному на каждый source-claim. Каждый их claim получает `confidence_score += 0.03`.

## Где используются метрики

| Куда | Что делают |
|---|---|
| **Feedback loop** ([feedback_service.py](../backend/app/features/scientific_kb/feedback_service.py)) | `faithfulness ≥ 0.8` → positive, иначе → review_required; weight_delta `±0.03/±0.05` на claim.confidence_score |
| **Review queue** | claim с `review_required` попадает в `scikb_human_review_queue` |
| **Aggregate dashboard** ([api](../backend/app/api/scientific_kb.py)) | `GET /v1/evaluation/aggregate` возвращает средние по всем 8 метрикам за время существования системы |
| **Lab UI** ([LabPage.tsx](../frontend/src/features/lab/LabPage.tsx)) | После клика «Оценить» рисует 8 score-bars + значения с 2 знаками после запятой |

## Ограничения и пути улучшения

Текущая реализация — **MVP**, формулы простые и интерпретируемые.
Стоит улучшить:

- **citation_correctness** — добавить проверку, что упомянутые в ответе
  claim_id действительно соответствуют цитатам в `evidence_text`;
- **faithfulness** — текущая формула линейная; можно добавить NLI-модель,
  которая проверяет логическое следование `evidence → answer`;
- **limitation_honesty** — оценивать содержательность ограничений
  (длина, конкретность), а не только их наличие;
- **answer_completeness** — учитывать **разнообразие claim_types**, а не
  просто число (3 definition'а ≠ 3 разных типа claim'ов);
- **contradiction_awareness** — детектировать упоминания противоречий
  через embeddings, а не по подстроке «противоречит».
