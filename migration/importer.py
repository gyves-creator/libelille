"""Import de l'ancien libelille.fr dans le nouveau projet.

    python importer.py /chemin/vers/LIB /chemin/vers/projet

Produit dans le projet :
  content/pages/*.json      pages reprises dans le nouveau design (même adresse)
  legacy/                   fichiers copiés tels quels (pages optique, leurs inclusions, images utilisées)
  state/redirections.json   301 / 410 à appliquer
  state/migration.csv       table de correspondance complète (à garder comme trace)
"""
import csv
import hashlib
import json
import os
import re
import shutil
import sys
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup, Comment

sys.path.insert(0, os.path.dirname(__file__))
import plan  # noqa: E402
from lib import decode_name  # noqa: E402

SRC = sys.argv[1] if len(sys.argv) > 1 else plan.SRC
DEST = sys.argv[2] if len(sys.argv) > 2 else "/home/claude/libelille"
plan.SRC = SRC

ALLOWED = {"p", "h2", "h3", "h4", "ul", "ol", "li", "strong", "b", "em", "i", "a", "img", "blockquote", "br", "table",
           "thead", "tbody", "tr", "td", "th"}
MOIS = {m: i for i, m in enumerate("janvier février mars avril mai juin juillet août septembre octobre novembre décembre".split(), 1)}


def construire_index():
    lignes_php = plan.plan_php()
    lignes_arc = plan.plan_archive()
    toutes = lignes_php + lignes_arc
    par_url = {l["ancien"]: l for l in toutes}
    return toutes, par_url


def cible_finale(url, par_url):
    """Où doit pointer un lien vers une ancienne adresse ?"""
    l = par_url.get(url)
    if not l:
        # ancienne page .php/.html qui n'existe plus nulle part : lien mort
        return None if re.search(r"\.(php|html?)$", url) and not re.match(r"^/20\d\d\.html$", url) else url
    if l["action"] in ("guide", "redirect"):
        return cible_finale(l["cible"], par_url) if l["cible"] in par_url else l["cible"]
    if l["action"] == "gone":
        return None
    return url


def normaliser_lien(href):
    if not href or "<" in href or " " in href.strip():
        return None
    if href.startswith("www."):
        return "http://" + href.rstrip(".")
    u = urlparse(href.strip())
    if u.netloc and "libelille.fr" not in u.netloc:
        return href  # lien externe
    chemin = unquote(u.path or "/")
    if not chemin.startswith("/"):
        chemin = "/" + chemin
    return chemin


def nettoyer(fragment, par_url, images):
    soup = BeautifulSoup(fragment, "lxml")
    for el in soup.find_all(["script", "style", "ins", "form", "iframe", "center", "noscript"]):
        if el.name == "center":
            el.unwrap()
        else:
            el.decompose()
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    for el in soup.find_all(True):
        if el.name in ("html", "body"):
            continue
        if el.name == "h1":
            el.decompose()
            continue
        if el.name not in ALLOWED:
            el.unwrap()
            continue
        attrs = {}
        if el.name == "a":
            href = normaliser_lien(el.get("href"))
            if href and href.startswith("/"):
                href = cible_finale(href, par_url)
            if not href:
                el.unwrap()
                continue
            attrs["href"] = href
            if href.startswith("http"):
                attrs["rel"] = "nofollow noopener"
        elif el.name == "img":
            src = normaliser_lien(el.get("src"))
            if not src or not src.startswith("/") or re.search(r"rachatdecredit|comparateur|logo\.|rachat-credit\.png", src):
                el.decompose()
                continue
            images.add(src)
            attrs = {"src": src, "alt": el.get("alt", ""), "loading": "lazy"}
        el.attrs = attrs
    corps = soup.body.decode_contents() if soup.body else str(soup)
    corps = re.sub(r"(<br/?>\s*){2,}", "<br>", corps)
    corps = re.sub(r"<p>\s*(<br/?>)?\s*</p>", "", corps)
    corps = re.sub(r"(</(p|h2|h3|h4|ul|ol|blockquote|table)>)\s*(<br/?>\s*)+", r"\1\n", corps)
    corps = re.sub(r"(<br/?>\s*)+(<(p|h2|h3|h4|ul|ol|blockquote|table)[ >])", r"\2", corps)
    corps = re.sub(r"^[\s|]*(<br/?>[\s|]*)*", "", corps)
    corps = re.sub(r"(\s*<br/?>)+\s*$", "", corps)
    return corps.strip()


def date_page(t, url):
    m = re.search(r'datetime="(\d{4}-\d{2}-\d{2}T\d\d:\d\d:\d\d[+-]\d\d:\d\d)"', t)
    if m:
        return m.group(1)
    m = re.match(r"/(20\d\d)/(\d\d)/", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-01T12:00:00+01:00"
    return None


def extraire(l, par_url, images):
    b = open(l["fichier"], "rb").read()
    try:
        t = b.decode("utf-8")
    except UnicodeDecodeError:
        t = b.decode("cp1252", errors="replace")
    t = re.sub(r"<\?php.*?\?>", "", t, flags=re.S)
    soup = BeautifulSoup(t, "lxml")
    for el in soup.select('[itemprop="Publisher"], time[itemprop], ul.navbar, #img'):
        el.decompose()
    zone = soup.select_one("div.entry-content") or soup.body
    html_zone = str(zone)
    if zone.name == "body":
        parts = re.split(r"</h1>", html_zone, maxsplit=1)
        html_zone = parts[1] if len(parts) > 1 else html_zone
    html_zone = re.split(r"<h3>\s*Sur le même thème|<h4>\s*A lire|Mentions légales", html_zone)[0]
    html_zone = re.sub(r"^\s*(</?(span|center|div|p|br)[^>]*>\s*|\|\s*)+", "", html_zone)
    corps = nettoyer(html_zone, par_url, images)
    imgs = re.findall(r'<img[^>]*src="([^"]+)"', corps)
    image = imgs[0] if imgs else None
    if image:  # la première image devient l'image d'en-tête : on l'enlève du texte
        corps = re.sub(r'<img[^>]*src="%s"[^>]*/?>' % re.escape(image), "", corps, count=1).strip()
        corps = re.sub(r"^(<p>\s*</p>|<br/?>|\s)+", "", corps)
    return corps, date_page(t, l["ancien"]), image


def main():
    toutes, par_url = construire_index()
    for d in ("content/pages", "legacy", "state"):
        os.makedirs(os.path.join(DEST, d), exist_ok=True)
    for f in os.listdir(os.path.join(DEST, "content/pages")):
        os.remove(os.path.join(DEST, "content/pages", f))
    shutil.rmtree(os.path.join(DEST, "legacy"))
    os.makedirs(os.path.join(DEST, "legacy"))

    # anciennes redirections du .htaccess (à conserver)
    anciennes = []
    for ligne in open(os.path.join(SRC, ".htaccess"), "rb").read().decode("cp1252", errors="replace").splitlines():
        m = re.match(r"Redirect 301 (\S+) (\S+)$", ligne.strip())
        if m and "�" not in m.group(1) and "?" not in m.group(1):
            anciennes.append([m.group(1), "/"])

    sources_anciennes = {a for a, _ in anciennes}
    images = set()
    pages = 0
    for l in toutes:
        if l["action"] == "import" and l["ancien"] in sources_anciennes:
            continue  # déjà redirigée vers l'accueil par l'ancien site : on respecte ce choix
        if l["action"] == "import":
            corps, date, image = extraire(l, par_url, images)
            if image:
                pass
            doc = {"url": l["ancien"], "titre": l["titre"], "rubrique": l["rubrique"], "date": date,
                   "image": image, "corps": corps, "mots": l["mots"]}
            nom = hashlib.md5(l["ancien"].encode()).hexdigest()[:12] + ".json"
            with open(os.path.join(DEST, "content/pages", nom), "w", encoding="utf-8") as fh:
                json.dump(doc, fh, ensure_ascii=False)
            pages += 1
        elif l["action"] == "asis":
            dest = os.path.join(DEST, "legacy", l["ancien"].lstrip("/"))
            shutil.copyfile(l["fichier"], dest)
            t = open(l["fichier"], "rb").read().decode("utf-8", errors="replace")
            for src in re.findall(r'(?:src|href)="([^"]+)"', t):
                p = normaliser_lien(src)
                if p and p.startswith("/") and re.search(r"\.(jpe?g|png|webp|gif|css|svg)$", p, re.I):
                    images.add(p)

    # images et feuilles de style utilisées par les pages gardées (pas les 260 Mo complets)
    src_noms = {decode_name(b)[0]: b for b in os.listdir(SRC.encode()) if not os.path.isdir(os.path.join(SRC.encode(), b))}
    copiees, manquantes = 0, 0
    for img in sorted(images):
        nom = img.lstrip("/")
        b = src_noms.get(nom)
        if b is None:
            manquantes += 1
            continue
        shutil.copyfile(os.path.join(SRC.encode(), b), os.path.join(DEST, "legacy", nom))
        copiees += 1
    shutil.copyfile(os.path.join(SRC, "ads.txt"), os.path.join(DEST, "legacy", "ads.txt"))

    redir = {"301": [], "410": []}
    for l in toutes:
        if l["action"] in ("guide", "redirect"):
            redir["301"].append([l["ancien"], cible_finale(l["ancien"], par_url)])
        elif l["action"] == "gone":
            redir["410"].append(l["ancien"])
    deja = {a for a, _ in redir["301"]}
    redir["301"] += [a for a in anciennes if a[0] not in deja and a[0] not in ("/rss.xml", "/sitemap.xml", "/robots.txt")]
    # résoudre les chaînes de redirections (A -> B -> C devient A -> C)
    table = dict(redir["301"])
    def fin(u, n=0):
        return fin(table[u], n + 1) if u in table and n < 10 else u
    redir["301"] = [[a, fin(b)] for a, b in redir["301"] if fin(b) != a]
    json.dump(redir, open(os.path.join(DEST, "state/redirections.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    with open(os.path.join(DEST, "state/migration.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Ancienne adresse", "Titre", "Action", "Nouvelle adresse", "Rubrique", "Mots"])
        for l in toutes:
            w.writerow([l["ancien"], l["titre"], l["action"], cible_finale(l["ancien"], par_url) or "(supprimée)",
                        l["rubrique"], l["mots"]])
    print(f"{pages} pages importées, {sum(1 for l in toutes if l['action']=='asis')} gardées telles quelles, "
          f"{copiees} fichiers d'images/styles copiés ({manquantes} introuvables), "
          f"{len(redir['301'])} redirections 301, {len(redir['410'])} suppressions 410")


if __name__ == "__main__":
    main()
