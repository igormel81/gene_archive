"""«Архив в цифрах» / "Archive in numbers": statistics computed from the published data at build time.

The result goes into data.json as `stats`; app.js draws it (#/stats) with bars on the theme's colours.
Only what is published counts: hidden documents are already gone, living people have no dates.
"""
import collections
import re

# where documents come from, by `kind`
ORIGINS = (
    ("family", ("family_photo", "family_archive_document", "family_manuscript", "letter", "family_report", "family_testimony")),
    ("archives", ("civil_record_copy", "church_record", "education_record", "revision_list", "census_record", "immigration_record",
                  "digitized_archive_original", "digitized_archive_case", "online_archive_index", "online_archive_catalog",
                  "archive_database", "research_scan")),
    ("publications", ("newspaper", "publication", "published_reference", "published_register_unlinked_person", "published_diary",
                      "online_reference")),
    ("military", ("online_military_record", "military_record_copy")),
    ("graves", ("gravestone", "gravestone_image", "memorial_image")),
)
ORIGIN_OF = {k: name for name, kinds in ORIGINS for k in kinds}
# what confirms a person, the strongest first
PROOF = ("archives", "publications", "family_papers", "family_word", "none")
OPEN_LEAD = lambda lead: lead.get("status") not in ("closed", "superseded", "accepted")   # noqa: E731


def year(ev):
    m = re.search(r"\d{4}", str((ev or {}).get("date") or ""))
    return int(m[0]) if m else None


def proof(p, kinds):
    """The strongest kind of evidence that this is the person: identity_source_ids, or — without them — the
    documents of birth, death and burial. "family_word": only the family's stories."""
    ids = p.get("identity_source_ids") or [s for e in ("birth", "death", "burial") for s in (p.get(e) or {}).get("source_ids", [])]
    ids = [s for s in ids if s in kinds]
    origins = {ORIGIN_OF.get(kinds[s], "other") for s in ids}
    if origins & {"archives", "military"}:
        return "archives"
    if "publications" in origins:
        return "publications"
    if any(kinds[s] not in ("family_report", "family_testimony") for s in ids):
        return "family_papers"
    return "family_word" if ids else "none"


def archive_stats(data, groups, living, restored=()):
    """`groups`: surname branches [(surname, [person ids])] as on the surname pages."""
    people = [p for p in data["people"] if not p.get("placeholder")]
    known = [p for p in people if p["id"] not in living]
    kinds = {s["id"]: s.get("kind") for s in data["sources"]}
    leads = data.get("research_leads", [])
    corrections = data.get("corrections", [])

    origins = collections.Counter(ORIGIN_OF.get(s.get("kind"), "other") for s in data["sources"])
    proofs = collections.Counter(proof(p, kinds) for p in known if p.get("research_status") != "unlinked_candidate")
    centuries = collections.Counter((y - 1) // 100 + 1 for y in (year(p.get("birth")) for p in known) if y)
    log = collections.Counter(e["date"] for e in data.get("research_log", []) if e.get("date"))

    byid = {p["id"]: p for p in people}
    branches = []
    for surname, ids in groups:
        ids = [i for i in ids if i in byid]
        dated = sorted((year(byid[i].get("birth")), i) for i in ids if i not in living and year(byid[i].get("birth")))
        branches.append({
            "surname": surname, "people": len(ids),
            "leads": sum(1 for x in leads if x.get("person_id") in ids and OPEN_LEAD(x)),
            "corrections": sum(1 for c in corrections if c.get("person_id") in ids),
            "earliest": dated[0][1] if dated else None, "earliest_year": dated[0][0] if dated else None,
        })
    return {
        "totals": {
            "people": len(people), "families": len(data["families"]), "documents": len(data["sources"]),
            "places": len(data.get("places", [])), "corrections": len(corrections), "restored": len(restored),
            "open_leads": sum(1 for x in leads if OPEN_LEAD(x)), "log": sum(log.values()),
            "possible": sum(1 for p in people if p.get("research_status") == "unlinked_candidate"),
        },
        "origins": [[k, origins[k]] for k in [o for o, _ in ORIGINS] + ["other"] if origins[k]],
        "proof": [[k, proofs[k]] for k in PROOF if proofs[k]],
        "branches": branches,
        "centuries": sorted([c, n] for c, n in centuries.items()),
        "log_by_day": sorted([d, n] for d, n in log.items()),
    }
