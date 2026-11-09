"""Génère le site statique libelille.fr dans public/.

    python build.py

Sources :
  content/articles/*.json   actualité du jour (robot)
  content/guides/*.md       guides (Argent, Santé, Beauté…)
  content/pages/*.json      anciens articles repris dans le nouveau design (adresse inchangée)
  legacy/                   fichiers copiés tels quels (pages optique, images, ads.txt…)
  state/redirections.json   redirections 301 et suppressions 410 → .htaccess
"""
import html
import json
import os
import re
import shutil
from collections import defaultdict
from datetime import datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import markdown
import yaml

from pipeline.util import RACINE, charger_config, heure_locale, lire_json, maintenant, tous_les_articles

SORTIE = RACINE / "public"
MOIS = "janvier février mars avril mai juin juillet août septembre octobre novembre décembre".split()
JOURS = "lundi mardi mercredi jeudi vendredi samedi dimanche".split()

cfg = charger_config()
SITE = cfg["site"]
ACTU = {r["slug"]: r for r in cfg["rubriques"]}
LOCAL = {k: v for k, v in ACTU.items() if v.get("groupe") == "local"}
SECTIONS = {s["slug"]: s for s in cfg.get("sections", [])}
TOUTES = {**ACTU, **SECTIONS}
LOCAL_NOM = {"nom": "Local", "slug": "local"}
DOMAINE = (SITE.get("domaine") or "").strip().strip("/")
BASE = "" if DOMAINE else os.environ.get("LEFIL_BASE", "").rstrip("/")
URL_SITE = f"https://{DOMAINE}" if DOMAINE else os.environ.get("LEFIL_SITE_URL", "").rstrip("/")
ALIAS_RUB = {"actualite-archives": "archives"}
e = html.escape


def lien(chemin):
    return f"{BASE}{chemin}"


def absolu(chemin):
    return f"{URL_SITE}{BASE}{chemin}" if URL_SITE else chemin


def dt(iso):
    return datetime.fromisoformat(iso)


MOIS_ABR = "janv. févr. mars avr. mai juin juil. août sept. oct. nov. déc.".split()


def date_courte(iso):
    d = heure_locale(cfg, dt(iso))
    return f"{d.day} {MOIS_ABR[d.month - 1]} {d.year}"


def date_longue(iso, heure=True):
    d = heure_locale(cfg, dt(iso))
    s = f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]} {d.year}"
    return s + (f" à {d:%Hh%M}" if heure else "")


def nom_rub(slug):
    if slug == "local":
        return "Local"
    return TOUTES.get(ALIAS_RUB.get(slug, slug), {"nom": slug})["nom"]


# ── Chargement des contenus ───────────────────────────────────────────────

def charger_guides():
    guides = []
    for f in sorted((RACINE / "content" / "guides").glob("*.md")):
        brut = f.read_text(encoding="utf-8")
        _, entete, corps = brut.split("---", 2)
        meta = yaml.safe_load(entete)
        meta["corps_html"] = markdown.markdown(corps.strip(), extensions=["sane_lists", "tables"])
        meta["type"] = "guide"
        meta.setdefault("date", "2026-11-09T09:00:00+01:00")
        guides.append(meta)
    return guides


def charger_pages():
    pages = []
    for f in (RACINE / "content" / "pages").glob("*.json"):
        p = json.loads(f.read_text(encoding="utf-8"))
        p["titre"] = p["titre"][:1].upper() + p["titre"][1:]
        p["rubrique"] = ALIAS_RUB.get(p["rubrique"], p["rubrique"])
        p["type"] = "page"
        p.setdefault("date", None)
        pages.append(p)
    return pages


OPTIQUE_GARDER = {"p", "h2", "h3", "h4", "ul", "ol", "li", "a", "strong", "b", "em", "i", "img", "br",
                  "table", "thead", "tbody", "tr", "td", "th", "blockquote"}


def extraire_optique(t):
    """Reprend le contenu d'une ancienne page optique (titre, description, texte) sans son ancienne mise en page."""
    from bs4 import BeautifulSoup, ProcessingInstruction, Comment
    soup = BeautifulSoup(t, "html.parser")
    titre = soup.title.get_text(" ", strip=True) if soup.title else ""
    def meta(nom):
        m = soup.find("meta", attrs={"name": nom})
        return (m.get("content") or "").strip() if m else ""
    h1 = soup.find("h1")
    h1_txt = re.sub(r"\s+", " ", h1.get_text(" ", strip=True)) if h1 else titre
    corps = soup.body or soup
    for n in corps.find_all(string=lambda x: isinstance(x, (ProcessingInstruction, Comment))):
        n.extract()
    for sel in ["ul.navbar", "div#img", "script", "noscript", "ins", "iframe", "style", "#fb-root", ".fb-like",
                "g\\:plusone", "h1"]:
        for n in corps.select(sel):
            n.decompose()
    for n in corps.find_all(lambda x: x.name and ":" in x.name):
        n.decompose()
    for a in corps.find_all("a"):
        h = a.get("href", "")
        if "twitter.com/share" in h or "mentions-legales" in h or "comparateur" in h:
            a.decompose()
    image = None
    for img in corps.find_all("img"):
        src = img.get("src", "")
        if re.search(r"rachatdecredit|comparateur-rachat", src):
            img.decompose()
            continue
        src = re.sub(r"^https?://(www\.)?libelille\.fr", "", src)
        if image is None and src.startswith("/"):
            image = src
            img.decompose()          # affichée en grand en tête d'article
            continue
        img["src"] = src
        img["loading"] = "lazy"
    for n in list(corps.find_all(True)):
        if n.name not in OPTIQUE_GARDER:
            n.unwrap()
            continue
        garder = {"href", "src", "alt", "title", "loading"}
        for att in list(n.attrs):
            if att not in garder:
                del n[att]
        if n.name == "a" and n.get("href"):
            n["href"] = re.sub(r"^https?://(www\.)?libelille\.fr(?=/)", "", n["href"])
    for p in corps.find_all("p"):
        if not p.get_text(strip=True) and not p.find("img"):
            p.decompose()
    html_corps = str(corps.decode_contents()) if hasattr(corps, "decode_contents") else str(corps)
    html_corps = re.sub(r"(<br\s*/?>\s*){2,}", "<br>", html_corps)
    html_corps = re.sub(r"^(\s|<br\s*/?>)+", "", html_corps.strip())
    # texte resté hors paragraphe : on l'enveloppe pour la mise en page
    return {"titre_exact": titre, "description": meta("description"), "mots_cles": meta("keywords"),
            "h1": h1_txt, "image": image, "corps_html": html_corps.strip()}


def page_optique(o, tous):
    url = o["url"]
    img = o.get("image")
    credit = (f'<figcaption><span class="credit">Photo : <a href="{e(o["photo_page"])}" rel="nofollow noopener">'
              f'{e(o["photo_credit"])} / Wikimedia Commons</a></span></figcaption>') if o.get("photo_credit") else ""
    figure = f'<figure class="photo-article"><img src="{e(lien(img))}" alt="{e(o["h1"])}">{credit}</figure>' if img else ""
    contenu = f"""<article class="article optique"><header>
<a class="etiquette r-optique" href="{lien("/rubrique/optique/")}">{e(nom_rub("optique"))}</a>
<h1>{e(o['h1'])}</h1></header>{figure}<div class="texte">{o['corps_html']}</div></article>
{bloc_optique("À lire aussi en Optique & Audition", optique_pour(url, 4), "compact")}"""
    head = jsonld("Article", o["h1"], o.get("description", ""), url, None, img, nom_rub("optique")) + og(o["h1"], o.get("description"), img)
    if o.get("mots_cles"):
        head += f'<meta name="keywords" content="{e(o["mots_cles"])}">\n'
    ecrire(url, page(o["h1"], contenu, o.get("description", ""), url, head, rub_active="optique",
                     titre_exact=o.get("titre_exact") or None))


def charger_optique():
    """Pages optique : même adresse, même texte, nouveau design (le contenu est repris de legacy/)."""
    lignes = []
    fc = RACINE / "state" / "optique_photos.json"
    photos_remplacees = {k: v for k, v in (json.loads(fc.read_text(encoding="utf-8")) if fc.exists() else {}).items()
                         if (RACINE / "legacy" / v["url"].lstrip("/")).exists()}
    for f in sorted((RACINE / "legacy").glob("*.*")):
        if f.suffix not in (".php", ".html") or f.name.startswith(("touc", "sbjp")):
            continue
        b = f.read_bytes()
        try:
            t = b.decode("utf-8")
        except UnicodeDecodeError:
            t = b.decode("cp1252", errors="replace")
        m = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", t) or re.search(r"(?is)<title>(.*?)</title>", t)
        titre = html.unescape(re.sub(r"<[^>]+>|\s+", " ", m.group(1))).strip() if m else f.stem
        img = re.search(r'<img[^>]*src="(?:https?://www\.libelille\.fr)?(/[^"]+\.(?:jpe?g|png|webp))"', t)
        x = extraire_optique(t)
        o = {"url": "/" + f.name, "titre": re.sub(r"\s*-\s*libelille.*$", "", titre, flags=re.I),
             "rubrique": "optique", "type": "optique", "image": x["image"],
             "date": None, **{k: v for k, v in x.items() if k != "image"}}
        if f.name in photos_remplacees:   # vraie photo à la place d'une bannière ou d'un dessin
            ph = photos_remplacees[f.name]
            o.update(image=ph["url"], photo_credit=ph["credit"], photo_page=ph["page"])
        lignes.append(o)
    return lignes


# ── Briques HTML ─────────────────────────────────────────────────────────

def url_de(x):
    return f"/article/{x['slug']}/" if x.get("type", "actu") == "actu" else x["url"]


def visuel(x):
    if x.get("type", "actu") == "actu":
        p = x.get("photo")
        src = p["url"] if p else None
    else:
        src = x.get("photo_url") or x.get("image")
    if src:
        return f'<div class="visuel"><img src="{e(lien(src) if src.startswith("/") else src)}" alt="" loading="lazy" decoding="async"></div>'
    rub = ALIAS_RUB.get(x["rubrique"], x["rubrique"])
    return f'<div class="visuel visuel-vide r-{rub}"><span>{e(nom_rub(rub))}</span></div>'


def carte(x, variante="", avec_visuel=True):
    rub = ALIAS_RUB.get(x["rubrique"], x["rubrique"])
    date = x.get("publie_le") or x.get("date")
    quand = ""
    if x.get("type", "actu") == "actu":
        quand = f'<time datetime="{date}">{date_courte(date)}, {heure_locale(cfg, dt(date)):%Hh%M}</time>'
    elif x.get("type") == "guide":
        quand = '<span class="badge">Guide</span>'
    elif date and rub == "archives":
        d = dt(date)
        quand = f'<time datetime="{date}">{MOIS[d.month - 1].capitalize()} {d.year}</time>'
    chapeau = f'<p class="chapeau">{e(x["chapeau"])}</p>' if variante in ("une", "large") and x.get("chapeau") else ""
    return f"""<article class="carte {variante}"><a href="{lien(url_de(x))}" class="carte-lien">
{visuel(x) if avec_visuel else ''}<div class="carte-texte"><span class="etiquette r-{rub}">{e(nom_rub(rub))}</span>
<h3>{e(x['titre'])}</h3>{chapeau}{quand}</div></a></article>"""


def tete_pub():
    s = ""
    if SITE.get("adsense_client"):
        s += (f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client='
              f'{e(SITE["adsense_client"])}" crossorigin="anonymous"></script>\n')
    if SITE.get("ga4"):
        s += (f'<script async src="https://www.googletagmanager.com/gtag/js?id={e(SITE["ga4"])}"></script>'
              f"<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}"
              f"gtag('js',new Date());gtag('config','{e(SITE['ga4'])}');</script>\n")
    return s


def page(titre, contenu, description="", canonique="/", extra_head="", rub_active="", titre_exact=None):
    nav_actu = "".join(
        f'<a href="{lien(f"/rubrique/{r}/")}"{" class=actif" if r == rub_active else ""}>{e(v["nom"])}</a>'
        for r, v in ACTU.items() if r not in LOCAL)
    if LOCAL:
        actif = " class=actif" if rub_active in LOCAL or rub_active == "local" else ""
        nav_actu += f'<a href="{lien("/rubrique/local/")}"{actif}>Local</a>'
    nav_mag = "".join(
        f'<a href="{lien(f"/rubrique/{r}/")}"{" class=actif" if r == rub_active else ""}>{e(v["nom"])}</a>'
        for r, v in SECTIONS.items())
    titre_complet = f"{titre} — {SITE['nom']}" if titre != SITE["nom"] else f"{SITE['nom']} — {SITE['slogan']}"
    if titre_exact:
        titre_complet = titre_exact
    return f"""<!DOCTYPE html>
<html lang="{SITE['langue']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titre_complet)}</title>
<meta name="description" content="{e((description or SITE['slogan'])[:300])}">
<link rel="canonical" href="{e(absolu(canonique))}">
<link rel="alternate" type="application/rss+xml" title="{e(SITE['nom'])}" href="{lien('/rss.xml')}">
<link rel="stylesheet" href="{lien('/style.css')}">
<link rel="icon" href="{lien('/favicon.svg')}" type="image/svg+xml">
{tete_pub()}{extra_head}
</head>
<body>
<header class="bandeau">
  <div class="bandeau-haut">
    <span class="date-jour" id="date-jour"></span>
    <a href="{lien('/')}" class="logo">{e(SITE['nom'])}<span class="point">.</span></a>
    <span class="slogan">{e(SITE['slogan'])}</span>
  </div>
  <nav class="rubriques"><a href="{lien('/')}"{" class=actif" if rub_active == "une" else ""}>À la une</a>{nav_actu}</nav>
  <nav class="rubriques magazine">{nav_mag}</nav>
</header>
<main>
{contenu}
</main>
<footer class="pied">
  <a href="{lien('/')}" class="logo petit">{e(SITE['nom'])}<span class="point">.</span></a>
  <nav>{nav_actu}{nav_mag}<a href="{lien('/a-propos/')}">À propos</a><a href="{lien('/mentions-legales/')}">Mentions légales</a><a href="{lien('/rss.xml')}">RSS</a></nav>
  <p>© {SITE['nom']}. Photos : Wikimedia Commons (licences libres), <a href="https://pixabay.com/fr/" rel="nofollow noopener">Pixabay</a> et {e(SITE['nom'])}.</p>
</footer>
<script>(function(){{try{{var d=new Date();document.getElementById('date-jour').textContent=d.toLocaleDateString('fr-FR',{{weekday:'long',day:'numeric',month:'long',year:'numeric'}});}}catch(_){{}}}})();</script>
</body>
</html>"""


def ecrire(chemin, contenu):
    f = SORTIE / chemin.lstrip("/")
    if chemin.endswith("/"):
        f = f / "index.html"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(contenu, encoding="utf-8")


def jsonld(type_, titre, description, url, date=None, image=None, section=None):
    d = {"@context": "https://schema.org", "@type": type_, "headline": titre[:110], "description": description or "",
         "inLanguage": "fr", "mainEntityOfPage": absolu(url),
         "author": {"@type": "Organization", "name": SITE["nom"]},
         "publisher": {"@type": "Organization", "name": SITE["nom"]}}
    if date:
        d["datePublished"] = d["dateModified"] = date
    if image:
        d["image"] = [image if image.startswith("http") else absolu(image)]
    if section:
        d["articleSection"] = section
    return f'<script type="application/ld+json">{json.dumps(d, ensure_ascii=False)}</script>'


def og(titre, description, image=None, type_="article"):
    s = (f'<meta property="og:title" content="{e(titre)}">\n<meta property="og:description" content="{e(description or "")}">\n'
         f'<meta property="og:type" content="{type_}">')
    if image:
        s += f'\n<meta property="og:image" content="{e(image if image.startswith("http") else absolu(image))}">'
    return s


# ── Pages ────────────────────────────────────────────────────────────────

OPTIQUE = []  # rempli dans main()
OPTIQUE_UNE = ["/optical-center.php", "/bien-choisir-lunettes-de-vue.php", "/appareil-auditif.php",
               "/acouphenes.php", "/test-auditif-en-ligne.php", "/lentilles-de-contact-en-ligne.php"]


def bloc_optique(titre, pages, classe=""):
    if not pages:
        return ""
    items = "".join(f'<li><a href="{lien(p["url"])}">{e(p["titre"])}</a></li>' for p in pages)
    return (f'<section class="bloc-rubrique bloc-optique {classe}"><h2 class="titre-section">'
            f'<a href="{lien("/rubrique/optique/")}">{e(titre)}</a></h2><ul class="liste-simple">{items}</ul>'
            f'<p><a class="voir-tout" href="{lien("/rubrique/optique/")}">Toute la rubrique Optique &amp; Audition →</a></p></section>')


def optique_pour(url, n=3):
    """Choix stable de quelques pages optique à recommander depuis une page donnée (répartit les liens)."""
    if not OPTIQUE:
        return []
    import hashlib
    k = int(hashlib.md5(url.encode()).hexdigest(), 16)
    return [OPTIQUE[(k + i * 7) % len(OPTIQUE)] for i in range(n)]


def charger_breves(heures=30):
    """Brèves récentes du fil (content/breves/AAAA-MM-JJ.json)."""
    limite = maintenant() - timedelta(hours=heures)
    tout = []
    for f in sorted((RACINE / "content" / "breves").glob("*.json"))[-2:]:
        tout += lire_json(f, [])
    return [b for b in tout if dt(b["publie_le"]) >= limite]


def page_accueil(actus, guides):
    if actus:
        # À la une : l'article le plus récent qui a une photo (sinon le plus récent tout court).
        recents = actus[:8]
        une = next((a for a in recents if a.get("photo")), actus[0])
        suite = [a for a in actus if a is not une][:4]
        # Le fil : articles et brèves mêlés, du plus récent au plus ancien
        elements = [(a["publie_le"], "article", a) for a in actus[:15]]
        elements += [(b["publie_le"], "breve", b) for b in charger_breves()]
        elements.sort(key=lambda x: x[0], reverse=True)
        lignes_fil = []
        for quand, genre, x in elements[:12]:
            h = f'<time>{heure_locale(cfg, dt(quand)):%Hh%M}</time>'
            if genre == "article":
                lignes_fil.append(f'<li>{h}<a href="{lien(url_de(x))}">{e(x["titre"])}</a></li>')
            else:
                lignes_fil.append(f'<li class="breve">{h}<details><summary>{e(x["titre"])}</summary>'
                                  f'<p>{e(x["texte"])}</p></details></li>')
        fil = "".join(lignes_fil)
        haut = f"""<section class="une-zone"><div class="une-principale">{carte(une, 'une')}</div>
<div class="une-secondaires">{''.join(carte(a, 'compacte') for a in suite)}</div>
<aside class="fil-direct"><h2 class="titre-section">Le fil</h2><ol>{fil}</ol></aside></section>"""
    else:
        haut = '<section class="vide"><h1>Les premiers articles arrivent…</h1><p>Le robot publie les actualités du jour dès ce matin.</p></section>'
    blocs = []
    for slug, r in ACTU.items():
        if slug in LOCAL:
            continue
        liste = [a for a in actus if a["rubrique"] == slug][:4]
        if liste:
            blocs.append(f'<section class="bloc-rubrique"><h2 class="titre-section"><a href="{lien(f"/rubrique/{slug}/")}">{e(r["nom"])}</a></h2>'
                         f'<div class="grille">{"".join(carte(a) for a in liste)}</div></section>')
    # Bloc « Près de chez vous » : le dernier article de chaque ville
    derniers = [next((a for a in actus if a["rubrique"] == v), None) for v in LOCAL]
    derniers = [a for a in derniers if a][:8]
    if derniers:
        villes = " · ".join(f'<a href="{lien(f"/rubrique/{v}/")}">{e(LOCAL[v]["nom"])}</a>' for v in LOCAL)
        blocs.insert(1 if blocs else 0, f'<section class="bloc-rubrique"><h2 class="titre-section"><a href="{lien("/rubrique/local/")}">Près de chez vous</a></h2>'
                     f'<p class="villes">{villes}</p><div class="grille">{"".join(carte(a) for a in derniers)}</div></section>')
    phares = [g for g in guides if g.get("phare")][:8] or guides[:8]
    if phares:
        blocs.append('<section class="bloc-rubrique guides"><h2 class="titre-section">Nos guides pratiques</h2>'
                     f'<div class="grille">{"".join(carte(g) for g in phares)}</div></section>')
    une_opt = [o for u in OPTIQUE_UNE for o in OPTIQUE if o["url"] == u]
    blocs.append(bloc_optique("Optique & Audition", une_opt))
    ecrire("/", page(SITE["nom"], haut + "".join(blocs), canonique="/", rub_active="une",
                     extra_head=f'<meta name="description" content="{e(SITE["slogan"])}">'))


def page_rubrique(slug, elements):
    r = TOUTES[slug]
    guides = [x for x in elements if x.get("type") == "guide"]
    autres = [x for x in elements if x.get("type") != "guide"]
    contenu = f'<h1 class="titre-rubrique">{e(r["nom"])}</h1>'
    if slug == "archives":
        annees = sorted({dt(x["date"]).year for x in autres if x.get("date")}, reverse=True)
        contenu += ('<p class="intro">Toute l\'actualité publiée sur le site depuis 2007, classée par année.</p>'
                    '<div class="annees">' + "".join(
                        f'<a href="{lien(f"/{a}.html" if a <= 2011 else f"/archives/{a}/")}">{a}<small>'
                        f'{sum(1 for x in autres if x.get("date") and dt(x["date"]).year == a)} articles</small></a>'
                        for a in annees) + "</div>")
        ecrire(f"/rubrique/{slug}/", page(r["nom"], contenu, f"Les archives de {SITE['nom']}", f"/rubrique/{slug}/", rub_active=slug))
        return
    if guides:
        contenu += f'<h2 class="titre-section">Les guides</h2><div class="grille grille-rubrique">{"".join(carte(g) for g in guides)}</div>'
    if autres:
        titre_liste = "À lire aussi" if guides else "Tous les articles"
        if slug in ACTU:
            titre_liste = "Les dernières actualités"
        contenu += f'<h2 class="titre-section">{titre_liste}</h2>'
        if slug == "optique":
            contenu += ('<p class="intro">Lunettes de vue, lentilles, appareils auditifs, acouphènes, opticiens : '
                        'tous nos articles sur la vue et l\'audition.</p><ul class="liste-simple">') + "".join(
                f'<li><a href="{lien(x["url"])}">{e(x["titre"])}</a></li>' for x in sorted(autres, key=lambda x: x["titre"].lower())) + "</ul>"
        else:
            contenu += f'<div class="grille grille-rubrique">{"".join(carte(x) for x in autres[:120])}</div>'
    if not guides and not autres:
        contenu += "<p>Aucun article pour l'instant.</p>"
    ecrire(f"/rubrique/{slug}/", page(r["nom"], contenu, f"{r['nom']} : toute l'actualité et nos guides", f"/rubrique/{slug}/", rub_active=slug))


def page_local(actus):
    contenu = '<h1 class="titre-rubrique">Local</h1><p class="intro">L\'actualité des huit plus grandes villes de France.</p>'
    contenu += '<p class="villes">' + " · ".join(f'<a href="{lien(f"/rubrique/{v}/")}">{e(r["nom"])}</a>' for v, r in LOCAL.items()) + "</p>"
    for v, r in LOCAL.items():
        liste = [a for a in actus if a["rubrique"] == v][:4]
        contenu += f'<section class="bloc-rubrique"><h2 class="titre-section"><a href="{lien(f"/rubrique/{v}/")}">{e(r["nom"])}</a></h2>'
        contenu += (f'<div class="grille">{"".join(carte(a) for a in liste)}</div>' if liste
                    else "<p>Les premiers articles arrivent bientôt.</p>") + "</section>"
    ecrire("/rubrique/local/", page("Local", contenu, "L'actualité locale : Paris, Marseille, Lyon, Toulouse, Nice, Nantes, Montpellier, Strasbourg", "/rubrique/local/", rub_active="local"))


def page_annee(annee, pages):
    par_mois = defaultdict(list)
    for p in pages:
        par_mois[dt(p["date"]).month].append(p)
    contenu = f'<p class="fil-ariane"><a href="{lien("/rubrique/archives/")}">Archives</a> › {annee}</p><h1 class="titre-rubrique">Archives {annee}</h1>'
    for m in sorted(par_mois, reverse=True):
        liste = sorted(par_mois[m], key=lambda p: p["titre"].lower())
        contenu += f'<h2 class="titre-section">{MOIS[m - 1].capitalize()} {annee}</h2><ul class="liste-simple">' + "".join(
            f'<li><a href="{lien(p["url"])}">{e(p["titre"])}</a></li>' for p in liste) + "</ul>"
    chemin = f"/{annee}.html" if annee <= 2011 else f"/archives/{annee}/"
    ecrire(chemin, page(f"Archives {annee}", contenu, f"Les articles publiés en {annee}", chemin, rub_active="archives"))


def mention(x):
    return f'<aside class="mention-ia">{e(SITE["mention_ia"])}</aside>' if x.get("type", "actu") == "actu" else ""


def bloc_lire_aussi(x, tous):
    rub = ALIAS_RUB.get(x["rubrique"], x["rubrique"])
    autres = [y for y in tous if ALIAS_RUB.get(y["rubrique"], y["rubrique"]) == rub and url_de(y) != url_de(x)]
    if x.get("type") == "page" and rub == "archives" and x.get("date"):
        a = dt(x["date"])
        autres = [y for y in autres if y.get("date") and abs((dt(y["date"]) - a).days) < 40]
    autres = autres[:3]
    if not autres:
        return ""
    return (f'<section class="bloc-rubrique a-lire"><h2 class="titre-section">À lire aussi</h2>'
            f'<div class="grille">{"".join(carte(y) for y in autres)}</div></section>')


def page_article(a, tous):
    rub = a["rubrique"]
    p = a.get("photo")
    url = url_de(a)
    figure = ""
    if p:
        lic = f'<a href="{e(p["licence_url"])}" rel="license">{e(p["licence"])}</a>' if p.get("licence_url") else e(p["licence"])
        figure = (f'<figure class="photo-article"><img src="{e(p["url"])}" alt="{e(p.get("legende") or a["titre"])}">'
                  f'<figcaption>{e(p.get("legende", ""))} <span class="credit">Photo : {e(p["credit"])} · {lic} · '
                  f'<a href="{e(p["page"])}">{e(p.get("source", "Wikimedia Commons"))}</a></span></figcaption></figure>')
    corps = markdown.markdown(html.escape(a["corps"], quote=False), extensions=["sane_lists"])
    contenu = f"""<article class="article"><header>
<a class="etiquette r-{rub}" href="{lien(f"/rubrique/{rub}/")}">{e(nom_rub(rub))}</a>
<h1>{e(a['titre'])}</h1><p class="chapeau">{e(a['chapeau'])}</p>
<p class="meta">Publié le <time datetime="{a['publie_le']}">{date_longue(a['publie_le'])}</time></p></header>
{figure}<div class="texte">{corps}</div>{mention(a)}</article>{bloc_lire_aussi(a, tous)}"""
    img = p["url"] if p else None
    head = jsonld("NewsArticle", a["titre"], a["chapeau"], url, a["publie_le"], img, nom_rub(rub)) + og(a["titre"], a["chapeau"], img)
    ecrire(url, page(a["titre"], contenu, a["chapeau"], url, head, rub_active=rub))


def page_guide(g, tous):
    url = g["url"]
    rub = g["rubrique"]
    img = g.get("photo_url") or g.get("image")
    if g.get("photo_url"):
        figure = (f'<figure class="photo-article"><img src="{e(lien(g["photo_url"]))}" alt="">'
                  f'<figcaption><span class="credit">Photo : <a href="{e(g.get("photo_page", "https://www.pexels.com"))}" '
                  f'rel="nofollow noopener">{e(g.get("photo_credit", ""))} / {e(g.get("photo_source", "Pexels"))}</a></span></figcaption></figure>')
    elif img:
        figure = f'<figure class="photo-article"><img src="{e(lien(img))}" alt=""></figure>'
    else:
        figure = ""
    maj = f'<p class="meta">Mis à jour le {date_longue(g["date"], heure=False)}</p>'
    contenu = f"""<article class="article guide"><header>
<a class="etiquette r-{rub}" href="{lien(f"/rubrique/{rub}/")}">{e(nom_rub(rub))} · Guide</a>
<h1>{e(g['titre'])}</h1><p class="chapeau">{e(g.get('chapeau', ''))}</p>{maj}</header>
{figure}<div class="texte">{g['corps_html']}</div>
{'<aside class="avertissement">' + e(g['avertissement']) + '</aside>' if g.get('avertissement') else ''}</article>
{bloc_lire_aussi(g, tous)}{bloc_optique("Vue et audition", optique_pour(url), "compact") if rub in ("sante", "beaute") else ""}"""
    head = jsonld("Article", g["titre"], g.get("chapeau", ""), url, g["date"], img, nom_rub(rub)) + og(g["titre"], g.get("chapeau"), img)
    ecrire(url, page(g["titre"], contenu, g.get("description") or g.get("chapeau", ""), url, head, rub_active=rub))


def page_ancienne(p, tous):
    url = p["url"]
    rub = p["rubrique"]
    img = p.get("image")
    figure = f'<figure class="photo-article"><img src="{e(lien(img))}" alt="{e(p["titre"])}"></figure>' if img else ""
    meta = ""
    if p.get("date"):
        d = dt(p["date"])
        meta = (f'<p class="meta">Publié en {MOIS[d.month - 1]} {d.year}</p>' if rub == "archives" and d.year <= 2011
                else f'<p class="meta">Publié le {date_longue(p["date"], heure=False)}</p>')
    ariane = ""
    if rub == "archives" and p.get("date"):
        an = dt(p["date"]).year
        ariane = (f'<p class="fil-ariane"><a href="{lien("/rubrique/archives/")}">Archives</a> › '
                  f'<a href="{lien(f"/{an}.html" if an <= 2011 else f"/archives/{an}/")}">{an}</a></p>')
    contenu = f"""<article class="article">{ariane}<header>
<a class="etiquette r-{rub}" href="{lien(f"/rubrique/{rub}/")}">{e(nom_rub(rub))}</a>
<h1>{e(p['titre'])}</h1>{meta}</header>{figure}<div class="texte">{p['corps']}</div></article>{bloc_lire_aussi(p, tous)}{bloc_optique("Vue et audition", optique_pour(url), "compact") if rub in ("famille", "people", "loisirs", "maison", "sport") else ""}"""
    desc = re.sub(r"<[^>]+>", " ", p["corps"])
    desc = html.unescape(re.sub(r"\s+", " ", desc)).strip()[:160]
    head = jsonld("Article", p["titre"], desc, url, p.get("date"), img, nom_rub(rub)) + og(p["titre"], desc, img)
    ecrire(url, page(p["titre"], contenu, desc, url, head, rub_active=rub))


def page_statiques():
    apropos = f"""<article class="article statique"><h1>À propos de {e(SITE['nom'])}</h1>
<p class="chapeau">{e(SITE['nom'])} publie chaque jour l'essentiel de l'actualité française et internationale, ainsi que des guides pratiques sur l'argent, la santé et la vie quotidienne.</p>
<div class="texte"><h2>Comment sont produits nos articles</h2>
<p>Les articles d'actualité sont préparés à l'aide d'une intelligence artificielle à partir d'informations recoupées entre plusieurs sources publiques. Ils le signalent explicitement.</p>
<p>Nos guides pratiques sont mis à jour régulièrement. Ils ne remplacent pas l'avis d'un professionnel (médecin, conseiller financier, notaire…).</p>
<h2>Archives</h2><p>Le site publie de l'information depuis 2007. Les articles plus anciens sont consultables dans la rubrique <a href="{lien('/rubrique/archives/')}">Archives</a>.</p>
<h2>Nous contacter</h2><p>Une erreur, une remarque ? Écrivez-nous : nous corrigerons rapidement.</p></div></article>"""
    ecrire("/a-propos/", page("À propos", apropos, canonique="/a-propos/"))
    ml = RACINE / "content" / "mentions-legales.html"
    corps = ml.read_text(encoding="utf-8") if ml.exists() else "<p>À compléter : éditeur du site, directeur de la publication, hébergeur, contact.</p>"
    ecrire("/mentions-legales/", page("Mentions légales", f'<article class="article statique"><h1>Mentions légales</h1><div class="texte">{corps}</div></article>', canonique="/mentions-legales/"))
    ecrire("/404.html", page("Page introuvable", f'<section class="vide"><h1>Page introuvable</h1><p><a href="{lien("/")}">Retour à l\'accueil</a></p></section>'))
    ecrire("/410.html", page("Page supprimée", f'<section class="vide"><h1>Cette page a été supprimée</h1><p><a href="{lien("/")}">Retour à l\'accueil</a></p></section>'))


# ── Redirections, flux, plans de site ────────────────────────────────────

def htaccess():
    r = lire_json(RACINE / "state" / "redirections.json", {"301": [], "410": []})
    def q(s):
        return '"' + s.replace('"', '\\"') + '"'
    lignes = [
        "# Généré automatiquement par build.py : ne pas modifier à la main.",
        "DirectoryIndex index.html index.php",
        "ErrorDocument 404 /404.html",
        "ErrorDocument 410 /410.html",
        "",
        "RewriteEngine on",
        "RewriteCond %{SERVER_PORT} ^80$",
        "RewriteRule .* https://www.libelille.fr%{REQUEST_URI} [R=301,L]",
        "RewriteCond %{HTTP_HOST} ^libelille\\.fr$ [NC]",
        "RewriteRule ^(.*)$ https://www.libelille.fr/$1 [R=301,L]",
        "RewriteRule ^index\\.php$ / [R=301,L]",
        "",
        "# Anciennes pages fusionnées ou déplacées",
    ]
    lignes += [f"Redirect 301 {q(a)} {q(b)}" for a, b in r["301"]]
    lignes += ["", "# Anciennes pages supprimées"] + [f"Redirect gone {q(a)}" for a in r["410"]]
    anciens = []
    for f in sorted((RACINE / "legacy").glob("*.*")):
        if f.suffix in (".php", ".html") and not any(o["url"] == "/" + f.name for o in OPTIQUE):
            try:
                f.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                anciens.append(re.escape(f.name))
    if anciens:
        # l'ordre compte : la règle la plus précise (Windows-1252) doit venir après la règle générale
        lignes += ["", '<FilesMatch "\\.(html|php)$">', "  AddDefaultCharset UTF-8", "</FilesMatch>",
                   "# Pages anciennes gardées telles quelles, encodées en Windows-1252 (accents)",
                   f'<FilesMatch "^({"|".join(anciens)})$">', "  AddDefaultCharset windows-1252",
                   "  <IfModule mod_headers.c>", '    Header always set Content-Type "text/html; charset=windows-1252"', "  </IfModule>",
                   "</FilesMatch>"]
        (RACINE / "state" / "pages-windows-1252.txt").write_text("\n".join(f.replace("\\", "") for f in anciens), encoding="utf-8")
    lignes += ["", "# Fichiers internes inclus par les anciennes pages : pas d'accès direct",
               '<FilesMatch "^(touc1?|sbjp)\\.php$">', "  Require all denied", "</FilesMatch>", ""]
    (SORTIE / ".htaccess").write_text("\n".join(lignes), encoding="utf-8")
    # Même chose pour nginx (si l'hébergement n'utilise pas Apache)
    ng = ["# À inclure dans le bloc server { } de www.libelille.fr", "error_page 404 /404.html;", "error_page 410 /410.html;"]
    ng += [f"location = {q(a)} {{ return 301 {b}; }}" for a, b in r["301"]]
    ng += [f"location = {q(a)} {{ return 410; }}" for a in r["410"]]
    ng += ["location ~ \\.php$ { default_type text/html; }  # si PHP n'est pas installé"]
    (RACINE / "state" / "nginx-libelille.conf").write_text("\n".join(ng), encoding="utf-8")
    return len(r["301"]), len(r["410"])


def flux_et_sitemaps(actus, guides, pages, optique):
    items = "".join(
        f"""<item><title>{e(a['titre'])}</title><link>{e(absolu(url_de(a)))}</link><guid>{e(absolu(url_de(a)))}</guid>
<pubDate>{format_datetime(dt(a['publie_le']))}</pubDate><category>{e(nom_rub(a['rubrique']))}</category>
<description>{e(a['chapeau'])}</description></item>""" for a in actus[:50])
    ecrire("/rss.xml", f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>{e(SITE['nom'])}</title><link>{e(absolu('/'))}</link>
<description>{e(SITE['slogan'])}</description><language>fr-fr</language>{items}</channel></rss>""")

    def url_xml(u, lastmod=None):
        lm = f"<lastmod>{lastmod[:10]}</lastmod>" if lastmod else ""
        return f"<url><loc>{e(absolu(u))}</loc>{lm}</url>"
    urls = [url_xml("/")] + [url_xml(f"/rubrique/{s}/") for s in TOUTES] + ([url_xml("/rubrique/local/")] if LOCAL else [])
    urls += [url_xml(url_de(a), a["publie_le"]) for a in actus]
    urls += [url_xml(g["url"], g["date"]) for g in guides]
    urls += [url_xml(p["url"], p.get("date")) for p in pages]
    urls += [url_xml(o["url"]) for o in optique]
    ecrire("/sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           + "".join(urls) + "</urlset>")
    limite = maintenant() - timedelta(hours=48)
    news = "".join(
        f"""<url><loc>{e(absolu(url_de(a)))}</loc><news:news><news:publication><news:name>{e(SITE['nom'])}</news:name>
<news:language>fr</news:language></news:publication><news:publication_date>{a['publie_le']}</news:publication_date>
<news:title>{e(a['titre'])}</news:title></news:news></url>""" for a in actus if dt(a["publie_le"]) >= limite)
    ecrire("/news-sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
           'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">' + news + "</urlset>")
    ecrire("/robots.txt", f"User-agent: *\nAllow: /\nSitemap: {absolu('/sitemap.xml')}\nSitemap: {absolu('/news-sitemap.xml')}\n")


def main():
    if SORTIE.exists():
        shutil.rmtree(SORTIE)
    SORTIE.mkdir()
    # 1) fichiers repris tels quels (pages optique, images, ads.txt), puis le style du nouveau site
    if (RACINE / "legacy").exists():
        shutil.copytree(RACINE / "legacy", SORTIE, dirs_exist_ok=True)
    for f in (RACINE / "static").iterdir():
        shutil.copy(f, SORTIE / f.name)
    if DOMAINE:
        (SORTIE / "CNAME").write_text(DOMAINE + "\n")
    (SORTIE / ".nojekyll").write_text("")

    actus = tous_les_articles()
    for a in actus:
        a["type"] = "actu"
    guides = charger_guides()
    pages = charger_pages()
    optique = charger_optique()
    OPTIQUE[:] = sorted(optique, key=lambda o: o["url"])
    pages.sort(key=lambda p: p.get("date") or "", reverse=True)
    tous = actus + guides + pages + optique

    page_accueil(actus, guides)
    par_rub = defaultdict(list)
    for x in tous:
        par_rub[ALIAS_RUB.get(x["rubrique"], x["rubrique"])].append(x)
    for slug in TOUTES:
        page_rubrique(slug, par_rub.get(slug, []))
    if LOCAL:
        page_local(actus)
    for a in actus:
        page_article(a, tous)
    for g in guides:
        page_guide(g, tous)
    for p in pages:
        page_ancienne(p, tous)
    for o in optique:
        page_optique(o, tous)
    par_annee = defaultdict(list)
    for p in pages:
        if p["rubrique"] == "archives" and p.get("date"):
            par_annee[dt(p["date"]).year].append(p)
    for an, lst in par_annee.items():
        page_annee(an, lst)
    page_statiques()
    n301, n410 = htaccess()
    flux_et_sitemaps(actus, guides, pages, optique)
    print(f"Site généré : {len(actus)} actus, {len(guides)} guides, {len(pages)} anciens articles, "
          f"{len(optique)} pages optique (même adresse, nouveau design), {n301} redirections, {n410} suppressions → {SORTIE}")


if __name__ == "__main__":
    main()
