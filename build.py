#!/usr/bin/env python3
"""
build.py — People Power SEO-generator

Haalt de Springcast RSS-feed op en genereert pre-rendered statische
HTML-pagina's in de dist/-map. Alle afleveringen krijgen een eigen URL
zodat zoekmachines en AI-crawlers de volledige catalogus kunnen indexeren.

Gebruik:
    python3 build.py

Vereist: requests
"""

import html
import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    import requests
except ImportError:
    print("Fout: requests is niet geinstalleerd. Draai eerst: pip install -r requirements.txt",
          file=sys.stderr)
    sys.exit(1)


# ==== Configuratie ====
RSS_URL = "https://app.springcast.fm/podcast-xml/17987"
SITE_URL = "https://peoplepower.radio"
SITE_NAME = "People Power"
DIST = Path(__file__).parent / "dist"
EPISODES_PER_PAGE = 50
ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
NS = {"itunes": ITUNES_NS}

# Live URLs voor foto- en categorie-mappings (wordt beheerd via admin.html)
IMAGES_URL = "https://peoplepower-radio.s3.nl-ams.scw.cloud/episode-images.json"
IMAGES_CUSTOM_URL = "https://peoplepower-radio.s3.nl-ams.scw.cloud/episode-images-custom.json"
CATEGORIES_URL = "https://peoplepower-radio.s3.nl-ams.scw.cloud/episode-categories.json"
CATEGORIES_CUSTOM_URL = "https://peoplepower-radio.s3.nl-ams.scw.cloud/episode-categories-custom.json"

MONTHS_NL = [
    "januari", "februari", "maart", "april", "mei", "juni",
    "juli", "augustus", "september", "oktober", "november", "december",
]

# Drempel voor thema-landingspagina's
MIN_EPISODES_PER_THEMA = 5

# SEO-descriptions per WordPress-category slug.
# De categorie-data zelf komt uit episode-categories.json (live uit de bucket).
# Deze descriptions worden gebruikt in <title>, <meta description>, <h1> lead-paragraaf
# en het JSON-LD op de thema-detail- en overzichtspagina's.
THEMA_DESCRIPTIONS = {
    "employability": "Employability: hoe houd je mensen duurzaam inzetbaar? People Power over loopbaan, leren, gezondheid en werkvermogen in een veranderende arbeidsmarkt.",
    "verandering-innovatie": "Organisatieverandering en innovatie: hoe verander je een organisatie zonder de mensen te verliezen? Over cultuur, structuur en nieuwe manieren van werken.",
    "learning-development": "Learning en Development: een leven lang leren in de praktijk. Over leerstrategieen, talentontwikkeling en hoe je een lerende organisatie bouwt.",
    "engagement": "Engagement: wat maakt mensen echt betrokken? People Power over bevlogenheid, motivatie en het bouwen van teams waar mensen graag bij willen horen.",
    "leiderschap": "Leiderschap: wat maakt een goede leider? Over leiderschapsstijlen, de menselijke kant van leiding geven en hoe leiders mensen laten groeien.",
    "inclusie": "Inclusie: diverse teams presteren beter, als de cultuur inclusief is. Over diversiteitsbeleid, inclusief leiderschap en gelijke kansen op werk.",
    "impact": "Impact: werken met betekenis. People Power over maatschappelijke bijdrage, duurzaamheid en organisaties die meer willen dan alleen winst maken.",
    "people-power-special": "People Power Specials: de bijzondere afleveringen met events, jubilea en verdiepende interviews over de grote vragen van werk.",
    "people-power-books": "People Power Boeken: interviews met auteurs over de beste boeken over HR, leiderschap, werkgeluk en organisatieontwikkeling.",
    "future-of-work": "Future of Work: hoe verandert werk door AI, hybride werken en globalisering? Samen met de Future of Work Hub van de Universiteit Utrecht.",
    "motivatie": "Motivatie: wat drijft mensen in hun werk? Over intrinsieke motivatie, waardering en de psychologie van betrokkenheid op de werkvloer.",
    "people-power-nieuws": "People Power Nieuws: updates over het programma, nieuwe partnerschappen en bijzondere aankondigingen.",
    "lef-en-liefde": "Lef en Liefde: over de menselijke kant van werk. Moed, kwetsbaarheid en de zachte waarden die teams sterk maken.",
    "werving-selectie": "Werving en Selectie: hoe vind je de juiste mensen in een krappe arbeidsmarkt? Over recruitment, employer branding en selectieprocessen.",
    "persoonlijk": "Persoonlijke verhalen van gasten uit People Power. De mensen achter de organisaties, hun drijfveren en hoe ze in het werk staan.",
    "onboarding": "Onboarding: de eerste indruk telt. Over de kunst van een goede start voor nieuwe medewerkers en hoe onboarding bijdraagt aan retentie.",
}


# Navigatie identiek aan bestaande site
NAV_LINKS = [
    ("/", "Home"),
    ("/afleveringen.html", "Afleveringen"),
    ("/themas.html", "Thema's"),
    ("/over.html", "Over"),
    ("/partner.html", "Vaker te gast"),
    ("/contact.html", "Contact"),
]


# ==== String-helpers ====

def slugify(text: str, max_len: int = 80) -> str:
    """Zet tekst om naar URL-vriendelijke slug (geen accenten, lowercase)."""
    if not text:
        return "aflevering"
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    # Strip #NNN prefix
    text = re.sub(r"^#?\d+\s*[-:.]?\s*", "", text)
    # Alleen alfanumeriek + spaties + streepjes
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    text = re.sub(r"\s+", "-", text).strip("-")
    text = re.sub(r"-+", "-", text)
    result = text[:max_len].rstrip("-")
    return result or "aflevering"


def strip_html(text: str) -> str:
    """Verwijder alle HTML-tags voor plain text weergave."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# Veilige HTML-whitelist voor aflevering-beschrijvingen
ALLOWED_TAGS = {"p", "br", "strong", "em", "b", "i", "u", "a", "ul", "ol", "li", "h3", "h4"}


def sanitize_html(text: str) -> str:
    """Beperk HTML tot een veilige subset van tags. Strip JS en on* attributes."""
    if not text:
        return ""
    # Unescape eventuele CDATA-escapes
    text = html.unescape(text)
    # Verwijder script en style volledig
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text,
                  flags=re.DOTALL | re.IGNORECASE)
    # Verwijder event handlers
    text = re.sub(r'\s*on\w+\s*=\s*"[^"]*"', "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*on\w+\s*=\s*'[^']*'", "", text, flags=re.IGNORECASE)
    # javascript: URLs
    text = re.sub(r"javascript:", "", text, flags=re.IGNORECASE)

    def tag_filter(match):
        tag = match.group(0)
        name_match = re.match(r"</?(\w+)", tag)
        if not name_match:
            return ""
        if name_match.group(1).lower() in ALLOWED_TAGS:
            return tag
        return ""

    text = re.sub(r"<[^>]+>", tag_filter, text)
    return text.strip()


def format_date_iso(pub_date_str: str) -> str:
    """RFC 822 naar ISO-datum (YYYY-MM-DD)."""
    if not pub_date_str:
        return ""
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT"):
        try:
            d = datetime.strptime(pub_date_str, fmt)
            return d.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def format_date_nl(pub_date_str: str) -> str:
    """RFC 822 naar Nederlandse datumnotatie (9 maart 2026)."""
    if not pub_date_str:
        return ""
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT"):
        try:
            d = datetime.strptime(pub_date_str, fmt)
            return f"{d.day} {MONTHS_NL[d.month - 1]} {d.year}"
        except ValueError:
            continue
    return ""


def format_duration(duration_str: str) -> str:
    if not duration_str:
        return ""
    if ":" in duration_str:
        parts = [int(p) for p in duration_str.split(":") if p.isdigit()]
        if len(parts) == 3:
            return f"{parts[0] * 60 + parts[1]} min"
        if len(parts) == 2:
            return f"{parts[0]} min"
    try:
        return f"{round(int(duration_str) / 60)} min"
    except ValueError:
        return ""


def extract_episode_number(title: str):
    m = re.match(r"^#?(\d+)\s", title)
    return int(m.group(1)) if m else None


# ==== RSS ====

def fetch_rss() -> str:
    print(f"-> Fetching RSS: {RSS_URL}")
    r = requests.get(RSS_URL, timeout=20,
                     headers={"User-Agent": "PeoplePower-Build/1.0"})
    r.raise_for_status()
    return r.text


def fetch_json(url: str, label: str) -> dict:
    """Haal een JSON-bestand op. Geeft leeg dict bij fout (niet-kritisch)."""
    try:
        r = requests.get(url, timeout=10,
                         headers={"User-Agent": "PeoplePower-Build/1.0"})
        r.raise_for_status()
        data = r.json()
        print(f"   {label}: geladen")
        return data
    except Exception as e:
        print(f"   {label}: NIET geladen ({e}). Fallback naar iTunes artwork.")
        return {}


def normalize_title(title: str) -> str:
    """Normaliseer een titel voor byTitle-lookup (lowercase, whitespace collapse)."""
    return re.sub(r"\s+", " ", (title or "").lower()).strip()


def best_image_for(ep: dict, img_data: dict, custom_imgs: dict) -> str:
    """Zoek de beste foto voor een aflevering. Prioriteit:
    1. custom override (admin.html)
    2. WordPress scrape op nummer
    3. WordPress scrape op titel
    4. iTunes RSS artwork (fallback)
    """
    num = str(ep.get("number") or "")
    if num and num in custom_imgs:
        return custom_imgs[num]
    by_number = img_data.get("byNumber", {})
    if num and num in by_number:
        return by_number[num]
    by_title = img_data.get("byTitle", {})
    if by_title:
        norm = normalize_title(ep.get("clean_title") or "")
        if norm in by_title:
            return by_title[norm]
    return ep.get("image_url") or ""


def best_cats_for(ep: dict, cat_data: dict, custom_cats: dict) -> list:
    """Zoek de categorieen voor een aflevering."""
    num = str(ep.get("number") or "")
    if num and num in custom_cats:
        return custom_cats[num]
    by_number = cat_data.get("byNumber", {})
    if num and num in by_number:
        return by_number[num]
    by_title = cat_data.get("byTitle", {})
    if by_title:
        norm = normalize_title(ep.get("clean_title") or "")
        if norm in by_title:
            return by_title[norm]
    return []


def cat_slug_to_name(slug: str, cat_data: dict) -> str:
    for c in cat_data.get("categories", []):
        if c.get("slug") == slug:
            return c.get("name") or slug
    return slug




def parse_episodes(xml_text: str):
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        return [], ""

    channel_image = ""
    ci = channel.find("itunes:image", NS)
    if ci is not None:
        channel_image = ci.get("href", "") or ""

    episodes = []
    seen_slugs = set()
    skipped = 0

    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        enclosure = item.find("enclosure")
        audio_url = enclosure.get("url") if enclosure is not None else ""

        if not title or not audio_url:
            skipped += 1
            continue

        description_raw = item.findtext("description") or ""
        description_text = strip_html(description_raw)
        description_safe = sanitize_html(description_raw)

        pub_date = (item.findtext("pubDate") or "").strip()

        image_el = item.find("itunes:image", NS)
        image_url = image_el.get("href") if image_el is not None else ""
        if not image_url:
            image_url = channel_image

        duration_raw = item.findtext("itunes:duration", default="", namespaces=NS) or ""
        duration = format_duration(duration_raw)

        ep_number = extract_episode_number(title)
        clean_title = re.sub(r"^#?\d+\s+", "", title).strip()

        slug = slugify(clean_title)
        base = slug
        counter = 2
        while slug in seen_slugs:
            slug = f"{base}-{counter}"
            counter += 1
        seen_slugs.add(slug)

        episodes.append({
            "title": title,
            "clean_title": clean_title,
            "number": ep_number,
            "slug": slug,
            "description_text": description_text,
            "description_safe": description_safe,
            "pub_date_raw": pub_date,
            "pub_date_iso": format_date_iso(pub_date),
            "pub_date_nl": format_date_nl(pub_date),
            "audio_url": audio_url,
            "image_url": image_url,
            "duration": duration,
        })

    if skipped:
        print(f"   {skipped} item(s) overgeslagen wegens ontbrekende titel of audio")
    return episodes, channel_image


# ==== HTML-templating ====

def render_nav(current_path: str = "") -> str:
    items = []
    for href, label in NAV_LINKS:
        cls = ' class="nav-active"' if current_path == href else ""
        items.append(f'        <a href="{href}"{cls}>{label}</a>')
    return "\n".join(items)


def render_layout(title: str, description: str, canonical: str, main_html: str,
                  extra_head: str = "", current_nav: str = "") -> str:
    nav_html = render_nav(current_nav)
    return f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(title)}</title>
  <meta name="description" content="{html.escape(description)}" />
  <link rel="canonical" href="{html.escape(canonical)}" />
  <link rel="icon" type="image/png" href="/logo-pp-orange-favicon.png" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="/style.css" />
  {extra_head}
</head>
<body>

  <a href="#main-content" class="skip-link">Sla navigatie over</a>

  <header class="site-header">
    <div class="container header-inner">
      <a href="/" class="brand">
        <img src="/logo-pp-full.png" alt="People Power, terug naar de homepage" class="brand-logo-full" />
      </a>
      <nav class="main-nav" aria-label="Hoofdnavigatie">
{nav_html}
      </nav>
    </div>
  </header>

  <main id="main-content">
{main_html}
  </main>

  <footer class="site-footer">
    <div class="container footer-inner">
      <div class="footer-brand">
        <img src="/logo-pp-full.png" alt="People Power, terug naar de homepage" class="footer-logo-full" />
        <div>
          <div class="footer-tag">Een programma op New Business Radio</div>
        </div>
      </div>
      <div class="footer-links">
        <a href="https://open.spotify.com/show/4X2GIU0blBAFkYzVbqTzpl" target="_blank" rel="noopener">Spotify</a>
        <a href="https://podcasts.apple.com/nl/podcast/new-business-radio-work/id1143830823" target="_blank" rel="noopener">Apple Podcasts</a>
        <a href="/contact.html">Contact</a>
      </div>
    </div>
    <div class="container footer-bottom">
      &copy; 2026 People Power &middot; <a href="mailto:glenn@people-power.nl">glenn@people-power.nl</a>
    </div>
  </footer>

</body>
</html>
"""


def render_episode_card(ep: dict, index: int) -> str:
    num_label = f"#{ep['number']}" if ep['number'] else "Aflevering"
    detail_url = f"/afleveringen/{ep['slug']}.html"
    desc = ep['description_text'][:200]
    if len(ep['description_text']) > 200:
        desc = desc.rstrip() + "..."

    img = ep.get('best_image') or ep['image_url']
    cats_html = ""
    if ep.get('cats_rendered'):
        cats_html = '<span class="ep-row-cats">' + ep['cats_rendered'] + '</span>'

    return f"""        <article class="ep-row" itemscope itemtype="https://schema.org/PodcastEpisode">
          <meta itemprop="url" content="{html.escape(SITE_URL + detail_url)}" />
          <a href="{html.escape(detail_url)}" class="ep-row-art">
            <img src="{html.escape(img)}" alt="Artwork {html.escape(ep['clean_title'])}" loading="lazy" itemprop="image" />
          </a>
          <div class="ep-row-body">
            <div class="ep-row-num">{html.escape(num_label)} &middot; <time datetime="{ep['pub_date_iso']}" itemprop="datePublished">{html.escape(ep['pub_date_nl'])}</time></div>
            <h2 class="ep-row-title"><a href="{html.escape(detail_url)}" itemprop="url name">{html.escape(ep['clean_title'])}</a></h2>
            <p class="ep-row-desc" itemprop="description">{html.escape(desc)}</p>
            <div class="ep-row-bottom">
              <span class="ep-row-meta">{html.escape(ep['duration'])}</span>
              {cats_html}
            </div>
          </div>
        </article>"""


def render_afleveringen_list(episodes: list, page: int, total_pages: int):
    start = (page - 1) * EPISODES_PER_PAGE
    slice_eps = episodes[start:start + EPISODES_PER_PAGE]

    filename = "afleveringen.html" if page == 1 else f"afleveringen-{page}.html"
    canonical = f"{SITE_URL}/{filename}"

    cards_html = "\n".join(render_episode_card(ep, i) for i, ep in enumerate(slice_eps))

    # Paginering-knoppen
    pag_lines = []
    if page > 1:
        prev_file = "afleveringen.html" if page == 2 else f"afleveringen-{page - 1}.html"
        pag_lines.append(f'          <a href="/{prev_file}" class="pag-btn" rel="prev">&larr; Vorige</a>')

    pag_lines.append('          <span class="pag-numbers">')
    for p in range(1, total_pages + 1):
        if p == 1 or p == total_pages or (page - 2 <= p <= page + 2):
            fn = "afleveringen.html" if p == 1 else f"afleveringen-{p}.html"
            if p == page:
                pag_lines.append(f'            <span class="pag-current" aria-current="page">{p}</span>')
            else:
                pag_lines.append(f'            <a href="/{fn}" class="pag-num">{p}</a>')
        elif p == page - 3 or p == page + 3:
            pag_lines.append('            <span class="pag-dots" aria-hidden="true">...</span>')
    pag_lines.append("          </span>")

    if page < total_pages:
        next_file = f"afleveringen-{page + 1}.html"
        pag_lines.append(f'          <a href="/{next_file}" class="pag-btn pag-btn-next" rel="next">Volgende</a>')

    pagination_html = "\n".join(pag_lines)

    suffix = f" (pagina {page})" if page > 1 else ""
    title = f"Alle afleveringen{suffix} | People Power"
    description = (
        f"Alle {len(episodes)} afleveringen van People Power. "
        f"Ruim 10 jaar radio en podcast over HR, leiderschap, werkgeluk en "
        f"de toekomst van werk. Elke maandag live op New Business Radio."
    )[:155]

    extra_head_parts = []
    if page > 1:
        extra_head_parts.append(f'<link rel="prev" href="{SITE_URL}/afleveringen.html" />')
    if page < total_pages:
        next_file = f"afleveringen-{page + 1}.html"
        extra_head_parts.append(f'<link rel="next" href="{SITE_URL}/{next_file}" />')
    extra_head = "\n  ".join(extra_head_parts)

    main_html = f"""    <div class="page-banner">
      <div class="container">
        <h1 class="page-banner-title">Alle afleveringen</h1>
      </div>
    </div>

    <section class="episodes-page">
      <div class="container">
        <p class="page-subtitle">{len(episodes)} afleveringen &middot; Pagina {page} van {total_pages}</p>
        <div class="ep-list">
{cards_html}
        </div>
        <nav class="pagination" aria-label="Paginering afleveringen">
{pagination_html}
        </nav>
      </div>
    </section>"""

    return filename, render_layout(title, description, canonical, main_html, extra_head,
                                   current_nav="/afleveringen.html")


def render_aflevering_detail(ep: dict) -> str:
    detail_url = f"/afleveringen/{ep['slug']}.html"
    canonical = f"{SITE_URL}{detail_url}"
    num_prefix = f"#{ep['number']} " if ep['number'] else ""
    title = f"{num_prefix}{ep['clean_title']} | People Power"
    description = ep['description_text'][:155]

    jsonld = {
        "@context": "https://schema.org",
        "@type": "PodcastEpisode",
        "name": ep['clean_title'],
        "description": ep['description_text'][:500],
        "datePublished": ep['pub_date_iso'],
        "contentUrl": ep['audio_url'],
        "url": canonical,
        "image": ep.get('best_image') or ep['image_url'],
        "partOfSeries": {
            "@type": "PodcastSeries",
            "name": "People Power",
            "url": SITE_URL,
        },
    }
    if ep['number']:
        jsonld["episodeNumber"] = ep['number']

    breadcrumb_ld = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE_URL + "/"},
            {"@type": "ListItem", "position": 2, "name": "Afleveringen",
             "item": SITE_URL + "/afleveringen.html"},
            {"@type": "ListItem", "position": 3, "name": ep['clean_title'], "item": canonical},
        ],
    }

    hero_img = ep.get('best_image') or ep['image_url']
    extra_head = (
        f'<meta property="og:title" content="{html.escape(ep["clean_title"])}" />\n'
        f'  <meta property="og:description" content="{html.escape(description)}" />\n'
        f'  <meta property="og:image" content="{html.escape(hero_img)}" />\n'
        f'  <meta property="og:type" content="article" />\n'
        f'  <meta property="og:url" content="{html.escape(canonical)}" />\n'
        f'  <meta property="og:locale" content="nl_NL" />\n'
        f'  <meta name="twitter:card" content="summary_large_image" />\n'
        f'  <script type="application/ld+json">\n{json.dumps(jsonld, ensure_ascii=False, indent=2)}\n  </script>\n'
        f'  <script type="application/ld+json">\n{json.dumps(breadcrumb_ld, ensure_ascii=False, indent=2)}\n  </script>'
    )

    aria_audio = html.escape(f"Afspelen: {ep['clean_title']}")
    num_text = f"Aflevering #{ep['number']}" if ep['number'] else "Aflevering"
    duration_html = (f"          &middot; {html.escape(ep['duration'])}"
                     if ep['duration'] else "")

    main_html = f"""    <div class="page-banner">
      <div class="container">
        <a href="/afleveringen.html" class="page-banner-back">&larr; Alle afleveringen</a>
        <h1 class="page-banner-title">{html.escape(ep['clean_title'])}</h1>
      </div>
    </div>

    <article class="ep-detail">
      <div class="container ep-detail-inner">
        <nav class="breadcrumbs" aria-label="Broodkruimels">
          <a href="/">Home</a> &rsaquo;
          <a href="/afleveringen.html">Afleveringen</a> &rsaquo;
          <span>{html.escape(ep['clean_title'])}</span>
        </nav>

        <div class="ep-number">{html.escape(num_text)}</div>
        <div class="ep-meta">
          <time datetime="{ep['pub_date_iso']}">{html.escape(ep['pub_date_nl'])}</time>
{duration_html}
        </div>

        <div class="ep-media">
          <div class="ep-player">
            <audio controls preload="none" src="{html.escape(ep['audio_url'])}" aria-label="{aria_audio}">
              Je browser ondersteunt geen audio-element.
              <a href="{html.escape(ep['audio_url'])}">Download de aflevering</a>.
            </audio>
          </div>
          <div class="ep-hero-wrap">
            <img class="ep-hero-img" src="{html.escape(hero_img)}" alt="Artwork bij {html.escape(ep['clean_title'])}" loading="lazy" />
          </div>
        </div>

        <div class="ep-description">
{ep['description_safe']}
        </div>

        <p class="ep-back-link"><a href="/afleveringen.html" class="link-arrow">Terug naar alle afleveringen</a></p>
      </div>
    </article>"""

    return render_layout(title, description, canonical, main_html, extra_head,
                         current_nav="/afleveringen.html")


def render_thema_card(ep: dict) -> str:
    """Kleine aflevering-card voor een themapagina."""
    num_label = f"#{ep['number']}" if ep['number'] else "Aflevering"
    detail_url = f"/afleveringen/{ep['slug']}.html"
    desc = ep['description_text'][:150]
    if len(ep['description_text']) > 150:
        desc = desc.rstrip() + "..."
    art = ep.get('best_image') or ep['image_url']

    return f"""        <article class="ep-row">
          <a href="{html.escape(detail_url)}" class="ep-row-art">
            <img src="{html.escape(art)}" alt="Artwork {html.escape(ep['clean_title'])}" loading="lazy" />
          </a>
          <div class="ep-row-body">
            <div class="ep-row-num">{html.escape(num_label)} &middot; <time datetime="{ep['pub_date_iso']}">{html.escape(ep['pub_date_nl'])}</time></div>
            <h3 class="ep-row-title"><a href="{html.escape(detail_url)}">{html.escape(ep['clean_title'])}</a></h3>
            <p class="ep-row-desc">{html.escape(desc)}</p>
            <div class="ep-row-bottom">
              <span class="ep-row-meta">{html.escape(ep['duration'])}</span>
            </div>
          </div>
        </article>"""


def render_thema_detail(thema_slug: str, thema_meta: dict, eps: list) -> str:
    label = thema_meta["label"]
    description = thema_meta["description"]
    canonical = f"{SITE_URL}/themas/{thema_slug}.html"

    title = f"{label} | People Power podcast"
    meta_desc = description[:155]

    jsonld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": f"{label} | People Power",
        "description": description,
        "url": canonical,
        "isPartOf": {
            "@type": "PodcastSeries",
            "name": "People Power",
            "url": SITE_URL,
        },
    }

    extra_head = (
        f'<meta property="og:title" content="{html.escape(label)} | People Power" />\n'
        f'  <meta property="og:description" content="{html.escape(meta_desc)}" />\n'
        f'  <meta property="og:type" content="website" />\n'
        f'  <meta property="og:url" content="{html.escape(canonical)}" />\n'
        f'  <meta property="og:locale" content="nl_NL" />\n'
        f'  <script type="application/ld+json">\n{json.dumps(jsonld, ensure_ascii=False, indent=2)}\n  </script>'
    )

    # Sorteer op datum aflopend
    sorted_eps = sorted(eps, key=lambda e: e['pub_date_iso'] or "", reverse=True)
    cards = "\n".join(render_thema_card(ep) for ep in sorted_eps)

    main_html = f"""    <div class="page-banner">
      <div class="container">
        <h1 class="page-banner-title">{html.escape(label)}</h1>
      </div>
    </div>

    <section class="episodes-page">
      <div class="container">
        <nav class="breadcrumbs" aria-label="Broodkruimels">
          <ol class="breadcrumbs-list">
            <li><a href="/">Home</a> &rsaquo;</li>
            <li><a href="/themas.html">Thema's</a> &rsaquo;</li>
            <li aria-current="page">{html.escape(label)}</li>
          </ol>
        </nav>

        <p class="thema-lead">{html.escape(description)}</p>
        <p class="page-subtitle">{len(sorted_eps)} afleveringen over dit thema</p>

        <section aria-labelledby="afleveringen-heading">
          <h2 id="afleveringen-heading" class="visually-hidden">Afleveringen</h2>
          <div class="ep-list">
{cards}
          </div>
        </section>
      </div>
    </section>"""

    return render_layout(title, meta_desc, canonical, main_html, extra_head,
                         current_nav="/themas.html")


def render_themas_overview(active_themas: dict, thema_meta_map: dict) -> str:
    """Overview page met per thema een korte lijst van 2 recente afleveringen.
    Themas gesorteerd op de datum van de nieuwste aflevering (aflopend).
    """
    canonical = f"{SITE_URL}/themas.html"
    title = "Thema's | People Power podcast over HR en leiderschap"
    meta_desc = (
        "Alle thema's van People Power: leiderschap, employability, engagement, "
        "learning en development, future of work en meer. "
        "Ruim 600 afleveringen doorzoekbaar per thema."
    )[:155]

    # Sorteer themas op de pub_date_iso van de nieuwste aflevering (list[0])
    # Episodes zijn in de episode-list al newest-first, dus eps[0] is de nieuwste.
    def newest_iso(eps):
        return eps[0]['pub_date_iso'] if eps else ""

    items = sorted(
        active_themas.items(),
        key=lambda kv: newest_iso(kv[1]),
        reverse=True,
    )

    sections = []
    for slug, eps in items:
        label = thema_meta_map[slug]["label"]
        count = len(eps)
        # Sorteer aflevering-lijst zelf ook op datum aflopend (voor zekerheid)
        top_two = sorted(eps, key=lambda e: e['pub_date_iso'] or "", reverse=True)[:2]
        cards_html = "\n".join(render_thema_card(ep) for ep in top_two)
        sections.append(
            f"""        <section class="thema-section">
          <div class="thema-head">
            <h2 class="thema-title"><a href="/themas/{slug}.html">{html.escape(label)}</a></h2>
            <span class="thema-count">{count} afleveringen</span>
          </div>
          <div class="ep-list ep-list-2col">
{cards_html}
          </div>
          <div class="thema-more">
            <a href="/themas/{slug}.html" class="btn-more">Meer {html.escape(label)}</a>
          </div>
        </section>"""
        )

    sections_joined = "\n".join(sections)

    main_html = f"""    <div class="page-banner">
      <div class="container">
        <h1 class="page-banner-title">Thema's</h1>
      </div>
    </div>

    <section class="themas-page">
      <div class="container">
        <p class="themas-intro">
          People Power bespreekt al ruim 10 jaar de grote thema's in werk en organisatie.
          Blader per thema door meer dan 600 afleveringen over leiderschap, werkgeluk,
          HR en de toekomst van werk.
        </p>

{sections_joined}
      </div>
    </section>"""

    return render_layout(title, meta_desc, canonical, main_html,
                         current_nav="/themas.html")


def render_sitemap(episodes: list, theme_slugs: list) -> str:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    # (path, priority, lastmod, changefreq)
    urls = [
        ("/", "1.0", today, "weekly"),
        ("/afleveringen.html", "0.9", today, "weekly"),
        ("/themas.html", "0.8", today, "weekly"),
        ("/over.html", "0.7", today, "monthly"),
        ("/partner.html", "0.7", today, "monthly"),
        ("/contact.html", "0.6", today, "monthly"),
    ]
    total_pages = (len(episodes) + EPISODES_PER_PAGE - 1) // EPISODES_PER_PAGE
    for p in range(2, total_pages + 1):
        urls.append((f"/afleveringen-{p}.html", "0.7", today, "weekly"))
    for slug in theme_slugs:
        urls.append((f"/themas/{slug}.html", "0.7", today, "weekly"))
    for ep in episodes:
        urls.append((f"/afleveringen/{ep['slug']}.html", "0.5",
                     ep['pub_date_iso'] or today, "monthly"))

    url_blocks = []
    for path, prio, lastmod, freq in urls:
        url_blocks.append(
            f"  <url>\n"
            f"    <loc>{SITE_URL}{path}</loc>\n"
            f"    <lastmod>{lastmod}</lastmod>\n"
            f"    <changefreq>{freq}</changefreq>\n"
            f"    <priority>{prio}</priority>\n"
            f"  </url>"
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(url_blocks)
        + "\n</urlset>\n"
    )


def render_robots() -> str:
    return f"""User-agent: *
Allow: /
Sitemap: {SITE_URL}/sitemap.xml
"""


def render_schema_index(total_episodes: int) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "PodcastSeries",
        "name": "People Power",
        "description": (
            "Mensgericht organiseren voor betere prestaties en gelukkige mensen. "
            "Praktijkvoorbeelden, onderzoeken en modellen over HR, leiderschap, "
            "werkgeluk en de toekomst van werk."
        ),
        "url": SITE_URL,
        "inLanguage": "nl-NL",
        "author": {
            "@type": "Person",
            "name": "Glenn van der Burg",
            "url": "https://glennvanderburg.nl",
        },
        "publisher": {
            "@type": "Organization",
            "name": "New Business Radio",
            "url": "https://newbusinessradio.nl",
        },
        "numberOfEpisodes": total_episodes,
        "genre": [
            "HR", "Leiderschap", "Werkgeluk",
            "Organisatieontwikkeling", "Toekomst van werk",
        ],
    }


# ==== Main ====

def main():
    # 1. Fetch RSS
    try:
        xml_text = fetch_rss()
    except Exception as e:
        print(f"\n[FOUT] Kon RSS-feed niet ophalen: {e}", file=sys.stderr)
        print("       Bestaande bestanden worden niet overschreven. Stop.", file=sys.stderr)
        sys.exit(1)

    # 2. Parse
    try:
        episodes, channel_image = parse_episodes(xml_text)
    except ET.ParseError as e:
        print(f"\n[FOUT] XML-parse fout: {e}", file=sys.stderr)
        sys.exit(1)

    if not episodes:
        print("\n[FOUT] Geen afleveringen gevonden in feed. Stop.", file=sys.stderr)
        sys.exit(1)

    print(f"   Geparseerd: {len(episodes)} afleveringen")

    # 3. Laad foto- en categorie-metadata (niet-kritisch, best effort)
    print("-> Fetching metadata:")
    img_data = fetch_json(IMAGES_URL, "episode-images.json")
    custom_imgs = fetch_json(IMAGES_CUSTOM_URL, "episode-images-custom.json")
    cat_data = fetch_json(CATEGORIES_URL, "episode-categories.json")
    custom_cats = fetch_json(CATEGORIES_CUSTOM_URL, "episode-categories-custom.json")

    # Verrijk elke episode met best_image en categorieen
    match_count = 0
    for ep in episodes:
        best = best_image_for(ep, img_data, custom_imgs)
        if best and best != ep.get('image_url'):
            match_count += 1
        ep['best_image'] = best

        cats = best_cats_for(ep, cat_data, custom_cats)
        ep['cats'] = cats
        if cats:
            ep['cats_rendered'] = "".join(
                f'<span class="ep-cat-tag">{html.escape(cat_slug_to_name(c, cat_data))}</span>'
                for c in cats
            )
        else:
            ep['cats_rendered'] = ""
    print(f"   {match_count} afleveringen gematcht met guest foto (van {len(episodes)})")

    # 4. Classificeer elke aflevering via WordPress-categorieen (uit episode-categories.json)
    # Eerder al op de episodes geplaatst als ep['cats']. Groepeer nu per thema.
    from collections import defaultdict
    themas_episodes = defaultdict(list)
    for ep in episodes:
        for t in ep.get('cats', []):
            if t and t != "uncategorized":
                themas_episodes[t].append(ep)

    # Bouw de thema-metadata dict: label uit categoryData, description uit THEMA_DESCRIPTIONS
    cat_label_map = {c.get("slug"): c.get("name") for c in cat_data.get("categories", [])}
    thema_meta_map = {}
    for slug in themas_episodes:
        label = cat_label_map.get(slug, slug.replace("-", " ").title())
        desc = THEMA_DESCRIPTIONS.get(
            slug,
            f"People Power over {label.lower()}. Alle afleveringen over dit thema op een rij."
        )
        thema_meta_map[slug] = {"label": label, "description": desc}

    # Thema's met genoeg afleveringen krijgen een eigen pagina
    active_themas = {
        slug: eps for slug, eps in themas_episodes.items()
        if len(eps) >= MIN_EPISODES_PER_THEMA
    }
    skipped_themas = {
        slug: len(eps) for slug, eps in themas_episodes.items()
        if slug not in active_themas
    }

    print(f"   {len(active_themas)} thema's actief (>= {MIN_EPISODES_PER_THEMA} afleveringen):")
    for slug, eps in sorted(active_themas.items(), key=lambda kv: -len(kv[1])):
        label = thema_meta_map[slug]["label"]
        print(f"     {slug:30s} {len(eps):4d} afleveringen  ({label})")
    if skipped_themas:
        print("   Onder drempel (geen pagina gegenereerd):")
        for slug, cnt in skipped_themas.items():
            label = thema_meta_map[slug]["label"]
            print(f"     {slug:30s} {cnt:4d} afleveringen  ({label})")

    # 5. Output-dir voorbereiden
    DIST.mkdir(exist_ok=True)
    (DIST / "afleveringen").mkdir(exist_ok=True)
    (DIST / "themas").mkdir(exist_ok=True)

    # 6. Lijstpagina's met paginering
    total_pages = (len(episodes) + EPISODES_PER_PAGE - 1) // EPISODES_PER_PAGE
    for p in range(1, total_pages + 1):
        filename, html_out = render_afleveringen_list(episodes, p, total_pages)
        (DIST / filename).write_text(html_out, encoding="utf-8")
    print(f"   Gegenereerd: {total_pages} lijstpagina(s)")

    # 7. Detailpagina's
    generated_details = 0
    for ep in episodes:
        detail_html = render_aflevering_detail(ep)
        (DIST / "afleveringen" / f"{ep['slug']}.html").write_text(
            detail_html, encoding="utf-8")
        generated_details += 1
    print(f"   Gegenereerd: {generated_details} detailpagina's")

    # 8a. Thema-detailpagina's
    for slug, eps in active_themas.items():
        html_out = render_thema_detail(slug, thema_meta_map[slug], eps)
        (DIST / "themas" / f"{slug}.html").write_text(html_out, encoding="utf-8")
    print(f"   Gegenereerd: {len(active_themas)} thema-detailpagina(s)")

    # 8b. Thema-overzichtspagina (themas.html)
    (DIST / "themas.html").write_text(
        render_themas_overview(active_themas, thema_meta_map), encoding="utf-8")
    print("   Gegenereerd: themas.html (overzicht)")

    # 7. Sitemap
    (DIST / "sitemap.xml").write_text(
        render_sitemap(episodes, list(active_themas.keys())), encoding="utf-8")
    print("   Gegenereerd: sitemap.xml")

    # 7. robots.txt
    (DIST / "robots.txt").write_text(render_robots(), encoding="utf-8")
    print("   Gegenereerd: robots.txt")

    # 8. Schema-index JSON
    schema = render_schema_index(len(episodes))
    (DIST / "schema-index.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    print("   Gegenereerd: schema-index.json")

    # 9. Verificatie op de meest recente aflevering
    last_ep = episodes[0]
    test_file = DIST / "afleveringen" / f"{last_ep['slug']}.html"
    if test_file.exists():
        content = test_file.read_text(encoding="utf-8")
        expected_title = html.escape(last_ep['clean_title'])
        if "<h1" in content and expected_title in content:
            print(f"\n[OK] Verificatie: {test_file.name} bevat correcte <h1>: "
                  f"{last_ep['clean_title']}")
        else:
            print(f"\n[WAARSCHUWING] Verificatie: <h1> niet gevonden in "
                  f"{test_file.name}", file=sys.stderr)
    else:
        print(f"\n[WAARSCHUWING] Verificatie: {test_file.name} ontbreekt",
              file=sys.stderr)

    print(f"\nKlaar. Output staat in {DIST}/")


if __name__ == "__main__":
    main()
