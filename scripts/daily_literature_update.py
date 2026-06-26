import json
import ssl
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

SUPABASE_URL = "https://xfikxinwupwhexietfvo.supabase.co"
SUPABASE_KEY = "sb_publishable_BkPixVx-V0Lkw2D9QchA4A_g4Jamn5j"

CORE_QUERIES = [
    '"moisture buffering" "3D printing" building',
    '"moisture buffering value" building material',
    '"passive indoor moisture" "3D printed"',
    '"3D-printed" clay "moisture buffering"',
    '"NORDTEST" "moisture buffering value"',
    '"hygrothermal" "3D printed" "building"',
    '"moisture buffering" "bio-based" "building material"',
    '"passive humidity regulation" "building component"',
]

HIGH_SIGNAL = [
    "moisture buffering",
    "moisture buffer",
    "moisture buffering value",
    "mbv",
    "nordtest",
    "passive humidity",
    "passive indoor moisture",
    "passive moisture",
]

BUILDING_SIGNAL = [
    "building",
    "indoor",
    "envelope",
    "component",
    "wall",
    "construction",
    "building material",
]

DESIGN_MATERIAL_SIGNAL = [
    "3d print",
    "3d-print",
    "additive manufacturing",
    "4d print",
    "clay",
    "geopolymer",
    "bio-based",
    "biobased",
    "hemp",
    "hygroscopic",
    "surface area",
]

LOW_PRIORITY = [
    "review",
    "bibliometric",
    "editorial",
    "perspective",
    "sustainable development goals",
]


def request_json(url, headers=None, method="GET", payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    context = ssl.create_default_context()
    with urllib.request.urlopen(req, context=context, timeout=40) as response:
        body = response.read().decode("utf-8")
        return json.loads(body) if body else None


def text_of(item):
    title = " ".join(item.get("title") or [])
    subtitle = " ".join(item.get("subtitle") or [])
    abstract = item.get("abstract") or ""
    journal = " ".join(item.get("container-title") or [])
    return f"{title} {subtitle} {abstract} {journal}".lower()


def has_any(text, terms):
    return any(term in text for term in terms)


def score_item(item):
    text = text_of(item)
    score = 0
    if has_any(text, HIGH_SIGNAL):
        score += 40
    if has_any(text, BUILDING_SIGNAL):
        score += 25
    if has_any(text, DESIGN_MATERIAL_SIGNAL):
        score += 25
    if "journal-article" == item.get("type"):
        score += 10
    if "3d" in text and ("moisture" in text or "humidity" in text):
        score += 15
    if "mbv" in text or "nordtest" in text:
        score += 15
    if has_any(text, LOW_PRIORITY):
        score -= 20
    return max(0, min(100, score))


def published_year(item):
    published = item.get("published-print") or item.get("published-online") or item.get("published")
    parts = (published or {}).get("date-parts") or []
    return parts[0][0] if parts and parts[0] else None


def authors_of(item):
    authors = item.get("author") or []
    names = []
    for author in authors[:8]:
        given = author.get("given", "")
        family = author.get("family", "")
        full = " ".join(part for part in [given, family] if part).strip()
        if full:
            names.append(full)
    if len(authors) > 8:
        names.append("et al.")
    return ", ".join(names)


def tags_for(item):
    text = text_of(item)
    tags = []
    mapping = [
        ("MBV", ["mbv", "moisture buffering value"]),
        ("NORDTEST", ["nordtest"]),
        ("3D printing", ["3d print", "3d-print", "additive manufacturing"]),
        ("4D printing", ["4d print"]),
        ("clay", ["clay"]),
        ("geopolymer", ["geopolymer"]),
        ("bio-based", ["bio-based", "biobased", "hemp"]),
        ("moisture buffering", ["moisture buffering", "moisture buffer"]),
        ("passive humidity", ["passive humidity", "passive moisture", "passive indoor moisture"]),
        ("hygrothermal transfer", ["hygrothermal", "heat and moisture"]),
        ("building component", ["component", "envelope", "wall"]),
        ("surface-area design", ["surface area", "surface-area"]),
    ]
    for tag, terms in mapping:
        if any(term in text for term in terms):
            tags.append(tag)
    return tags[:8]


def clean_title(item):
    return " ".join(item.get("title") or []).strip()


def journal_of(item):
    return " ".join(item.get("container-title") or []).strip()


def summary_for(item, tags):
    tag_text = ", ".join(tags[:5]) if tags else "topic relevance"
    return f"Matched the focused literature radar through {tag_text}. Review manually for methods, material system, MBV or hygrothermal metrics, and relevance to passive indoor moisture regulation."


def search_crossref(query, from_date):
    params = {
        "rows": "20",
        "sort": "published",
        "order": "desc",
        "filter": f"type:journal-article,from-pub-date:{from_date}",
        "query.bibliographic": query,
    }
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
    data = request_json(url)
    return data.get("message", {}).get("items", [])


def collect_candidates():
    cutoff_recent = (date.today() - timedelta(days=21)).isoformat()
    cutoff_backfill = (date.today() - timedelta(days=365 * 3)).isoformat()
    seen = {}

    for cutoff in [cutoff_recent, cutoff_backfill]:
        for query in CORE_QUERIES:
            try:
                for item in search_crossref(query, cutoff):
                    doi = (item.get("DOI") or "").lower()
                    title = clean_title(item)
                    if not doi or not title:
                        continue
                    score = score_item(item)
                    if score < 70:
                        continue
                    if doi not in seen or score > seen[doi][0]:
                        seen[doi] = (score, item)
                time.sleep(0.25)
            except Exception as error:
                print(f"Search failed for {query}: {error}")
        if len(seen) >= 3:
            break

    return sorted(seen.values(), key=lambda pair: pair[0], reverse=True)[:5]


def to_paper(score, item):
    tags = tags_for(item)
    doi = item.get("DOI")
    return {
        "title": clean_title(item),
        "authors": authors_of(item),
        "journal": journal_of(item),
        "year": published_year(item),
        "doi": doi,
        "url": f"https://doi.org/{doi}",
        "pdf": "",
        "score": score,
        "summary": summary_for(item, tags),
        "tags": tags,
    }


def supabase_headers(prefer):
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def upsert_papers(papers):
    if not papers:
        return []
    url = f"{SUPABASE_URL}/rest/v1/papers?on_conflict=doi"
    return request_json(
        url,
        headers=supabase_headers("resolution=merge-duplicates,return=representation"),
        method="POST",
        payload=papers,
    ) or []


def insert_default_states(inserted):
    if not inserted:
        return
    states = [{"paper_id": paper["id"], "status": "To read", "saved": False} for paper in inserted]
    url = f"{SUPABASE_URL}/rest/v1/paper_state?on_conflict=paper_id"
    request_json(
        url,
        headers=supabase_headers("resolution=ignore-duplicates,return=minimal"),
        method="POST",
        payload=states,
    )


def main():
    candidates = collect_candidates()
    papers = [to_paper(score, item) for score, item in candidates]
    inserted = upsert_papers(papers)
    insert_default_states(inserted)
    print(json.dumps({"candidate_count": len(candidates), "upserted_count": len(inserted), "titles": [p["title"] for p in papers]}, indent=2))


if __name__ == "__main__":
    main()
