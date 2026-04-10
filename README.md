# People Power — peoplepower.radio

Statische website voor People Power, gehost op Scaleway (EU).

## Architectuur

```
peoplepower-scw/
├── public/                   Statische frontend (HTML/CSS/JS/images)
│   ├── index.html
│   ├── style.css
│   ├── app.js                Audio player + RSS rendering
│   ├── config.js             API URL config (na deploy invullen)
│   ├── logo-pp.png
│   ├── logo-pp-orange.png
│   └── banner.png
└── functions/
    └── episodes/
        ├── handler.py        Python Serverless Function
        └── requirements.txt  (leeg, alleen stdlib)
```

**Twee componenten:**
1. **Statische frontend** → Scaleway Object Storage + CDN (regio: `fr-par` Parijs of `nl-ams` Amsterdam)
2. **Serverless Function** → Scaleway Serverless Functions (zelfde regio), haalt elke 10 min de Springcast RSS op en geeft JSON terug

## Stappen voor Claude Code

### 1. Vereisten controleren

```bash
which scw || echo "Scaleway CLI niet geïnstalleerd"
scw version
```

Als de CLI niet aanwezig is, installeren via:
```bash
# macOS
brew install scaleway-cli

# Linux
curl -s https://raw.githubusercontent.com/scaleway/scaleway-cli/master/scripts/get.sh | sh
```

### 2. Authenticeren

Glenn moet eenmalig een API token aanmaken op:
https://console.scaleway.com/iam/api-keys

Daarna:
```bash
scw init
# Plak access key + secret key
# Kies regio: nl-ams (Amsterdam) of fr-par (Parijs)
```

### 3. Serverless Function deployen

```bash
cd functions/episodes

# Maak een namespace aan (eenmalig)
scw function namespace create name=peoplepower region=nl-ams

# Note: noteer de namespace ID die teruggegeven wordt
NAMESPACE_ID="<id-uit-vorige-stap>"

# Function aanmaken
scw function function create \
  namespace-id=$NAMESPACE_ID \
  name=episodes \
  runtime=python311 \
  handler=handler.handle \
  privacy=public \
  http-option=enabled \
  region=nl-ams

# Code uploaden en deployen
zip -r episodes.zip handler.py requirements.txt
scw function function deploy \
  function-id=<id-van-vorige-stap> \
  zip-file=episodes.zip
```

De CLI geeft een endpoint terug zoals:
`https://peoplepowerepisodes-xxx.functions.fnc.nl-ams.scw.cloud`

**Test deze URL** met `curl` om te checken of er JSON met afleveringen terugkomt.

### 4. API URL invullen in frontend

```bash
cd ../../public
# Vervang REPLACE_WITH_SCALEWAY_FUNCTION_URL in config.js met de echte URL
```

### 5. Statische site uploaden naar Object Storage

```bash
# Maak een bucket aan
scw object bucket create name=peoplepower-radio region=nl-ams

# Bucket public maken
scw object bucket update name=peoplepower-radio acl=public-read region=nl-ams

# Files uploaden (uit /public)
cd ../public
for f in *; do
  scw object object put bucket=peoplepower-radio key=$f file=$f acl=public-read region=nl-ams
done

# Static website hosting aanzetten
scw object bucket update-website-configuration \
  name=peoplepower-radio \
  index-document=index.html \
  region=nl-ams
```

De bucket krijgt nu een publieke URL zoals:
`https://peoplepower-radio.s3-website.nl-ams.scw.cloud`

### 6. CDN/Edge aanzetten (optioneel maar aanbevolen)

Voor snellere performance en HTTPS op een custom domein:
- Scaleway "Edge Services" aanzetten via console
- Of Cloudflare ervoor zetten als CDN-laag (gratis tier)

### 7. Domein peoplepower.radio koppelen

Bij Siteground (waar het domein staat):
1. Verwijder de A-record die nu naar de WordPress-server wijst
2. Voeg een CNAME toe: `peoplepower.radio` → `peoplepower-radio.s3-website.nl-ams.scw.cloud`
3. Of via Edge Services een fixed IP

**LET OP**: dit haalt de huidige WordPress-site offline. Test eerst op een staging-subdomein zoals `nieuw.peoplepower.radio`.

## Lokaal testen

```bash
# Frontend lokaal serveren
cd public
python3 -m http.server 8000
# Open http://localhost:8000

# Function lokaal testen
cd ../functions/episodes
python3 -c "from handler import handle; import json; print(json.dumps(handle({}, {}), indent=2))"
```

## Kosten-inschatting

Scaleway Serverless Functions: gratis tot 1 miljoen requests/maand. Met 10-minuten cache wordt de Springcast feed maximaal ~4.300 keer per maand opgehaald, en eindgebruikers raken vooral de cache. Praktisch gratis.

Object Storage: ~€0.01/GB/maand. De site is <2 MB. Praktisch gratis.

Egress (data uit): eerste 75 GB/maand gratis op Scaleway. Voor een podcast-site met visuele content ruim voldoende.

**Verwachte kosten: €0 tot €1 per maand.**

## Volgende stappen

- Aflevering-detailpagina's per RSS-item
- Themafilter (vereist mapping in een aparte JSON of via WordPress API)
- Spotify-embed
- Search via Pagefind of MeiliSearch
- Fase 2: ledendirectory met Scaleway Managed PostgreSQL + auth
