from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ontology import RESEARCH_FIELDS_FOR_METHOD


@dataclass
class DemoAuthor:
    id: str
    name: str
    organization: str
    orcid: str | None = None


@dataclass
class DemoOrganization:
    id: str
    name: str
    country: str
    kind: str = "Research lab"


@dataclass
class DemoCitation:
    source_title: str
    target_title: str
    citation_context: str


DEMO_AUTHORS: list[DemoAuthor] = [
    DemoAuthor(id="auth_iv01", name="Анна Иванова", organization="org_mguim", orcid="0000-0002-1010-0001"),
    DemoAuthor(id="auth_ku02", name="Дмитрий Кузнецов", organization="org_mguim", orcid="0000-0002-1010-0002"),
    DemoAuthor(id="auth_or03", name="Мария Орлова", organization="org_spbu_db", orcid="0000-0002-1010-0003"),
    DemoAuthor(id="auth_se04", name="Сергей Семёнов", organization="org_yandex_research", orcid="0000-0002-1010-0004"),
    DemoAuthor(id="auth_pe05", name="Юлия Петрова", organization="org_spbu_db", orcid="0000-0002-1010-0005"),
    DemoAuthor(id="auth_so06", name="Александр Соколов", organization="org_yandex_research", orcid="0000-0002-1010-0006"),
    DemoAuthor(id="auth_no07", name="Никита Новиков", organization="org_dbm_lab", orcid="0000-0002-1010-0007"),
    DemoAuthor(id="auth_vo08", name="Виктория Волкова", organization="org_dbm_lab", orcid="0000-0002-1010-0008"),
    DemoAuthor(id="auth_sm09", name="Игорь Смирнов", organization="org_school_math", orcid="0000-0002-1010-0009"),
    DemoAuthor(id="auth_le10", name="Екатерина Лебедева", organization="org_school_math", orcid="0000-0002-1010-0010"),
    DemoAuthor(id="auth_pa11", name="Михаил Павлов", organization="org_school_inform", orcid="0000-0002-1010-0011"),
    DemoAuthor(id="auth_ne12", name="Ольга Нестерова", organization="org_school_inform", orcid="0000-0002-1010-0012"),
]


DEMO_ORGANIZATIONS: list[DemoOrganization] = [
    DemoOrganization(
        id="org_mguim",
        name="Кафедра вычислительной математики МГУ",
        country="RU",
        kind="Университетская кафедра",
    ),
    DemoOrganization(
        id="org_spbu_db",
        name="Лаборатория баз данных СПбГУ",
        country="RU",
        kind="Университетская лаборатория",
    ),
    DemoOrganization(
        id="org_yandex_research",
        name="Группа учебных данных Яндекс",
        country="RU",
        kind="Корпоративная исследовательская группа",
    ),
    DemoOrganization(
        id="org_dbm_lab",
        name="Лаборатория управления данными ИТМО",
        country="RU",
        kind="Университетская лаборатория",
    ),
    DemoOrganization(
        id="org_school_math",
        name="Кафедра школьной математики педагогического университета",
        country="RU",
        kind="Школьная кафедра",
    ),
    DemoOrganization(
        id="org_school_inform",
        name="Школьная лаборатория информатики и алгоритмов",
        country="RU",
        kind="Школьная лаборатория",
    ),
]


# Заголовки 20 статей нового компактного корпуса (5 кластеров).
# Порядок важен — в этом порядке авторы циклически распределяются.
_TITLES_ALL = [
    # Кластер 1 — Поиск в массиве
    "Линейный поиск элемента в массиве",
    "Двоичный поиск в отсортированном массиве",
    "Сравнение линейного и двоичного поиска",
    "Двоичный поиск не работает на неотсортированных массивах",
    # Кластер 2 — Сортировка
    "Сортировка пузырьком",
    "Сортировка слиянием: разделяй и властвуй",
    "Сравнение сортировок: пузырёк против слияния",
    "Сортировка как предусловие для двоичного поиска",
    # Кластер 3 — Таблицы и ключи
    "Таблица в реляционной базе данных",
    "Первичный ключ как уникальный идентификатор строки",
    "Внешний ключ для связи между таблицами",
    "Фильтрация строк через условие WHERE",
    "Соединение таблиц через JOIN по ключу",
    # Кластер 4 — Индексы
    "Индекс на колонке для ускорения запросов",
    "Индекс ускоряет SELECT в десятки раз",
    "Индекс работает по принципу двоичного поиска",
    "Когда индекс мешает: замедление операций записи",
    # Кластер 5 — Школьная математика
    "Линейная функция и её график",
    "Квадратное уравнение и формула корней",
    "Производная как скорость изменения функции",
]


def _author_pair(index: int) -> list[str]:
    a = index % len(DEMO_AUTHORS)
    b = (index + 5) % len(DEMO_AUTHORS)
    if a == b:
        b = (b + 1) % len(DEMO_AUTHORS)
    return [DEMO_AUTHORS[a].id, DEMO_AUTHORS[b].id]


PUBLICATION_AUTHORS: dict[str, list[str]] = {
    title: _author_pair(i) for i, title in enumerate(_TITLES_ALL)
}


# Цитирования между статьями корпуса. Каждое цитирование = ребро CITES в графе.
# Дизайн: внутрикластерные ссылки + 3 cross-cluster bridge'а (Сортировка ↔ Поиск,
# Индекс ↔ Поиск, Индекс ↔ Таблицы). Это даёт связный граф без избыточности.
DEMO_CITATIONS: list[DemoCitation] = [
    # ── Кластер 1 (Поиск) внутрикластерные ─────────────────────────────
    DemoCitation(
        source_title="Двоичный поиск в отсортированном массиве",
        target_title="Линейный поиск элемента в массиве",
        citation_context="развивает идею линейного поиска через сокращение области поиска вдвое на каждом шаге",
    ),
    DemoCitation(
        source_title="Сравнение линейного и двоичного поиска",
        target_title="Линейный поиск элемента в массиве",
        citation_context="сравнивает с базовым линейным поиском по числу операций",
    ),
    DemoCitation(
        source_title="Сравнение линейного и двоичного поиска",
        target_title="Двоичный поиск в отсортированном массиве",
        citation_context="сравнивает с двоичным поиском на отсортированных массивах",
    ),
    DemoCitation(
        source_title="Двоичный поиск не работает на неотсортированных массивах",
        target_title="Двоичный поиск в отсортированном массиве",
        citation_context="ограничивает применимость двоичного поиска условием отсортированности",
    ),
    # ── Кластер 2 (Сортировка) внутрикластерные ─────────────────────────
    DemoCitation(
        source_title="Сортировка слиянием: разделяй и властвуй",
        target_title="Сортировка пузырьком",
        citation_context="развивает идею сортировки пузырьком через рекурсивное деление",
    ),
    DemoCitation(
        source_title="Сравнение сортировок: пузырёк против слияния",
        target_title="Сортировка пузырьком",
        citation_context="сравнивает простую сортировку с более эффективной",
    ),
    DemoCitation(
        source_title="Сравнение сортировок: пузырёк против слияния",
        target_title="Сортировка слиянием: разделяй и властвуй",
        citation_context="сравнивает сортировку слиянием с простыми методами",
    ),
    DemoCitation(
        source_title="Сортировка как предусловие для двоичного поиска",
        target_title="Сортировка пузырьком",
        citation_context="использует сортировку пузырьком как простую опцию подготовки данных",
    ),
    DemoCitation(
        source_title="Сортировка как предусловие для двоичного поиска",
        target_title="Сортировка слиянием: разделяй и властвуй",
        citation_context="использует сортировку слиянием для подготовки больших массивов",
    ),
    # ── Bridge: Cluster 2 → Cluster 1 ───────────────────────────────────
    DemoCitation(
        source_title="Сортировка как предусловие для двоичного поиска",
        target_title="Двоичный поиск в отсортированном массиве",
        citation_context="обосновывает необходимость сортировки для применения двоичного поиска",
    ),
    # ── Кластер 3 (Таблицы и ключи) — цепочка определений ───────────────
    DemoCitation(
        source_title="Первичный ключ как уникальный идентификатор строки",
        target_title="Таблица в реляционной базе данных",
        citation_context="развивает идею таблицы, добавляя гарантию уникальности строк",
    ),
    DemoCitation(
        source_title="Внешний ключ для связи между таблицами",
        target_title="Первичный ключ как уникальный идентификатор строки",
        citation_context="опирается на первичный ключ как точку привязки внешнего ключа",
    ),
    DemoCitation(
        source_title="Фильтрация строк через условие WHERE",
        target_title="Таблица в реляционной базе данных",
        citation_context="применяет операцию фильтрации к таблице реляционной базы данных",
    ),
    DemoCitation(
        source_title="Соединение таблиц через JOIN по ключу",
        target_title="Внешний ключ для связи между таблицами",
        citation_context="использует внешний ключ для соединения двух таблиц",
    ),
    DemoCitation(
        source_title="Соединение таблиц через JOIN по ключу",
        target_title="Фильтрация строк через условие WHERE",
        citation_context="комбинирует соединение с фильтрацией результата",
    ),
    # ── Кластер 4 (Индексы) внутрикластерные ────────────────────────────
    DemoCitation(
        source_title="Индекс ускоряет SELECT в десятки раз",
        target_title="Индекс на колонке для ускорения запросов",
        citation_context="измеряет экспериментально ускорение от индекса",
    ),
    DemoCitation(
        source_title="Когда индекс мешает: замедление операций записи",
        target_title="Индекс на колонке для ускорения запросов",
        citation_context="фиксирует ограничения индекса при частой записи",
    ),
    DemoCitation(
        source_title="Когда индекс мешает: замедление операций записи",
        target_title="Индекс ускоряет SELECT в десятки раз",
        citation_context="противопоставляет выигрыш по чтению потерям по записи",
    ),
    # ── Bridge: Cluster 4 → Cluster 3 ───────────────────────────────────
    DemoCitation(
        source_title="Индекс на колонке для ускорения запросов",
        target_title="Таблица в реляционной базе данных",
        citation_context="индекс — вспомогательная структура поверх таблицы",
    ),
    DemoCitation(
        source_title="Индекс на колонке для ускорения запросов",
        target_title="Фильтрация строк через условие WHERE",
        citation_context="индекс ускоряет именно операцию фильтрации строк",
    ),
    # ── Bridge: Cluster 4 → Cluster 1 (главный кросс-кластерный мост) ──
    DemoCitation(
        source_title="Индекс работает по принципу двоичного поиска",
        target_title="Двоичный поиск в отсортированном массиве",
        citation_context="внутренний механизм индекса — это двоичный поиск по отсортированным значениям",
    ),
    DemoCitation(
        source_title="Индекс работает по принципу двоичного поиска",
        target_title="Индекс на колонке для ускорения запросов",
        citation_context="раскрывает внутреннее устройство индекса",
    ),
    # ── Кластер 5 (Математика) внутрикластерные ─────────────────────────
    DemoCitation(
        source_title="Квадратное уравнение и формула корней",
        target_title="Линейная функция и её график",
        citation_context="развивает идею уравнения до второй степени",
    ),
    DemoCitation(
        source_title="Производная как скорость изменения функции",
        target_title="Линейная функция и её график",
        citation_context="развивает понятие наклона прямой до произвольной функции",
    ),
]




def attach_authors_and_organizations(scientific_kb: Any) -> None:
    by_title = {p.title: p for p in scientific_kb.publications.values()}
    scientific_kb.demo_authors = {a.id: a for a in DEMO_AUTHORS}
    scientific_kb.demo_organizations = {o.id: o for o in DEMO_ORGANIZATIONS}

    for title, author_ids in PUBLICATION_AUTHORS.items():
        publication = by_title.get(title)
        if not publication:
            continue
        publication.authors = [scientific_kb.demo_authors[aid].name for aid in author_ids]
        publication.metadata.setdefault("author_ids", [])
        publication.metadata["author_ids"] = author_ids
        organisations = sorted(
            {scientific_kb.demo_authors[aid].organization for aid in author_ids if aid in scientific_kb.demo_authors}
        )
        publication.metadata["organizations"] = organisations
        primary_field = _primary_research_field(scientific_kb, publication.id)
        publication.metadata["research_field"] = primary_field


def attach_citations(scientific_kb: Any) -> None:
    by_title = {p.title: p for p in scientific_kb.publications.values()}
    citations: list[dict[str, str]] = []
    for citation in DEMO_CITATIONS:
        src = by_title.get(citation.source_title)
        tgt = by_title.get(citation.target_title)
        if not src or not tgt:
            continue
        citations.append(
            {
                "source_publication_id": src.id,
                "target_publication_id": tgt.id,
                "context": citation.citation_context,
            }
        )
        src.metadata.setdefault("cites", [])
        if tgt.id not in src.metadata["cites"]:
            src.metadata["cites"].append(tgt.id)
        tgt.metadata.setdefault("cited_by", [])
        if src.id not in tgt.metadata["cited_by"]:
            tgt.metadata["cited_by"].append(src.id)
    scientific_kb.demo_citations = citations


def _primary_research_field(scientific_kb: Any, publication_id: str) -> str | None:
    counters: dict[str, int] = {}
    # 1) Сначала пытаемся вытащить область из subject/object исков.
    for claim in scientific_kb.claims.values():
        if claim.publication_id != publication_id:
            continue
        for name in (claim.subject_entity, claim.object_entity, claim.metric):
            if not name:
                continue
            field = RESEARCH_FIELDS_FOR_METHOD.get(name)
            if field:
                counters[field] = counters.get(field, 0) + 1
            entity_id = scientific_kb._entity_by_canonical.get(name)
            if entity_id and scientific_kb.entities[entity_id].entity_type == "ResearchField":
                counters[name] = counters.get(name, 0) + 2
    # 2) Если не нашли — смотрим все mentions сущностей, привязанных к публикации.
    if not counters:
        for entity in scientific_kb.entities.values():
            if not any(m.get("publication_id") == publication_id for m in entity.mentions):
                continue
            if entity.entity_type == "ResearchField":
                counters[entity.canonical_name] = counters.get(entity.canonical_name, 0) + 2
            else:
                field = RESEARCH_FIELDS_FOR_METHOD.get(entity.canonical_name)
                if field:
                    counters[field] = counters.get(field, 0) + 1
    if not counters:
        return None
    return max(counters.items(), key=lambda kv: kv[1])[0]


def attach_demo_metadata(scientific_kb: Any) -> None:
    attach_authors_and_organizations(scientific_kb)
    attach_citations(scientific_kb)
