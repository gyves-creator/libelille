# libelille.fr — nouveau site

Ce dossier contient **tout le nouveau libelille.fr** :

- **la page d'accueil d'actualité**, alimentée chaque heure par le robot (6 rubriques : Politique, International, Économie, Société, Sport, Tech, environ 10 articles par jour au départ) ;
- **34 guides** (Argent, Santé, Beauté & Mode, Maison), qui remplacent environ 500 anciennes pages ;
- **1 229 anciens articles** repris dans le nouveau design, **à la même adresse** (Famille, Maison, Loisirs, People, Sport, Archives 2007-2024) ;
- **45 pages optique et audition**, copiées strictement **telles quelles** ;
- **849 redirections 301** (chaque ancienne page fusionnée renvoie vers son guide) et **9 suppressions 410** ;
- tes publicités **AdSense** (même compte que l'ancien site) et ton fichier `ads.txt`.

La table complète « ancienne adresse → nouvelle adresse » est dans `state/migration.csv`.

---

## Mise en ligne (une seule fois, environ 30 minutes)

### 1. Sauvegarder l'ancien site (indispensable)
Avec FileZilla (gratuit), connecte-toi au FTP de ton hébergement OVH et télécharge **tout le dossier `www`** sur ton ordinateur.
Garde cette copie : elle permet de revenir en arrière à tout moment.

> Les identifiants FTP sont dans ton espace client OVH : **Web Cloud → Hébergements → ton hébergement → FTP-SSH**.

### 2. Créer les clés gratuites
- Gemini (rédaction) : https://aistudio.google.com/apikey
- Groq (rédaction, secours) : https://console.groq.com/keys
- Pexels (vraies photos) : crée un compte sur https://www.pexels.com/fr-fr/ puis demande ta clé sur https://www.pexels.com/api/

### 3. Mettre le projet sur GitHub
Le projet contient plus de 1 500 fichiers : l'envoi par le navigateur est limité à 100 fichiers à la fois.
Le plus simple : installer **GitHub Desktop** (gratuit), choisir **File → Add local repository** sur ce dossier,
puis **Publish repository**. Le dépôt peut rester **privé**.

### 4. Donner les accès au robot
Dans le dépôt GitHub : **Settings → Secrets and variables → Actions → New repository secret** :

| Nom | Valeur |
|---|---|
| `GEMINI_API_KEY` | ta clé Gemini |
| `GROQ_API_KEY` | ta clé Groq |
| `PEXELS_API_KEY` | ta clé Pexels |
| `FTP_SERVER` | le serveur FTP OVH (du type `ftp.clusterXXX.hosting.ovh.net`) |
| `FTP_USER` | ton identifiant FTP |
| `FTP_PASSWORD` | ton mot de passe FTP |
| `FTP_DOSSIER` | facultatif : `www/` par défaut |

### 5. Premier envoi du site
**Actions → Publication automatique → Run workflow**, mets **`0`** dans le champ, puis **Run**.
Le site est construit et envoyé sur OVH, sans publier d'article (le premier envoi prend quelques minutes).
Vérifie le site, quelques anciennes adresses, une page optique.

Ensuite, relance avec **`3`** pour publier les trois premiers articles. Le robot tourne ensuite tout seul, chaque heure.

**Horaires de publication** (réglables dans `config.yaml`, bloc `creneaux`) : les articles nationaux sortent juste avant
les pics de lecture sur mobile : 6 h-7 h (trajets du matin), 11 h-12 h (pause déjeuner), 16 h-17 h (retour du travail) et 20 h (soirée).
Les infos locales importantes sortent dès qu'elles tombent ; le rattrapage local a lieu à 16 h.

### 6. Prévenir Google
Dans **Google Search Console** → **Sitemaps**, ajoute :
- `https://www.libelille.fr/sitemap.xml`
- `https://www.libelille.fr/news-sitemap.xml`

### 7. Publicité et cookies (obligatoire en Europe)
Dans **AdSense → Confidentialité et messages**, active le message de consentement européen (RGPD).
Il s'affiche automatiquement sur le site, sans rien changer au code.

### 8. Mentions légales
Complète les champs `[À COMPLÉTER]` dans `content/mentions-legales.html` (nom de l'éditeur, directeur de la publication).

---

## La rubrique Présidentielle 2027

- Au moins **un article par jour** sur la présidentielle (deux au maximum), publié en priorité.
- Consignes de rédaction renforcées : neutralité stricte entre candidats, sondages toujours cités avec institut,
  date et échantillon, aucun conseil de vote.
- **Silence électoral automatique** : aucun article de la rubrique la veille du scrutin et le jour même avant 20 h
  (17-18 avril et 1er-2 mai 2027).
- Un guide permanent « Présidentielle 2027 : le calendrier et comment voter » (sources officielles).
- Réglages dans `config.yaml`, rubrique `presidentielle`.

## L'actualité locale (8 villes)

- Les **8 plus grandes villes de France** : Paris, Marseille, Lyon, Toulouse, Nice, Nantes, Montpellier, Strasbourg.
- **Jusqu'à deux articles par ville et par jour** (le 2e uniquement pour une info importante), regroupés sous l'onglet **Local** et dans le bloc « Près de chez vous » de l'accueil.
- **Publication déclenchée par l'actualité** : rien avant 8 h. Ensuite, chaque heure, le robot ne publie pour une ville
  que si une **info importante** tombe (reprise par au moins 2 médias, ou contenant un mot-clé comme accident, incendie,
  grève, alerte, coupure… et datant de moins de 4 h).
- **Rattrapage à 16 h** : si rien n'a été publié pour une ville dans la journée, le robot prend le meilleur sujet du jour.
- Réglages (heures, seuils) dans `config.yaml`, bloc `declenchement` de la première ville (Paris), partagé par les 8 villes.
- Sources : le quotidien régional de chaque ville et Google Actualités (recherche sur la ville, dernières 24 h).
  Le robot ne garde que les dépêches qui citent la ville ou ses environs, et écarte la politique nationale.
- Règles renforcées pour les faits divers : aucun nom de victime, de mineur ou de suspect, présomption d'innocence,
  pas de détail macabre, conditionnel si une seule source.
- **Au premier lancement**, regarde le journal dans l'onglet Actions : si le flux d'un quotidien régional est marqué ✗,
  remplace son adresse dans `config.yaml` (le flux Google Actualités suffit en attendant).
- Pour changer de ville : copie le bloc d'une ville dans `config.yaml` et adapte le nom, le filtre et les flux.

## Les photos

- **Articles d'actu** : le robot cherche d'abord une vraie photo du sujet sur Wikimedia Commons (personne, lieu, institution),
  puis une photo d'illustration réaliste sur Pexels, et en dernier recours affiche le bandeau coloré de la rubrique.
  Le photographe et la source sont toujours crédités sous la photo.
- **Guides** : au premier passage, chaque guide reçoit automatiquement une vraie photo Pexels (ligne `photo_recherche` du guide).
  Pour en changer : supprime les lignes `photo_url`, `photo_credit` et `photo_page` du guide, et modifie `photo_recherche`.
- Aucune image n'est générée par IA.

## Au quotidien

- **Réglages** (nom du site, nombre d'articles, rubriques, flux) : `config.yaml`.
- **Modifier un guide** : les fichiers texte de `content/guides/`.
- **Supprimer un article du robot** : supprime son fichier dans `content/articles/`.
- **Suivre le robot** : onglet **Actions** de GitHub (journal de chaque passage).
- **Augmenter le rythme** : passe `articles_par_jour` à 15 puis 20 quand Search Console montre que le site décolle.

## Ce qui a été fait sur les anciennes pages

| Thème | Avant | Après |
|---|---|---|
| Minceur | ≈ 370 pages | 15 guides santé (redirections 301) |
| Beauté & mode | ≈ 60 pages | 5 guides |
| Santé, nutrition | ≈ 25 pages | 7 guides |
| Crédit, argent | ≈ 55 pages | 7 guides |
| Optique & audition | 45 pages | **inchangées** (même adresse, même contenu) |
| Famille, maison, loisirs, people, sport, actu 2017-2024 | ≈ 55 pages | gardées, nouveau design, même adresse |
| Archives 2007-2011 | 1 657 fichiers | 1 175 articles uniques, même adresse (doublons redirigés) |
| Pages techniques et inutiles | 9 | supprimées (410) |

Les anciennes redirections de ton `.htaccess` sont conservées.

## Pour les curieux : régénérer depuis l'ancien site
Les scripts de migration (`plan.py`, `importer.py`, `images_guides.py`) sont dans le dossier `migration/`.
