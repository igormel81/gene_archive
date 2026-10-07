"""Living people: who they are and what is removed before publishing.

A person counts as living when `living` is not set explicitly and
  * there is no death date and no burial, and
  * the birth year is within `living_years` (default 100) of today, or — with no birth date —
    the person belongs to the generation of the root person's parents or younger.
Dead ancestors without dates stay public: the older generations are the point of the archive.

For a living person only the name, sex and relation stay on the site; dates, places, notes,
aliases, profiles and documents are removed, and documents that concern only living people
are not published at all.
"""
import collections
import datetime
import re

KEEP_FOR_LIVING = ("id", "given_names", "surname", "display_name", "sex", "relation", "placeholder", "living")
SRC_IN_TEXT = re.compile(r"\bS\d+\b")


def generations(data, root):
    """Generation of each person relative to `root`: parents +1, children -1, spouses equal."""
    gen = {root: 0}
    todo = collections.deque([root])
    fams = data["families"]
    while todo:
        x = todo.popleft()
        for f in fams:
            kids = f.get("children", []) + f.get("adopted_children", [])
            if x in f["partners"]:
                for y in f["partners"]:
                    if y not in gen:
                        gen[y] = gen[x]; todo.append(y)
                for y in kids:
                    if y not in gen:
                        gen[y] = gen[x] - 1; todo.append(y)
            if x in kids:
                for y in f["partners"]:
                    if y not in gen:
                        gen[y] = gen[x] + 1; todo.append(y)
    return gen


def living_people(data, root=None, living_years=100, today=None):
    root = root or data.get("root_person_id")
    year_now = (today or datetime.date.today()).year
    gen = generations(data, root) if root else {}
    living = set()
    for p in data["people"]:
        if isinstance(p.get("living"), bool):
            if p["living"]:
                living.add(p["id"])
            continue
        death, burial = p.get("death") or {}, p.get("burial") or {}
        if death or burial.get("place_as_recorded") or burial.get("date"):
            continue   # any death or burial record (even without a date) means not living
        m = re.search(r"\d{4}", str((p.get("birth") or {}).get("date", "")))
        if m:
            if int(m[0]) > year_now - living_years:
                living.add(p["id"])
        elif gen.get(p["id"], 0) <= 1:
            living.add(p["id"])
    return living


def _mentions(obj):
    return set(SRC_IN_TEXT.findall(str(obj)))


def redact(data, living):
    """Returns a copy of data without private details of living people."""
    if not living:
        return data
    out = dict(data)
    people = []
    private_src, public_src = set(), set()
    for p in data["people"]:
        refs = set(p.get("identity_source_ids", [])) | set(p.get("source_ids", [])) | _mentions(
            [p.get(k) for k in p if k not in ("id",)])
        if p["id"] in living:
            private_src |= refs
            q = {k: p[k] for k in KEEP_FOR_LIVING if k in p}
            q["notes"] = []
            q["living"] = True
            people.append(q)
        else:
            public_src |= refs
            people.append(p)
    out["people"] = people
    families = []
    for f in data["families"]:
        # a marriage concerns both partners: if either of them is living, its details stay private
        if any(x in living for x in f.get("partners", [])):
            private_src |= set(f.get("source_ids", [])) | _mentions(f)
            f = {k: v for k, v in f.items() if k not in ("marriage", "notes", "source_ids", "probable_note")}
            f["source_ids"] = []
        else:
            public_src |= set(f.get("source_ids", [])) | _mentions(f)
        families.append(f)
    out["families"] = families
    for pl in data.get("places", []):
        public_src |= set(pl.get("sources", [])) | _mentions(pl)
    # a document is private when only living people (or couples) refer to it
    hidden = private_src - public_src
    out["sources"] = [s for s in data["sources"] if s["id"] not in hidden]
    out["places"] = [dict(pl, people=[x for x in pl.get("people", []) if x not in living],
                          timeline=[dict(t, people=[x for x in t.get("people", []) if x not in living])
                                    for t in pl.get("timeline", [])])
                     for pl in data.get("places", [])]
    out["corrections"] = [c for c in data.get("corrections", []) if c.get("person_id") not in living]
    out["research_leads"] = [x for x in data.get("research_leads", []) if x.get("person_id") not in living]
    return strip_sources(out, hidden)


def strip_sources(data, hidden):
    """Removes ids of hidden documents from every list in the data (texts keep their wording)."""
    if not hidden:
        return data

    def walk(v):
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v if not (isinstance(x, str) and x in hidden)]
        if isinstance(v, str) and SRC_IN_TEXT.search(v):
            # "(S12, S40)" → "(S40)"; a bare hidden S12 in running text disappears
            v = re.sub(r"\b(S\d+)\b", lambda mm: "" if mm[1] in hidden else mm[1], v)
            v = re.sub(r"\(\s*[,;\s]*\)", "", re.sub(r"\(\s*[,;]\s*", "(", re.sub(r"[,;]\s*\)", ")", re.sub(r",\s*,", ",", v))))
            return re.sub(r"\s{2,}", " ", v).replace(" .", ".").replace(" ,", ",")
        return v
    out = walk({k: v for k, v in data.items() if k != "sources"})
    out["sources"] = [walk(s) for s in data["sources"] if s["id"] not in hidden]
    return out


def without_hidden(data):
    """Removes documents the family asked to hide (`hidden: true`) and merged backs (`merged_into`)."""
    hidden = {s["id"] for s in data["sources"] if s.get("hidden") or s.get("merged_into")}
    return strip_sources(data, hidden)
