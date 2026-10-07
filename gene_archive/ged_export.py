"""GEDCOM export of the (already published, privacy-filtered) data.

Two versions:
* 5.5.1 (default) — what MyHeritage, Ancestry, Geni, Gramps, RootsMagic, Family Tree Maker and most
  other programs read reliably: lines up to 255 characters (long texts split with CONC, new lines
  with CONT), every "@" in a text doubled, a submitter record.
* 7.0 — the current standard: no line-length limit, only a leading "@" doubled.

The file is offered on the Archive page as family_tree.ged; `gene gedcom` writes it anywhere.
"""
import datetime
import re

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
VERSIONS = ("5.5.1", "7.0")
MAX_LINE = 240   # 5.5.1 allows 255 per line; some programs count bytes, so pieces are measured in UTF-8 bytes


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


def _chunks(text, size):
    """Splits a long line for CONC into pieces of at most `size` UTF-8 bytes, never starting or ending
    a piece on a space: many programs trim spaces at line ends, which would glue words together."""
    out = []
    while len(text.encode()) > size:
        cut = len(text.encode()[:size].decode("utf-8", "ignore"))   # whole characters that fit
        while cut > 1 and (text[cut - 1] == " " or text[cut] == " "):
            cut -= 1
        out.append(text[:cut])
        text = text[cut:]
    out.append(text)
    return out


class Writer:
    def __init__(self, version):
        if version not in VERSIONS:
            raise ValueError(f"GEDCOM version must be one of {VERSIONS}")
        self.version = version
        self.lines = []

    def line(self, level, tag, value=None):
        self.lines.append(f"{level} {tag}" + (f" {value}" if value not in (None, "") else ""))

    def text(self, level, tag, value):
        """A line with a text value: new lines become CONT, long lines (5.5.1) are split with CONC."""
        value = str(value).replace("\r", "")
        if self.version == "5.5.1":
            value = value.replace("@", "@@")
        elif value.startswith("@"):
            value = "@" + value
        parts = value.split("\n")
        for n, part in enumerate(parts):
            pieces = _chunks(part, MAX_LINE) if self.version == "5.5.1" else [part]
            for k, piece in enumerate(pieces):
                if n == 0 and k == 0:
                    self.line(level, tag, piece)
                else:
                    self.line(level + 1, "CONT" if k == 0 else "CONC", piece)


def _event(w, tag, ev, sources):
    w.line(1, tag)
    if ev.get("date"):
        w.line(2, "DATE", ged_date(ev["date"]))
    if ev.get("place_as_recorded"):
        w.text(2, "PLAC", ev["place_as_recorded"])
    if ev.get("note"):
        w.text(2, "NOTE", ev["note"])
    for s in ev.get("source_ids", []):
        if s in sources:
            w.line(2, "SOUR", f"@{s}@")


def build(data, title="Family archive", today=None, version="5.5.1"):
    today = today or datetime.date.today()
    w = Writer(version)
    people = {p["id"]: p for p in data["people"]}
    sources = {s["id"] for s in data["sources"]}
    w.line(0, "HEAD")
    w.line(1, "GEDC")
    w.line(2, "VERS", version)
    if version == "5.5.1":
        w.line(2, "FORM", "LINEAGE-LINKED")
        w.line(1, "CHAR", "UTF-8")
    w.line(1, "SOUR", "GENE_ARCHIVE")
    w.line(2, "NAME", "gene-archive")
    w.line(1, "DATE", f"{today.day} {MONTHS[today.month - 1]} {today.year}")
    if version == "5.5.1":
        w.line(1, "SUBM", "@SUBM1@")
    w.text(1, "NOTE", title)

    famc, fams = {}, {}
    for f in data["families"]:
        for x in f.get("partners", []):
            fams.setdefault(x, []).append(f["id"])
        for c in f.get("children", []):
            famc.setdefault(c, []).append((f["id"], None))
        for c in f.get("adopted_children", []):
            famc.setdefault(c, []).append((f["id"], "adopted"))

    for p in data["people"]:
        pid = p["id"]
        w.line(0, f"@{pid}@ INDI")
        name = f"{p.get('given_names', '')} /{p['surname']}/" if p.get("surname") else p.get("given_names") or p["display_name"]
        w.text(1, "NAME", name.strip())
        if p.get("given_names"):
            w.text(2, "GIVN", p["given_names"])
        if p.get("surname"):
            w.text(2, "SURN", p["surname"])
        for a in p.get("aliases", []):
            w.text(1, "NAME", a)
            w.line(2, "TYPE", "aka" if version == "5.5.1" else "AKA")
        w.line(1, "SEX", p.get("sex", "U"))
        for key, tag in (("birth", "BIRT"), ("death", "DEAT"), ("burial", "BURI")):
            if p.get(key):
                _event(w, tag, p[key], sources)
            for alt in p.get(f"{key}_alternatives", []):
                _event(w, tag, alt, sources)
        for r in p.get("residences", []):
            w.line(1, "RESI")
            if r.get("place"):
                w.text(2, "PLAC", r["place"])
            if r.get("date"):
                w.text(2, "NOTE", r["date"])   # a free-text period, not a GEDCOM date
            for s in r.get("source_ids", []):
                if s in sources:
                    w.line(2, "SOUR", f"@{s}@")
        for fid in fams.get(pid, []):
            w.line(1, "FAMS", f"@{fid}@")
        for fid, pedi in famc.get(pid, []):
            w.line(1, "FAMC", f"@{fid}@")
            if pedi:
                w.line(2, "PEDI", pedi if version == "5.5.1" else pedi.upper())
        if p.get("relation"):
            w.text(1, "NOTE", "Relation: " + p["relation"])
        if p.get("research_status") == "unlinked_candidate":
            w.text(1, "NOTE", "Possible relative, link not proven. " + (p.get("research_note") or ""))
        for n in p.get("notes", []):
            w.text(1, "NOTE", n)
        for s in p.get("identity_source_ids", []):
            if s in sources:
                w.line(1, "SOUR", f"@{s}@")

    for f in data["families"]:
        w.line(0, f"@{f['id']}@ FAM")
        for pid in f.get("partners", []):
            w.line(1, "WIFE" if people[pid].get("sex") == "F" else "HUSB", f"@{pid}@")
        for c in f.get("children", []) + f.get("adopted_children", []):
            w.line(1, "CHIL", f"@{c}@")
        if f.get("marriage"):
            _event(w, "MARR", f["marriage"], sources)
        elif f.get("relation") in ("spouses", "divorced"):
            w.line(1, "MARR", "Y")
        if f.get("relation") == "divorced":
            w.line(1, "DIV", "Y")
        if f.get("probable_note"):
            w.text(1, "NOTE", f["probable_note"])
        for n in f.get("notes", []):
            w.text(1, "NOTE", n)
        for s in f.get("source_ids", []):
            if s in sources:
                w.line(1, "SOUR", f"@{s}@")

    for s in data["sources"]:
        w.line(0, f"@{s['id']}@ SOUR")
        w.text(1, "TITL", s["title"])
        if s.get("locator"):
            w.text(1, "PUBL", s["locator"])
        if s.get("scope"):
            w.text(1, "TEXT", s["scope"])
        if s.get("url"):
            w.text(1, "NOTE", "Online: " + s["url"])
        if s.get("file"):
            w.text(1, "NOTE", "Copy in the archive: " + s["file"])

    if version == "5.5.1":
        w.line(0, "@SUBM1@ SUBM")
        w.text(1, "NAME", title)
    w.line(0, "TRLR")
    return "\n".join(w.lines) + "\n"
