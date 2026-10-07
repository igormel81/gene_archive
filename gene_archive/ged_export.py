"""GEDCOM 7.0 export of the (already published, privacy-filtered) data.

The file is offered on the Archive page as family_tree.ged for MyHeritage, Gramps,
Ancestry, Geni and other genealogy programs.
"""
import datetime
import re

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def ged_date(value):
    """ISO dates → GEDCOM ("1899-10-09" → "9 OCT 1899"); GEDCOM phrases pass through."""
    value = str(value).strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", value)
    if m:
        return f"{int(m[3])} {MONTHS[int(m[2]) - 1]} {m[1]}"
    m = re.fullmatch(r"(\d{4})-(\d{2})", value)
    if m:
        return f"{MONTHS[int(m[2]) - 1]} {m[1]}"
    return value


def _text(level, tag, value, lines):
    """A line with a possibly multi-line value: continuation lines become CONT."""
    parts = str(value).replace("\r", "").split("\n")
    first = parts[0]
    if first.startswith("@"):
        first = "@" + first   # GEDCOM 7: a leading @ in a text value is doubled
    lines.append(f"{level} {tag} {first}".rstrip())
    for p in parts[1:]:
        lines.append(f"{level + 1} CONT {p}".rstrip())


def _event(lines, tag, ev, sources):
    lines.append(f"1 {tag}")
    if ev.get("date"):
        lines.append(f"2 DATE {ged_date(ev['date'])}")
    if ev.get("place_as_recorded"):
        _text(2, "PLAC", ev["place_as_recorded"], lines)
    if ev.get("note"):
        _text(2, "NOTE", ev["note"], lines)
    for s in ev.get("source_ids", []):
        if s in sources:
            lines.append(f"2 SOUR @{s}@")


def build(data, title="Family archive", today=None):
    today = today or datetime.date.today()
    people = {p["id"]: p for p in data["people"]}
    sources = {s["id"] for s in data["sources"]}
    lines = ["0 HEAD", "1 GEDC", "2 VERS 7.0", "1 SOUR GENE_ARCHIVE", "2 NAME gene-archive",
             f"1 DATE {today.day} {MONTHS[today.month - 1]} {today.year}"]
    _text(1, "NOTE", title, lines)
    famc, fams = {}, {}
    for f in data["families"]:
        for x in f.get("partners", []):
            fams.setdefault(x, []).append(f["id"])
        for c in f.get("children", []):
            famc.setdefault(c, []).append((f["id"], None))
        for c in f.get("adopted_children", []):
            famc.setdefault(c, []).append((f["id"], "ADOPTED"))

    for p in data["people"]:
        pid = p["id"]
        lines.append(f"0 @{pid}@ INDI")
        name = f"{p.get('given_names', '')} /{p['surname']}/" if p.get("surname") else p.get("given_names") or p["display_name"]
        _text(1, "NAME", name.strip(), lines)
        for a in p.get("aliases", []):
            _text(1, "NAME", a, lines)
            lines.append("2 TYPE AKA")
        lines.append(f"1 SEX {p.get('sex', 'U')}")
        for key, tag in (("birth", "BIRT"), ("death", "DEAT"), ("burial", "BURI")):
            if p.get(key):
                _event(lines, tag, p[key], sources)
            for alt in p.get(f"{key}_alternatives", []):
                _event(lines, tag, alt, sources)
        for r in p.get("residences", []):
            lines.append("1 RESI")
            if r.get("date"):
                _text(2, "NOTE", r["date"], lines)   # free-text period, not a GEDCOM date
            if r.get("place"):
                _text(2, "PLAC", r["place"], lines)
            for s in r.get("source_ids", []):
                if s in sources:
                    lines.append(f"2 SOUR @{s}@")
        for fid in fams.get(pid, []):
            lines.append(f"1 FAMS @{fid}@")
        for fid, pedi in famc.get(pid, []):
            lines.append(f"1 FAMC @{fid}@")
            if pedi:
                lines.append(f"2 PEDI {pedi}")
        if p.get("relation"):
            _text(1, "NOTE", "Relation: " + p["relation"], lines)
        if p.get("research_status") == "unlinked_candidate":
            _text(1, "NOTE", "Possible relative, link not proven. " + (p.get("research_note") or ""), lines)
        for n in p.get("notes", []):
            _text(1, "NOTE", n, lines)
        for s in p.get("identity_source_ids", []):
            if s in sources:
                lines.append(f"1 SOUR @{s}@")

    for f in data["families"]:
        lines.append(f"0 @{f['id']}@ FAM")
        for pid in f.get("partners", []):
            lines.append(f"1 {'WIFE' if people[pid].get('sex') == 'F' else 'HUSB'} @{pid}@")
        for c in f.get("children", []) + f.get("adopted_children", []):
            lines.append(f"1 CHIL @{c}@")
        if f.get("marriage"):
            _event(lines, "MARR", f["marriage"], sources)
        elif f.get("relation") in ("spouses", "divorced"):
            lines.append("1 MARR Y")
        if f.get("relation") == "divorced":
            lines.append("1 DIV Y")
        if f.get("probable_note"):
            _text(1, "NOTE", f["probable_note"], lines)
        for n in f.get("notes", []):
            _text(1, "NOTE", n, lines)
        for s in f.get("source_ids", []):
            if s in sources:
                lines.append(f"1 SOUR @{s}@")

    for s in data["sources"]:
        lines.append(f"0 @{s['id']}@ SOUR")
        _text(1, "TITL", s["title"], lines)
        if s.get("locator"):
            _text(1, "NOTE", "Location: " + s["locator"], lines)
        if s.get("url"):
            _text(1, "NOTE", "Online: " + s["url"], lines)
        if s.get("file"):
            _text(1, "NOTE", "Copy in the archive: " + s["file"], lines)
        if s.get("scope"):
            _text(1, "NOTE", s["scope"], lines)
    lines.append("0 TRLR")
    return "\n".join(lines) + "\n"
