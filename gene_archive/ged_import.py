"""Import a GEDCOM file (5.5, 5.5.1 or 7.0) into the ``family_tree.json`` format.

Usage::

    python -m gene_archive.ged_import tree.ged -o family_tree.json [--root I12] [--force]

or from Python::

    from gene_archive.ged_import import import_gedcom
    data = import_gedcom("tree.ged")

The importer is deliberately forgiving: anything it cannot map is reported as a
warning instead of aborting the import. Records are renumbered ``I1..In``,
``F1..Fn``, ``S1..Sn`` in file order; the original cross-reference id is kept in
a ``gedcom_id`` field so every record can be traced back to the GEDCOM file.

See ``docs/data-format.md`` for the target format.
"""

from __future__ import annotations

import argparse
import calendar
import datetime
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

__all__ = ["import_gedcom", "import_gedcom_with_warnings", "convert_date", "parse_gedcom", "main"]

SCHEMA_VERSION = "1.0"

MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()

# Individual events and attributes that become `residences` entries.
RESIDENCE_KINDS = {
    "RESI": "residence", "OCCU": "occupation", "EDUC": "education", "EMIG": "emigration",
    "IMMI": "immigration", "CENS": "census", "EVEN": "event", "FACT": "fact",
    "NATU": "naturalization", "RETI": "retirement", "GRAD": "graduation", "RELI": "religion",
    "PROP": "property", "TITL": "title", "DSCR": "description", "NATI": "nationality",
    "CAST": "caste", "NCHI": "children count", "NMR": "marriages count", "IDNO": "identity number",
    "SSN": "social security number", "ADOP": "adoption", "CONF": "confirmation",
    "FCOM": "first communion", "BARM": "bar mitzvah", "BASM": "bas mitzvah", "BLES": "blessing",
    "CHRA": "adult christening", "ORDN": "ordination", "PROB": "probate", "WILL": "will",
    "CREM": "cremation", "MILI": "military service", "_MILT": "military service",
    "_MILI": "military service", "_DEG": "degree", "_ELEC": "election", "_EMPLOY": "employment",
    "_MDCL": "medical", "_HEIG": "height", "_WEIG": "weight",
    # Only used when the event is not mapped to birth/burial (see Importer._person).
    "CHR": "baptism", "BAPM": "baptism", "BIRT": "birth", "DEAT": "death", "BURI": "burial",
}

# Family events other than MARR/DIV: summarized in the family notes.
FAMILY_EVENT_LABELS = {
    "ENGA": "Engagement", "MARB": "Marriage banns", "MARC": "Marriage contract",
    "MARL": "Marriage licence", "MARS": "Marriage settlement", "ANUL": "Annulment",
    "DIVF": "Divorce filed", "EVEN": "Event", "RESI": "Residence", "CENS": "Census",
    "FACT": "Fact", "NCHI": "Number of children",
}

# Tags that carry no information we can use; they are skipped without a warning.
IGNORED_TAGS = {
    "CHAN", "CREA", "RIN", "REFN", "UID", "_UID", "AFN", "RFN", "SUBM", "ANCI", "DESI",
    "_UPD", "_FSFTID", "EXID", "_PRIM", "_CUTOUT", "_PHOTO_RIN", "_FILESIZE", "_TYPE",
    "FAMS", "FAMC", "CONT", "CONC", "SDATE", "LANG", "PHRASE", "TIME", "_TIME", "QUAY",
    "_APID", "_LKID", "_FREL", "_MREL", "PEDI", "STAT", "RESN", "ROLE", "ASSO", "ALIA",
    "_GUID", "SNOTE", "NOTE", "SOUR", "OBJE", "CRMN",
}

# GEDCOM 7.0 and GEDCOM 5.5 encode citations and notes the same way, so one
# list of sub-tags handled inside events is enough.
EVENT_SUBTAGS = {"DATE", "PLAC", "ADDR", "SOUR", "NOTE", "SNOTE", "AGE", "TYPE", "CAUS",
                 "AGNC", "OBJE", "HUSB", "WIFE", "FAMC", "PHON", "EMAIL", "WWW", "FAX",
                 "RELI", "_PLAC", "ROLE"}

PRIVATE_RESN = {"PRIVACY", "CONFIDENTIAL"}


# --------------------------------------------------------------------------- parsing


@dataclass
class Node:
    """One GEDCOM line with its sub-structure."""

    level: int
    tag: str
    value: str = ""
    xref: str | None = None
    children: list["Node"] = field(default_factory=list)
    line: int = 0

    def first(self, tag: str) -> "Node | None":
        for child in self.children:
            if child.tag == tag:
                return child
        return None

    def all(self, *tags: str) -> list["Node"]:
        return [c for c in self.children if c.tag in tags]

    def text(self) -> str:
        """The value with CONT/CONC continuation lines applied."""
        parts = [self.value]
        for child in self.children:
            if child.tag == "CONT":
                parts.append("\n" + child.value)
            elif child.tag == "CONC":
                parts.append(child.value)
        return "".join(parts)

    def sub_text(self, tag: str) -> str:
        node = self.first(tag)
        return node.text().strip() if node else ""

    @property
    def pointer(self) -> str | None:
        """The value if it is a pointer like ``@I1@`` (``@VOID@`` counts as no pointer)."""
        v = self.value.strip()
        if re.fullmatch(r"@[^@\s#][^@]*@", v) and v.upper() != "@VOID@":
            return v
        return None


LINE_RE = re.compile(r"^\s*(\d{1,2})\s+(?:(@[^@]+@)\s+)?([A-Za-z0-9_]+)(?: (.*))?$")


def parse_gedcom(text: str, warnings: list[str] | None = None) -> list[Node]:
    """Parse GEDCOM text into a list of level-0 records.

    Tolerates blank lines, CRLF, leading whitespace and tags without a value.
    A line that is not a GEDCOM line is treated as a continuation of the previous
    value (some programs wrap long notes without CONT); it is reported as a warning.
    """
    warnings = warnings if warnings is not None else []
    records: list[Node] = []
    stack: list[Node] = []
    bad_lines = 0
    level_jumps = 0
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        m = LINE_RE.match(raw)
        if not m:
            bad_lines += 1
            if stack:
                stack[-1].children.append(Node(stack[-1].level + 1, "CONT", raw.strip(), line=number))
            continue
        level = int(m.group(1))
        value = m.group(4) or ""
        if value.startswith("@@"):          # GEDCOM escape for a leading "@"
            value = value[1:]
        node = Node(level, m.group(3).upper(), value, m.group(2), line=number)
        if level == 0:
            records.append(node)
            stack = [node]
            continue
        if not stack:
            bad_lines += 1
            continue
        while stack and stack[-1].level >= level:
            stack.pop()
        if not stack:
            bad_lines += 1
            continue
        if level > stack[-1].level + 1:
            level_jumps += 1
        stack[-1].children.append(node)
        stack.append(node)
    if bad_lines:
        warnings.append(f"{bad_lines} line(s) were not valid GEDCOM lines; "
                        "they were attached to the previous value or skipped")
    if level_jumps:
        warnings.append(f"{level_jumps} line(s) skipped a level number; attached to the nearest parent")
    return records


def decode_gedcom(data: bytes, warnings: list[str]) -> str:
    """Decode GEDCOM bytes: UTF-8 (with or without BOM), UTF-16, else a guess with a warning."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    head = data[:4000].decode("ascii", errors="ignore").upper()
    m = re.search(r"^\s*1\s+CHAR\s+(\S+)", head, re.M)
    declared = m.group(1) if m else "unknown"
    encoding = "cp1251" if _looks_cyrillic(data) or "1251" in declared or "CYR" in declared else "latin-1"
    if declared == "ANSEL":
        warnings.append("File is in ANSEL encoding, which is not supported; decoded as latin-1 — "
                        "accented letters may be wrong. Re-export as UTF-8 if possible.")
        encoding = "latin-1"
    else:
        warnings.append(f"File is not UTF-8 (declared CHAR {declared}); decoded as {encoding}. "
                        "Check names with non-Latin letters.")
    return data.decode(encoding, errors="replace")


def _looks_cyrillic(data: bytes) -> bool:
    """Cyrillic cp1251 text has runs of high bytes; Western latin-1 has isolated ones."""
    high = [i for i, b in enumerate(data) if b >= 0xC0]
    if not high:
        return False
    adjacent = sum(1 for a, b in zip(high, high[1:]) if b == a + 1)
    return adjacent / len(high) > 0.4


# --------------------------------------------------------------------------- dates

_SIMPLE_DATE = re.compile(r"(?:(\d{1,2}) )?(?:([A-Z]{3}) )?(\d{3,4})")


def _simple(text: str) -> tuple[str, str | None, str | None] | None:
    """Parse ``[day] [MON] year`` into (year, month, day) strings, validating the day."""
    m = _SIMPLE_DATE.fullmatch(text)
    if not m:
        return None
    day, mon, year = m.group(1), m.group(2), m.group(3)
    if mon is not None and mon not in MONTHS:
        return None
    if day is not None and mon is None:
        return None
    if day is not None:
        last = calendar.monthrange(int(year), MONTHS.index(mon) + 1)[1]
        if not 1 <= int(day) <= last:
            return None
        day = str(int(day))
    return year, mon, day


def _gedcom_form(parts: tuple[str, str | None, str | None]) -> str:
    year, mon, day = parts
    return " ".join(x for x in (day, mon, year) if x)


def convert_date(raw: str) -> str | None:
    """Convert a GEDCOM date to the engine format, or return None if it cannot be expressed.

    ``9 OCT 1899`` -> ``1899-10-09``; ``OCT 1899`` -> ``1899-10``; ``1899`` stays;
    qualified forms (ABT/CAL/EST/BEF/AFT, BET…AND, FROM…TO) keep the GEDCOM form with
    the month upper-cased and the day without a leading zero.
    """
    s = re.sub(r"\s+", " ", raw.strip().upper())
    # Gregorian is the default calendar; any other calendar cannot be shown as is.
    s = re.sub(r"^@#DGREGORIAN@ ?|^GREGORIAN ", "", s)
    s = re.sub(r"(?<=[A-Z]) @#DGREGORIAN@ ?|(?<=[A-Z]) GREGORIAN ", " ", s)
    if not s or "@#" in s or "(" in s or "/" in s:
        return None
    iso = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", s)
    if iso:
        try:
            datetime.date(int(iso[1]), int(iso[2] or 1), int(iso[3] or 1))
        except ValueError:
            return None
        return s
    simple = _simple(s)
    if simple:
        year, mon, day = simple
        out = year.zfill(4)
        if mon:
            out += f"-{MONTHS.index(mon) + 1:02d}"
        if day:
            out += f"-{int(day):02d}"
        return out
    m = re.fullmatch(r"(ABT|CAL|EST|BEF|AFT) (.+)", s)
    if m:
        inner = _simple(m.group(2))
        return f"{m.group(1)} {_gedcom_form(inner)}" if inner else None
    m = re.fullmatch(r"BET (.+) AND (.+)", s)
    if m:
        a, b = _simple(m.group(1)), _simple(m.group(2))
        return f"BET {_gedcom_form(a)} AND {_gedcom_form(b)}" if a and b else None
    m = re.fullmatch(r"FROM (.+?)(?: TO (.+))?", s)
    if m:
        a = _simple(m.group(1))
        b = _simple(m.group(2)) if m.group(2) else None
        if not a or (m.group(2) and not b):
            return None
        return f"FROM {_gedcom_form(a)}" + (f" TO {_gedcom_form(b)}" if b else "")
    return None


# --------------------------------------------------------------------------- importer


def _basename(path: str) -> str:
    """File name of a GEDCOM FILE value: Windows or POSIX path, or a file: URI."""
    if path.lower().startswith("file:"):
        path = unquote(urlparse(path).path)
    return re.split(r"[\\/]", path.rstrip("\\/"))[-1]


def _paragraphs(text: str) -> list[str]:
    paras = []
    for chunk in re.split(r"\n\s*\n", text.replace("\r", "")):
        para = " ".join(line.strip() for line in chunk.split("\n") if line.strip())
        if para:
            paras.append(para)
    return paras


def _name_parts(value: str) -> tuple[str, str, str]:
    """Split ``Given /Surname/ Suffix`` into (given, surname, suffix)."""
    m = re.match(r"^(.*?)/(.*?)/(.*)$", value)
    if not m:
        return value.strip(), "", ""
    return m.group(1).strip(), m.group(2).strip(), m.group(3).strip()


class Importer:
    """Turns parsed GEDCOM records into the family_tree.json dict."""

    def __init__(self, records: list[Node], warnings: list[str]):
        self.records = records
        self.warnings = warnings
        self.unknown: Counter[str] = Counter()
        self.version = "5.5"
        self.indi = [r for r in records if r.tag == "INDI"]
        self.fams = [r for r in records if r.tag == "FAM"]
        self.sour = [r for r in records if r.tag == "SOUR"]
        self.notes = {r.xref: r for r in records if r.tag in ("NOTE", "SNOTE") and r.xref}
        self.repos = {r.xref: r for r in records if r.tag == "REPO" and r.xref}
        self.objes = {r.xref: r for r in records if r.tag == "OBJE" and r.xref}
        self.person_id = {r.xref: f"I{i}" for i, r in enumerate(self.indi, 1) if r.xref}
        self.family_id = {r.xref: f"F{i}" for i, r in enumerate(self.fams, 1) if r.xref}
        self.source_id = {r.xref: f"S{i}" for i, r in enumerate(self.sour, 1) if r.xref}
        self.sources: list[dict] = []
        self.extra_sources: list[dict] = []     # inline citations and media files
        self.media_by_key: dict[str, str] = {}  # OBJE xref or file path -> source id
        self.inline_by_text: dict[str, str] = {}
        self.source_media: dict[str, list[str]] = {}  # SOUR id -> media source ids
        self.files_to_copy: list[str] = []
        head = next((r for r in records if r.tag == "HEAD"), None)
        if head:
            gedc = head.first("GEDC")
            vers = gedc.sub_text("VERS") if gedc else ""
            if vers:
                self.version = vers
        if not records or records[0].tag != "HEAD":
            self.warnings.append("File does not start with a HEAD record; is it a GEDCOM file?")

    # ---- helpers

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def skip_unknown(self, node: Node, known: set[str]) -> None:
        for child in node.children:
            if child.tag not in known and child.tag not in IGNORED_TAGS:
                self.unknown[f"{node.tag}.{child.tag}"] += 1

    def note_text(self, node: Node) -> str:
        """Text of a NOTE/SNOTE node, resolving shared ``@N1@`` notes."""
        ptr = node.pointer
        if ptr:
            shared = self.notes.get(ptr)
            if shared is None:
                self.warn(f"Note {ptr} referenced on line {node.line} does not exist")
                return ""
            return shared.text().strip()
        return node.text().strip()

    def notes_of(self, node: Node) -> list[str]:
        return [t for t in (self.note_text(n) for n in node.all("NOTE", "SNOTE")) if t]

    def new_source(self, record: dict) -> str:
        sid = f"S{len(self.sour) + len(self.extra_sources) + 1}"
        record = {"id": sid, **record}
        self.extra_sources.append(record)
        return sid

    def citations(self, node: Node) -> tuple[list[str], list[str]]:
        """Source ids cited by SOUR sub-records of `node`, and citation details (PAGE etc.)."""
        ids: list[str] = []
        details: list[str] = []
        for cite in node.all("SOUR"):
            ptr = cite.pointer
            if ptr:
                sid = self.source_id.get(ptr)
                if sid is None:
                    self.warn(f"Source {ptr} cited on line {cite.line} does not exist")
                    continue
            else:
                text = cite.text().strip()
                if not text:
                    continue
                sid = self.inline_by_text.get(text)
                if sid is None:
                    title = text if len(text) <= 120 else text[:117].rstrip() + "…"
                    sid = self.new_source({"title": title, "kind": "imported_source", "locator": "",
                                           "scope": text if title != text else ""})
                    self.inline_by_text[text] = sid
            ids.append(sid)
            ids.extend(self.source_media.get(sid, []))
            ids.extend(self.media(cite))
            parts = [cite.sub_text("PAGE")]
            data = cite.first("DATA")
            if data:
                parts.append(data.sub_text("TEXT"))
            parts.extend(self.notes_of(cite))
            parts = [p.replace("\n", " ") for p in parts if p]
            if parts:
                details.append(f"{sid}: " + "; ".join(parts))
        return _unique(ids), details

    def media(self, node: Node) -> list[str]:
        """Sources (kind family_photo) for OBJE sub-records of `node`."""
        ids = []
        for obje in node.all("OBJE"):
            ptr = obje.pointer
            target = self.objes.get(ptr) if ptr else obje
            if target is None:
                self.warn(f"Media object {ptr} referenced on line {obje.line} does not exist")
                continue
            key = ptr or None
            if key and key in self.media_by_key:
                ids.append(self.media_by_key[key])
                continue
            title = target.sub_text("TITL")
            for file_node in target.all("FILE"):
                path = file_node.text().strip()
                if not path:
                    continue
                file_key = key or path
                if file_key in self.media_by_key:
                    ids.append(self.media_by_key[file_key])
                    continue
                form = file_node.first("FORM")
                file_title = title or file_node.sub_text("TITL") or (form.sub_text("TITL") if form else "")
                record = {"title": file_title or _basename(path), "kind": "family_photo"}
                if re.match(r"https?://", path, re.I):
                    record["url"] = path
                else:
                    record["file"] = "sources/" + _basename(path)
                    self.files_to_copy.append(path)
                record.update({"locator": "", "scope": "; ".join(self.notes_of(target))})
                sid = self.new_source(record)
                self.media_by_key[file_key] = sid
                ids.append(sid)
                break   # one source per media object; further FILEs are alternative formats
        return ids

    # ---- events

    def event(self, node: Node, who: str, label: str) -> dict:
        """Map a BIRT/DEAT/BURI/MARR-style node to an event dict."""
        ev: dict = {}
        notes: list[str] = []
        raw = node.sub_text("DATE")
        if raw:
            date = convert_date(raw)
            if date:
                ev["date"] = date
            else:
                notes.append(f"date as recorded: {raw}")
                self.warn(f"{who}: {label} date {raw!r} cannot be expressed; kept in the note")
            date_node = node.first("DATE")
            if date_node and date_node.first("PHRASE"):
                notes.append(date_node.sub_text("PHRASE"))
        place = node.sub_text("PLAC") or node.sub_text("ADDR").replace("\n", ", ")
        if place:
            ev["place_as_recorded"] = place
        ids, details = self.citations(node)
        ids += self.media(node)
        for tag, prefix in (("TYPE", ""), ("AGE", "age "), ("CAUS", "cause: "), ("AGNC", "")):
            value = node.sub_text(tag)
            if value:
                notes.append(prefix + value)
        notes.extend(self.notes_of(node))
        notes.extend(details)
        ev["status"] = "documented" if node.first("SOUR") else "family_report"
        if ids:
            ev["source_ids"] = _unique(ids)
        if notes:
            ev["note"] = "; ".join(n.replace("\n", " ") for n in notes)
        self.skip_unknown(node, EVENT_SUBTAGS | {"DATA", "_PRIM"})
        return ev

    def residence(self, node: Node, who: str) -> dict:
        kind = RESIDENCE_KINDS[node.tag]
        type_ = node.sub_text("TYPE")
        if node.tag in ("EVEN", "FACT") and type_:
            kind = type_.lower()
        place = node.sub_text("PLAC") or node.sub_text("ADDR").replace("\n", ", ")
        entry: dict = {"place": place}
        raw = node.sub_text("DATE")
        if raw:
            entry["date"] = re.sub(r"\s+", " ", raw)
        entry["place_event_kind"] = kind
        ids, details = self.citations(node)
        ids += self.media(node)
        if ids:
            entry["source_ids"] = _unique(ids)
        value = node.text().strip().replace("\n", " ")
        notes = []
        if type_ and node.tag not in ("EVEN", "FACT"):
            notes.append(type_)
        if value and value.upper() != "Y":
            notes.append(value)
        for tag, prefix in (("AGE", "age "), ("CAUS", "cause: "), ("AGNC", "")):
            if node.sub_text(tag):
                notes.append(prefix + node.sub_text(tag))
        notes += self.notes_of(node) + details
        if notes:
            entry["note"] = "; ".join(n.replace("\n", " ") for n in notes)
        self.skip_unknown(node, EVENT_SUBTAGS | {"DATA"})
        return entry

    # ---- records

    def source(self, rec: Node, sid: str) -> dict:
        title = rec.sub_text("TITL") or rec.sub_text("ABBR") or f"Source {sid[1:]}"
        locator = []
        if rec.sub_text("PUBL"):
            locator.append(rec.sub_text("PUBL"))
        for repo in rec.all("REPO"):
            ptr = repo.pointer
            name = ""
            if ptr and ptr in self.repos:
                name = self.repos[ptr].sub_text("NAME")
            elif not ptr:
                name = repo.text().strip()
            calns = [c.text().strip() for c in repo.all("CALN") if c.text().strip()]
            text = ", ".join(x for x in [name] + calns if x)
            if text:
                locator.append(text)
        scope = []
        if rec.sub_text("AUTH"):
            scope.append("Author: " + rec.sub_text("AUTH"))
        if rec.sub_text("TEXT"):
            scope.append(rec.sub_text("TEXT"))
        data = rec.first("DATA")
        if data:
            for ev in data.all("EVEN"):
                bits = [ev.value.strip(), ev.sub_text("DATE"), ev.sub_text("PLAC")]
                scope.append("Records: " + ", ".join(b for b in bits if b))
            scope.extend(self.notes_of(data))
        scope.extend(self.notes_of(rec))
        record = {"id": sid, "gedcom_id": rec.xref, "title": title, "kind": "imported_source"}
        for tag in ("WWW", "_LINK", "URL", "_URL"):
            url = rec.sub_text(tag)
            if url:
                record["url"] = url
                break
        record["locator"] = "; ".join(locator).replace("\n", " ")
        record["scope"] = "\n\n".join(scope)
        self.skip_unknown(rec, {"TITL", "ABBR", "PUBL", "REPO", "AUTH", "TEXT", "DATA", "NOTE",
                                "SNOTE", "WWW", "_LINK", "URL", "_URL", "OBJE", "_MEDI"})
        return record

    def person(self, rec: Node, pid: str) -> dict:
        names = rec.all("NAME")
        given, surname = "", ""
        aliases: list[str] = []
        identity: list[str] = []
        citation_notes: list[str] = []
        who = f"{pid} ({rec.xref})"
        for i, name in enumerate(names):
            g, s, suffix = _name_parts(name.text().strip())
            g = g or name.sub_text("GIVN")
            s = s or name.sub_text("SURN")
            if suffix or name.sub_text("NSFX"):
                g = " ".join(x for x in (g, suffix or name.sub_text("NSFX")) if x)
            full = " ".join(x for x in (g, s) if x)
            if i == 0:
                given, surname = g, s
            elif full:
                aliases.append(full)
            for tag in ("_MARNM", "_MAR", "_AKA", "NICK", "_RUFNAME", "_BIRTHNAME", "_MARRIED"):
                for alt in name.all(tag):
                    aliases.append(self._alias(alt.text(), g))
            for tran in name.all("TRAN", "ROMN", "FONE"):
                tg, ts, _ = _name_parts(tran.text().strip())
                aliases.append(" ".join(x for x in (tg, ts) if x))
            ids, details = self.citations(name)
            identity += ids
            citation_notes += details
            self.skip_unknown(name, {"GIVN", "SURN", "NPFX", "NSFX", "SPFX", "NICK", "TYPE", "SOUR",
                                     "NOTE", "SNOTE", "TRAN", "ROMN", "FONE", "_MARNM", "_MAR", "_AKA",
                                     "_RUFNAME", "_BIRTHNAME", "_MARRIED"})
        for tag in ("_MARNM", "NICK", "_AKA", "_BIRTHNAME"):
            for alt in rec.all(tag):
                aliases.append(self._alias(alt.text(), given))
        if not names:
            self.warn(f"{who}: has no NAME")
        display = f"{surname} {given}".strip() if surname else given
        ids, details = self.citations(rec)
        identity += ids + self.media(rec)
        citation_notes += details
        sex = rec.sub_text("SEX").upper()[:1]
        person: dict = {
            "id": pid, "gedcom_id": rec.xref,
            "given_names": given, "surname": surname,
            "display_name": display or "(no name)",
            "sex": sex if sex in ("M", "F") else "U",
        }
        aliases = [a for a in _unique(aliases) if a and a != display and a != f"{given} {surname}".strip()]
        if aliases:
            person["aliases"] = aliases
        if identity:
            person["identity_source_ids"] = _unique(identity)

        residences = []
        for kind, tags in (("birth", ("BIRT",)), ("death", ("DEAT",)), ("burial", ("BURI",))):
            events = rec.all(*tags)
            fallback = None
            if not events and kind == "birth":
                events, fallback = rec.all("CHR", "BAPM"), "baptism (no birth record)"
            if not events and kind == "burial":
                events, fallback = rec.all("CREM"), "cremation"
            mapped = []
            for node in events:
                ev = self.event(node, who, kind)
                if fallback:
                    ev["note"] = fallback + ("; " + ev["note"] if ev.get("note") else "")
                if kind == "death" and "date" not in ev:
                    ev["note"] = "died (date unknown)" + ("; " + ev["note"] if ev.get("note") else "")
                mapped.append(ev)
            if mapped:
                person[kind] = mapped[0]
                if len(mapped) > 1 and kind in ("birth", "death"):
                    person[kind + "_alternatives"] = mapped[1:]
        used = {"BIRT", "DEAT", "BURI"}
        if "birth" in person and not rec.all("BIRT"):
            used |= {"CHR", "BAPM"}
        if "burial" in person and not rec.all("BURI"):
            used.add("CREM")
        for node in rec.children:
            if node.tag in RESIDENCE_KINDS and node.tag not in used:
                residences.append(self.residence(node, who))
        if residences:
            person["residences"] = residences
        notes = []
        for n in rec.all("NOTE", "SNOTE"):
            notes += _paragraphs(self.note_text(n))
        if citation_notes:
            notes.append("Citations: " + "; ".join(citation_notes) + ".")
        person["notes"] = notes
        resn = rec.sub_text("RESN").upper()
        if any(word in resn for word in PRIVATE_RESN):
            person["living"] = True
        self.skip_unknown(rec, {"NAME", "SEX", "NOTE", "SNOTE", "SOUR", "OBJE", "RESN", "_MARNM",
                                "NICK", "_AKA", "_BIRTHNAME"} | set(RESIDENCE_KINDS))
        return person

    @staticmethod
    def _alias(value: str, given: str) -> str:
        """An alternative name; a bare surname (e.g. a married name) gets the given names."""
        g, s, _ = _name_parts(value.strip())
        if s:
            return " ".join(x for x in (g or given, s) if x)
        value = value.strip()
        return f"{given} {value}".strip() if " " not in value else value

    def family(self, rec: Node, fid: str, adopted: set[tuple[str, str]], child_of: dict) -> dict:
        who = f"{fid} ({rec.xref})"
        partners = []
        for tag in ("HUSB", "WIFE"):
            for node in rec.all(tag):
                pid = self.person_id.get(node.pointer or "")
                if pid:
                    partners.append(pid)
                elif node.pointer:
                    self.warn(f"{who}: {tag} {node.pointer} does not exist; skipped")
        children, adopted_children = [], []
        child_nodes = rec.all("CHIL")
        # Children listed only on the INDI side (FAMC) are added as well.
        listed = {n.pointer for n in child_nodes}
        extra = [x for x, fams in child_of.items() if rec.xref in fams and x not in listed]
        for ptr in [n.pointer for n in child_nodes] + extra:
            pid = self.person_id.get(ptr or "")
            if not pid:
                if ptr:
                    self.warn(f"{who}: CHIL {ptr} does not exist; skipped")
                continue
            node = next((n for n in child_nodes if n.pointer == ptr), None)
            ftm_rel = " ".join(node.sub_text(t) for t in ("_FREL", "_MREL")).lower() if node else ""
            if (ptr, rec.xref) in adopted or "adopt" in ftm_rel or "foster" in ftm_rel:
                adopted_children.append(pid)
            else:
                children.append(pid)
        family: dict = {"id": fid, "gedcom_id": rec.xref, "partners": partners[:2],
                        "children": _unique(children), "adopted_children": _unique(adopted_children)}
        if len(partners) > 2:
            self.warn(f"{who}: more than two partners; only the first two were kept")
        marriages = rec.all("MARR")
        divorced = rec.all("DIV", "ANUL")
        if divorced:
            family["relation"] = "divorced"
        elif marriages or len(partners) >= 2:
            family["relation"] = "spouses"
        else:
            family["relation"] = ""
        if marriages:
            family["marriage"] = self.event(marriages[0], who, "marriage")
        ids, details = self.citations(rec)
        ids += self.media(rec)
        family["source_ids"] = ids
        notes = []
        for n in rec.all("NOTE", "SNOTE"):
            notes += _paragraphs(self.note_text(n))
        for node in marriages[1:] + divorced + rec.all(*FAMILY_EVENT_LABELS):
            label = "Marriage" if node.tag == "MARR" else "Divorce" if node.tag == "DIV" \
                else FAMILY_EVENT_LABELS[node.tag]
            ev = self.event(node, who, label.lower())
            bits = [ev.get("date", ""), ev.get("place_as_recorded", ""), ev.get("note", "")]
            bits += [", ".join(ev.get("source_ids", []))]
            text = ", ".join(b for b in bits if b)
            if node.value.strip() and node.value.strip().upper() != "Y":
                text = ", ".join(x for x in (node.value.strip(), text) if x)
            notes.append(f"{label}: {text}." if text else f"{label}.")
        if details:
            notes.append("Citations: " + "; ".join(details) + ".")
        family["notes"] = notes
        self.skip_unknown(rec, {"HUSB", "WIFE", "CHIL", "MARR", "DIV", "NOTE", "SNOTE", "SOUR", "OBJE"}
                          | set(FAMILY_EVENT_LABELS))
        return family

    # ---- top level

    def run(self, root: str | None, filename: str) -> dict:
        self.sources = [self.source(rec, f"S{i}") for i, rec in enumerate(self.sour, 1)]
        # Media attached to SOUR records: separate sources, added wherever the source is cited.
        for rec, src in zip(self.sour, self.sources):
            media = self.media(rec)
            if media:
                self.source_media[src["id"]] = media
        # Adoption is recorded on the child's FAMC link (PEDI adopted/foster).
        adopted: set[tuple[str, str]] = set()
        child_of: dict[str, list[str]] = {}
        for rec in self.indi:
            for famc in rec.all("FAMC"):
                if not famc.pointer:
                    continue
                pedi = famc.sub_text("PEDI").lower()
                if pedi in ("adopted", "foster"):
                    adopted.add((rec.xref, famc.pointer))
                child_of.setdefault(rec.xref, []).append(famc.pointer)
        people = [self.person(rec, self.person_id.get(rec.xref, f"I{i}"))
                  for i, rec in enumerate(self.indi, 1)]
        families = [self.family(rec, self.family_id.get(rec.xref, f"F{i}"), adopted, child_of)
                    for i, rec in enumerate(self.fams, 1)]
        self._check_single_biological_family(families)
        root_id = self._root(root, people)
        for p in people:
            if p["id"] == root_id:
                p["relation"] = "root person"
        for tag, count in Counter(r.tag for r in self.records).items():
            if tag not in ("HEAD", "TRLR", "INDI", "FAM", "SOUR", "NOTE", "SNOTE", "REPO", "OBJE",
                           "SUBM", "SUBN", "_EVDEF", "_TODO", "_PLAC_DEFN", "_PLAC"):
                self.unknown[tag] += count
        if self.unknown:
            summary = ", ".join(f"{tag} ×{n}" for tag, n in sorted(self.unknown.items()))
            self.warn(f"Ignored unsupported tags: {summary}")
        if self.files_to_copy:
            self.warn("Copy these media files into sources/ (they are referenced by name): "
                      + ", ".join(_unique(self.files_to_copy)))
        sources = self.sources + self.extra_sources
        result = f"{len(people)} people, {len(families)} families, {len(sources)} sources imported"
        if self.warnings:
            result += f"; {len(self.warnings)} warning(s)"
        return {
            "schema_version": SCHEMA_VERSION,
            "root_person_id": root_id,
            "people": people,
            "families": families,
            "sources": sources,
            "places": [], "place_groups": [], "place_routes": [],
            "research_leads": [], "corrections": [],
            "research_log": [{"date": datetime.date.today().isoformat(), "action": "GEDCOM import",
                              "result": result + f" (GEDCOM {self.version})", "scope": filename}],
            "surnames": {},
        }

    def _root(self, root: str | None, people: list[dict]) -> str | None:
        if not people:
            self.warn("The file contains no individuals")
            return None
        if root is None:
            return people[0]["id"]
        wanted = root.strip()
        ptr = wanted if wanted.startswith("@") else f"@{wanted}@"
        if ptr in self.person_id:              # the original GEDCOM xref wins
            return self.person_id[ptr]
        if any(p["id"] == wanted for p in people):
            return wanted
        raise ValueError(f"Root person {root!r} not found (neither a GEDCOM xref nor a new id)")

    def _check_single_biological_family(self, families: list[dict]) -> None:
        """A person may be the biological child of only one family with partners."""
        seen: dict[str, str] = {}
        for fam in families:
            if not fam["partners"]:
                continue
            keep = []
            for pid in fam["children"]:
                if pid in seen:
                    fam.setdefault("probable_children", []).append(pid)
                    fam["probable_note"] = f"Also listed as a child of {seen[pid]} in the GEDCOM file"
                    self.warn(f"{pid} is a child of both {seen[pid]} and {fam['id']}; "
                              f"marked as a probable child of {fam['id']}")
                else:
                    seen[pid] = fam["id"]
                    keep.append(pid)
            fam["children"] = keep


def _unique(items: list) -> list:
    return list(dict.fromkeys(x for x in items if x))


# --------------------------------------------------------------------------- public API


def _read_input(path_or_text, warnings: list[str]) -> tuple[str, str]:
    """Return (text, filename) for a path, raw bytes or GEDCOM text."""
    if isinstance(path_or_text, bytes):
        return decode_gedcom(path_or_text, warnings), "(bytes)"
    if isinstance(path_or_text, str) and ("\n" in path_or_text or path_or_text.lstrip("﻿").lstrip().startswith("0 ")):
        return path_or_text.lstrip("﻿"), "(text)"
    path = Path(path_or_text)
    return decode_gedcom(path.read_bytes(), warnings), path.name


def import_gedcom_with_warnings(path_or_text, root: str | None = None) -> tuple[dict, list[str]]:
    """Like :func:`import_gedcom`, but also return the list of warnings."""
    warnings: list[str] = []
    text, filename = _read_input(path_or_text, warnings)
    records = parse_gedcom(text, warnings)
    importer = Importer(records, warnings)
    data = importer.run(root, filename)
    data["_media_files"] = importer.files_to_copy  # removed by import_gedcom
    return data, warnings


def import_gedcom(path_or_text, root: str | None = None, warnings: list[str] | None = None) -> dict:
    """Convert a GEDCOM file (path), its bytes or its text into a family_tree.json dict.

    `root` is the original xref (``@I12@`` or ``I12``) or the new id of the root person;
    by default the first individual. Warnings are appended to `warnings` if given.
    """
    data, found = import_gedcom_with_warnings(path_or_text, root)
    data.pop("_media_files", None)
    if warnings is not None:
        warnings.extend(found)
    return data


def _run_validator(data: dict, out_dir: Path, media: list[str]) -> tuple[list[str], list[str]]:
    """Run gene_archive.validate if available. Missing media files are only warnings."""
    try:
        from gene_archive import validate as validate_module  # noqa: PLC0415 (optional module)
    except ImportError:
        return [], []
    try:
        result = validate_module.validate(data, root=out_dir)
    except Exception as exc:  # the validator is optional; never lose the import because of it
        return [], [f"Validator failed: {exc}"]
    if isinstance(result, dict):
        errors, warns = list(result.get("errors", [])), list(result.get("warnings", []))
    elif isinstance(result, tuple) and len(result) == 2:
        errors, warns = list(result[0]), list(result[1])
    else:
        errors, warns = list(result or []), []
    names = {_basename(m) for m in media}
    missing = [e for e in errors if any(n and n in str(e) for n in names)]
    errors = [str(e) for e in errors if e not in missing]
    return errors, [str(w) for w in warns] + [f"(file not copied yet) {e}" for e in missing]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m gene_archive.ged_import",
                                     description="Convert a GEDCOM file into family_tree.json.")
    parser.add_argument("gedcom", help="GEDCOM file (.ged)")
    parser.add_argument("-o", "--output", default="family_tree.json", help="output JSON file")
    parser.add_argument("--root", help="root person: GEDCOM xref (@I12@ or I12) or new id")
    parser.add_argument("--force", action="store_true", help="overwrite an existing output file")
    args = parser.parse_args(argv)

    out = Path(args.output)
    if out.exists() and not args.force:
        print(f"error: {out} already exists; use --force to overwrite it", file=sys.stderr)
        return 1
    try:
        data, warnings = import_gedcom_with_warnings(Path(args.gedcom), args.root)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    media = data.pop("_media_files")
    errors, more = _run_validator(data, out.resolve().parent, media)
    warnings += more
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {out}: {len(data['people'])} people, {len(data['families'])} families, "
          f"{len(data['sources'])} sources; root {data['root_person_id']}; "
          f"{len(warnings)} warning(s)")
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    return 2 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
