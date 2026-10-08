"""Checks family_tree.json (and site.json) before a build.

An *error* breaks the site or the GEDCOM export: a broken reference to a person, family,
document or place, an `S12` mentioned in a text without such a document, a missing file,
an unreadable date. A *warning* is worth a look: death before birth, a person aged 110+.
`gene build` refuses to build when there are errors.
"""
import calendar
import datetime
import re
from pathlib import Path

from .messages import m

MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
_DAY_MON_YEAR = r"(?:(\d{1,2}) )?(?:(" + "|".join(MONTHS) + r") )?(\d{3,4})"
# date forms understood by the site and the GEDCOM export: ISO or GEDCOM (ABT 1899, BET 1900 AND 1905, 9 OCT 1899)
DATE_FORMS = [
    re.compile(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?"),
    re.compile(r"(?:(?:ABT|CAL|EST|BEF|AFT) )?" + _DAY_MON_YEAR),
    re.compile(r"BET " + _DAY_MON_YEAR + r" AND " + _DAY_MON_YEAR),
    re.compile(r"FROM " + _DAY_MON_YEAR + r"(?: TO " + _DAY_MON_YEAR + r")?"),
]
ID_RE = {"people": r"I\d+", "families": r"F\d+", "sources": r"S\d+", "research_leads": r"L\d+"}
SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
SRC_IN_TEXT = re.compile(r"\bS\d+\b")


def bad_path(rel):
    """A file reference must stay inside the site folder and avoid hidden folders (.git, .gene-state…):
    whatever it names is copied to the published site."""
    rel = str(rel)
    parts = rel.replace("\\", "/").split("/")
    return rel.startswith(("/", "~")) or ":" in parts[0] or any(p.startswith(".") or p == "" for p in parts)


def _valid_ymd(y, mo, d):
    try:
        datetime.date(int(y), int(mo or 1), int(d or 1))
        return True
    except ValueError:
        return False


def parse_date(value):
    """The (first) year of a date, or None when the format is not recognised."""
    v = str(value).strip()
    iso = DATE_FORMS[0].fullmatch(v)
    if iso:
        return int(iso[1]) if _valid_ymd(*iso.groups()) else None
    for form in DATE_FORMS[1:]:
        hit = form.fullmatch(v)
        if not hit:
            continue
        g = hit.groups()
        for i in range(0, len(g), 3):   # (day, month, year) triples
            day, mon, year = g[i:i + 3]
            if year is None:
                continue
            if day and not mon:
                return None
            if day and int(day) > calendar.monthrange(int(year), MONTHS.index(mon) + 1)[1]:
                return None
        return int(g[2])
    return None


def validate(data, root=Path("."), cfg=None):
    """Returns (errors, warnings): lists of strings. `root` is the site folder (for file checks)."""
    root = Path(root)
    errors, warnings = [], []
    err, warn = errors.append, warnings.append
    for key in ("people", "families", "sources"):
        if not isinstance(data.get(key), list):
            return [m(f"family_tree.json: '{key}' must be a list", f"family_tree.json: «{key}» должен быть списком")], []

    # --- ids
    ids = {}
    for kind, pattern in ID_RE.items():
        seen = set()
        for x in data.get(kind, []):
            i = x.get("id")
            if not isinstance(i, str) or not re.fullmatch(pattern, i):
                err(m(f"{kind}: invalid id {i!r}", f"{kind}: неверный номер {i!r}"))
            elif i in seen:
                err(m(f"{kind}: id {i} is used twice", f"{kind}: номер {i} повторяется"))
            seen.add(i)
        ids[kind] = seen
    people, fams, srcs = ids["people"], ids["families"], ids["sources"]
    slugs = [p.get("slug") for p in data.get("places", [])]
    places = set(slugs)
    for s in slugs:
        if not isinstance(s, str) or not SLUG_RE.fullmatch(s):
            err(m(f"places: invalid slug {s!r} (use a-z, 0-9 and -)", f"places: неверный slug {s!r} (латиница, цифры, -)"))
    for s in {s for s in slugs if slugs.count(s) > 1}:
        err(m(f"places: slug {s} is used twice", f"places: slug {s} повторяется"))
    groups = {g["id"] for g in data.get("place_groups", [])}

    def need(where, ref, pool, what_en, what_ru):
        if ref not in pool:
            err(m(f"{where}: no {what_en} {ref}", f"{where}: нет {what_ru} {ref}"))

    def need_sources(where, refs):
        for s in refs or []:
            need(where, s, srcs, "document", "документа")

    def text_sources(where, text):
        if isinstance(text, list):
            text = "\n".join(t for t in text if isinstance(t, str))
        for s in SRC_IN_TEXT.findall(text or ""):
            if s not in srcs:
                err(m(f"{where}: the text mentions {s}, but there is no such document",
                      f"{where}: в тексте упомянут {s}, а такого документа нет"))

    def check_event(where, ev):
        if not isinstance(ev, dict):
            return None
        need_sources(where, ev.get("source_ids"))
        for k in ("note", "place_as_recorded"):
            text_sources(where, ev.get(k))
        for slug in ev.get("place_slugs", []):
            need(where, slug, places, "place", "места")
        year = None
        if ev.get("date"):
            year = parse_date(ev["date"])
            if year is None:
                err(m(f"{where}: date {ev['date']!r} is neither ISO nor GEDCOM (see docs/data-format.md)",
                      f"{where}: дата {ev['date']!r} не в формате ISO или GEDCOM (см. docs/data-format.ru.md)"))
        return year

    # --- people
    for p in data["people"]:
        pid = p.get("id")
        for k in ("given_names", "surname", "display_name", "sex", "notes"):
            if k not in p:
                err(m(f"{pid}: field {k} is missing", f"{pid}: нет поля {k}"))
        if p.get("sex") not in ("M", "F", "U"):
            err(m(f"{pid}: sex {p.get('sex')!r} (use M, F or U)", f"{pid}: пол {p.get('sex')!r} (M, F или U)"))
        if not isinstance(p.get("notes", []), list):
            err(m(f"{pid}: notes must be a list of paragraphs", f"{pid}: notes — список абзацев"))
        if "living" in p and not isinstance(p["living"], bool):
            err(m(f"{pid}: living must be true or false", f"{pid}: living — true или false"))
        need_sources(pid, p.get("identity_source_ids", []) + p.get("source_ids", []))
        text_sources(pid, p.get("notes"))
        text_sources(pid, p.get("research_note"))
        years = {}
        for key in ("birth", "death", "burial"):
            years[key] = check_event(f"{pid} {key}", p.get(key))
            for n, alt in enumerate(p.get(f"{key}_alternatives", [])):
                check_event(f"{pid} {key}_alternatives[{n}]", alt)
        for n, r in enumerate(p.get("residences", [])):
            # residence dates are free text ("until 1968 — 1972") and are not parsed
            need_sources(f"{pid} residences[{n}]", r.get("source_ids"))
            for slug in r.get("place_slugs", []):
                need(f"{pid} residences[{n}]", slug, places, "place", "места")
        b, d = years["birth"], years["death"]
        if b and d and d < b:
            warn(m(f"{pid}: death ({d}) before birth ({b})", f"{pid}: смерть ({d}) раньше рождения ({b})"))
        if b and d and d - b > 110:
            warn(m(f"{pid}: lived more than 110 years ({b}–{d})", f"{pid}: прожил(а) больше 110 лет ({b}–{d})"))

    # --- families
    in_family = {}
    for f in data["families"]:
        fid = f.get("id")
        for k in ("partners", "children", "adopted_children", "probable_children"):
            for x in f.get(k, []):
                need(f"{fid} {k}", x, people, "person", "человека")
        if len(f.get("partners", [])) > 2:
            err(m(f"{fid}: more than two partners", f"{fid}: больше двух партнёров"))
        for x in f.get("children", []) + f.get("adopted_children", []):
            if x in f.get("partners", []):
                err(m(f"{fid}: {x} is both a parent and a child", f"{fid}: {x} одновременно родитель и ребёнок"))
        for x in f.get("children", []) if f.get("partners") else []:
            if x in in_family:
                warn(m(f"{x}: biological child in two families ({in_family[x]}, {fid})",
                       f"{x}: родной ребёнок в двух семьях ({in_family[x]}, {fid})"))
            in_family.setdefault(x, fid)
        need_sources(fid, f.get("source_ids"))
        text_sources(fid, f.get("notes"))
        text_sources(fid, f.get("probable_note"))
        check_event(f"{fid} marriage", f.get("marriage"))

    # --- sources
    for s in data["sources"]:
        sid = s.get("id")
        for k in ("title", "kind"):
            if not s.get(k):
                err(m(f"{sid}: field {k} is missing", f"{sid}: нет поля {k}"))
        for k in ("file", "back"):
            if s.get(k):
                rel = str(s[k])
                if bad_path(rel):
                    err(m(f"{sid}: {k} must be a path inside the site folder", f"{sid}: {k} — путь внутри папки сайта"))
                elif not (root / rel).is_file():
                    err(m(f"{sid}: file {rel} not found", f"{sid}: нет файла {rel}"))
        if s.get("merged_into"):
            need(sid, s["merged_into"], srcs, "document", "документа")
        if s.get("preview_page") is not None and not str(s.get("file", "")).lower().endswith(".pdf"):
            warn(m(f"{sid}: preview_page on a file that is not a PDF", f"{sid}: preview_page у файла, который не PDF"))
        text_sources(sid, s.get("scope"))

    # --- places
    for pl in data.get("places", []):
        where = m(f"place {pl.get('slug')}", f"место {pl.get('slug')}")
        if not pl.get("name"):
            err(m(f"{where}: name is missing", f"{where}: нет названия"))
        for x in pl.get("people", []):
            need(where, x, people, "person", "человека")
        need_sources(where, pl.get("sources"))
        for g in pl.get("groups", []):
            need(where, g, groups, "place group", "группы мест")
        for k in ("text", "details"):
            text_sources(where, pl.get(k))
        for n, t in enumerate(pl.get("timeline", [])):
            for x in t.get("people", []):
                need(f"{where} timeline[{n}]", x, people, "person", "человека")
            need_sources(f"{where} timeline[{n}]", t.get("sources"))
            text_sources(f"{where} timeline[{n}]", t.get("text"))
        if ("lat" in pl) != ("lon" in pl):
            err(m(f"{where}: only one coordinate", f"{where}: координата только одна"))
        for n, md in enumerate(pl.get("media", [])):
            if md.get("file") and bad_path(md["file"]):
                err(m(f"{where} media[{n}]: file must be a path inside the site folder", f"{where} media[{n}]: файл — путь внутри папки сайта"))
            elif md.get("file") and not (root / md["file"]).is_file():
                err(m(f"{where} media[{n}]: file {md['file']} not found", f"{where} media[{n}]: нет файла {md['file']}"))
    for n, r in enumerate(data.get("place_routes", [])):
        where = f"place_routes[{n}]"
        need(where, r.get("from_place"), places, "place", "места")
        need(where, r.get("to_place"), places, "place", "места")
        need(where, r.get("group"), groups, "place group", "группы мест")
        need_sources(where, r.get("sources"))

    # --- research journal
    for lead in data.get("research_leads", []):
        lid = lead.get("id")
        for k in ("title", "status", "record"):
            if not lead.get(k):
                err(m(f"{lid}: field {k} is missing", f"{lid}: нет поля {k}"))
        if lead.get("person_id"):
            need(lid, lead["person_id"], people, "person", "человека")
        need_sources(lid, lead.get("source_ids"))
    for n, c in enumerate(data.get("corrections", [])):
        where = f"corrections[{n}]"
        missing = [k for k in ("field", "previous", "current", "reason") if k not in c]
        if missing:
            err(m(f"{where}: fields missing: {', '.join(missing)}", f"{where}: нет полей {', '.join(missing)}"))
        if not any(c.get(k) for k in ("person_id", "family_id", "record")):
            err(m(f"{where}: say what it is about (person_id, family_id or record)",
                  f"{where}: не указано, к кому относится (person_id, family_id или record)"))
        # the log keeps corrections about deleted people too: only the id format is checked; "*" = many people
        if c.get("person_id") and not re.fullmatch(r"I\d+|\*", c["person_id"]):
            err(m(f"{where}: invalid person_id {c['person_id']!r}", f"{where}: неверный person_id {c['person_id']!r}"))
        if c.get("family_id"):
            need(where, c["family_id"], fams, "family", "семьи")
        need_sources(where, c.get("source_ids"))
    for n, r in enumerate(data.get("research_log", [])):
        where = f"research_log[{n}]"
        missing = [k for k in ("date", "action", "result") if not r.get(k)]
        if missing:
            err(m(f"{where}: fields missing: {', '.join(missing)}", f"{where}: нет полей {', '.join(missing)}"))
        if r.get("date") and not (re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["date"]) and parse_date(r["date"])):
            err(m(f"{where}: date {r['date']!r} is not YYYY-MM-DD", f"{where}: дата {r['date']!r} не в формате ГГГГ-ММ-ДД"))

    root_id = (cfg or {}).get("root_person") or data.get("root_person_id")
    if root_id not in people:
        err(m(f"root person {root_id!r} does not exist", f"корневого человека {root_id!r} нет"))

    # --- site.json references
    if cfg:
        refs = [("start_person", cfg.get("start_person"))]
        refs += [(f"quick_focus[{n}]", q.get("person")) for n, q in enumerate(cfg.get("quick_focus", []))]
        refs += [(f"branches[{n}]", b.get("focus")) for n, b in enumerate(cfg.get("branches", []))]
        refs += [(f"questions[{n}]", q.get("person")) for n, q in enumerate(cfg.get("questions", []))]
        for where, pid in refs:
            if pid and pid not in people:
                err(m(f"site.json {where}: no person {pid}", f"site.json {where}: нет человека {pid}"))
        for n, item in enumerate((cfg.get("story") or {}).get("places", [])):
            try:
                re.compile(item[1])
            except (re.error, IndexError, TypeError):
                err(m(f"site.json story.places[{n}]: expected [label, regular expression]",
                      f"site.json story.places[{n}]: нужно [название, регулярное выражение]"))
    return errors, warnings
