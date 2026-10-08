"""Research hints: what is missing or looks wrong in the data — a to-do list for the next search.

Not errors (`gene validate` finds those): the data is valid, but a person has no dates, a date
has no document, a mother is 61 at a birth, a document is not referenced by anyone…

    gene hints <folder> [--json]          and the "Checks" tab of the online editor

Each hint is {"code", "kind", "id", "params"}; texts for people are in HINTS (ru/en) here and
in the editor's dictionary.
"""
import collections
import re

SRC_IN_TEXT = re.compile(r"\bS\d+\b")
# order = importance: impossible facts first, then gaps
CODES = ("born_after_mother_death", "born_after_father_death", "parent_young", "parent_old", "married_young",
         "long_life", "unconnected", "no_documents", "event_no_source", "no_dates", "family_no_source",
         "no_sex", "unused_source", "place_no_coords")
HINTS = {   # code → (English, Russian) with {name}, {other}, {age}, {event}
    "born_after_mother_death": ("{name} was born after the death of the mother, {other}", "{name} родился(ась) после смерти матери — {other}"),
    "born_after_father_death": ("{name} was born more than a year after the death of the father, {other}", "{name} родился(ась) больше чем через год после смерти отца — {other}"),
    "parent_young": ("{other} was {age} at the birth of {name}", "{other} — {age} лет при рождении ребёнка: {name}"),
    "parent_old": ("{other} was {age} at the birth of {name}", "{other} — {age} лет при рождении ребёнка: {name}"),
    "married_young": ("{name} married at {age}", "{name}: брак в {age} лет"),
    "long_life": ("{name} lived {age} years — check the dates", "{name}: прожил(а) {age} лет — проверьте даты"),
    "unconnected": ("{name} is not connected to the tree", "{name} не связан(а) с древом"),
    "no_documents": ("{name}: not a single document", "{name}: нет ни одного документа"),
    "event_no_source": ("{name}: {event} date without a document", "{name}: дата события «{event}» без документа"),
    "no_dates": ("{name}: no dates of birth or death", "{name}: нет дат рождения и смерти"),
    "family_no_source": ("{name}: the family has no document", "{name}: у семьи нет документа"),
    "no_sex": ("{name}: sex not set", "{name}: не указан пол"),
    "unused_source": ("{name}: nobody refers to this document", "{name}: на документ никто не ссылается"),
    "place_no_coords": ("{name}: no coordinates for the map", "{name}: нет координат для карты"),
}
EVENTS = {"birth": ("birth", "рождение"), "death": ("death", "смерть"), "marriage": ("marriage", "брак")}


def year(ev, exact=False):
    """The year of an event; with exact=True only for dates that are not 'before/after/between'."""
    d = str((ev or {}).get("date") or "")
    if exact and d.startswith(("BEF", "AFT", "BET", "FROM")):
        return None
    m = re.search(r"\d{4}", d)
    return int(m[0]) if m else None


def _refs(obj, out):
    """Every S## mentioned anywhere in obj (lists of ids and texts)."""
    if isinstance(obj, dict):
        for v in obj.values():
            _refs(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _refs(v, out)
    elif isinstance(obj, str):
        out.update(SRC_IN_TEXT.findall(obj))


def hints(data):
    people = {p["id"]: p for p in data.get("people", [])}
    fams = data.get("families", [])
    out = []

    def add(code, kind, rid, **params):
        out.append({"code": code, "kind": kind, "id": rid, "params": params})

    name = lambda pid: people[pid].get("display_name") or pid   # noqa: E731
    parents = collections.defaultdict(list)
    for f in fams:
        for c in f.get("children", []) + f.get("adopted_children", []):
            parents[c].append(f)

    for pid, p in people.items():
        if p.get("placeholder"):
            continue
        b, d = year(p.get("birth"), True), year(p.get("death"), True)
        if not (p.get("birth") or {}).get("date") and not (p.get("death") or {}).get("date"):
            add("no_dates", "people", pid, name=name(pid))
        if p.get("sex") not in ("M", "F"):
            add("no_sex", "people", pid, name=name(pid))
        refs = set()
        _refs({k: v for k, v in p.items() if k != "id"}, refs)
        if not refs:
            add("no_documents", "people", pid, name=name(pid))
        else:
            for ev in ("birth", "death"):
                e = p.get(ev) or {}
                if e.get("date") and not e.get("source_ids"):
                    add("event_no_source", "people", pid, name=name(pid), event=ev)
        if b and d and d - b > 105:
            add("long_life", "people", pid, name=name(pid), age=d - b)
        for f in parents.get(pid, []):
            if pid in f.get("adopted_children", []):
                continue
            for par in f.get("partners", []):
                q = people.get(par)
                if not q or not b:
                    continue
                qb, qd = year(q.get("birth"), True), year(q.get("death"), True)
                if qd and q.get("sex") == "F" and b > qd:
                    add("born_after_mother_death", "people", pid, name=name(pid), other=name(par))
                if qd and q.get("sex") == "M" and b > qd + 1:
                    add("born_after_father_death", "people", pid, name=name(pid), other=name(par))
                if qb:
                    age = b - qb
                    if age < 14:
                        add("parent_young", "people", par, name=name(pid), other=name(par), age=age)
                    elif age > (55 if q.get("sex") == "F" else 75):
                        add("parent_old", "people", par, name=name(pid), other=name(par), age=age)

    for f in fams:
        partners = [x for x in f.get("partners", []) if x in people]
        m = year(f.get("marriage"), True)
        for x in partners:
            xb = year(people[x].get("birth"), True)
            if m and xb and m - xb < 15:
                add("married_young", "people", x, name=name(x), age=m - xb)
        if (partners or f.get("children")) and not f.get("source_ids") and not (f.get("marriage") or {}).get("source_ids"):
            title = " + ".join(name(x) for x in partners) or f["id"]
            add("family_no_source", "families", f["id"], name=title)

    # people the root cannot reach through families
    root = data.get("root_person_id")
    if root in people:
        seen, todo = {root}, [root]
        links = collections.defaultdict(set)
        for f in fams:
            group = f.get("partners", []) + f.get("children", []) + f.get("adopted_children", [])
            for x in group:
                links[x].update(group)
        while todo:
            for y in links[todo.pop()]:
                if y not in seen:
                    seen.add(y)
                    todo.append(y)
        for pid, p in people.items():
            if pid not in seen and not p.get("placeholder") and p.get("research_status") != "unlinked_candidate":
                add("unconnected", "people", pid, name=name(pid))

    used = set()
    _refs({k: v for k, v in data.items() if k not in ("sources", "corrections", "research_log")}, used)
    for s in data.get("sources", []):
        _refs([s.get("scope"), s.get("merged_into")], used)
    for s in data.get("sources", []):
        if s["id"] not in used and not s.get("hidden") and not s.get("merged_into"):
            add("unused_source", "sources", s["id"], name=s.get("title") or s["id"])
    for pl in data.get("places", []):
        if "lat" not in pl:
            add("place_no_coords", "places", pl.get("slug"), name=pl.get("name") or pl.get("slug"))

    rank = {c: i for i, c in enumerate(CODES)}
    out.sort(key=lambda h: rank[h["code"]])
    return out


def text(h, lang="en"):
    en, ru = HINTS[h["code"]]
    params = dict(h["params"])
    if "event" in params:
        params["event"] = EVENTS[params["event"]][1 if lang == "ru" else 0]
    return (ru if lang == "ru" else en).format(**params)
