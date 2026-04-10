#!/bin/bash
# deploy.sh — Synchroniseer de dist/-map naar de Scaleway Object Storage bucket.
#
# ==============================================================================
# EENMALIGE SETUP
# ==============================================================================
# 1. Installeer de AWS CLI (compatibel met Scaleway's S3 API):
#      brew install awscli
#
# 2. Configureer een apart profiel voor Scaleway:
#      aws configure --profile scaleway
#    En vul in:
#      AWS Access Key ID     : <jouw Scaleway Access Key>
#      AWS Secret Access Key : <jouw Scaleway Secret Key>
#      Default region name   : nl-ams
#      Default output format : json
#
# 3. (Optioneel) Zet het profiel als default voor deze sessie:
#      export AWS_PROFILE=scaleway
#
# ==============================================================================
# GEBRUIK
# ==============================================================================
#   ./deploy.sh            # Deploy de inhoud van ./dist/ naar de bucket
#
# Vereist dat build.py eerst is gedraaid (python3 build.py).
#
# ==============================================================================
# LET OP — DESTRUCTIEVE FLAG
# ==============================================================================
# De --delete flag VERWIJDERT alle bestanden in de bucket die NIET in ./dist/
# staan. Omdat build.py alleen afleveringen.html, afleveringen/*, sitemap.xml,
# robots.txt en schema-index.json genereert, worden bestanden zoals
# index.html, over.html, style.css, photos/*, etc. verwijderd als je --delete
# gebruikt zonder die eerst naar dist/ te kopieren.
#
# Deze versie draait daarom ZONDER --delete. Verwijder de # op de regel met
# --delete alleen als je zeker weet dat je bucket-inhoud overeenkomt met ./dist/.
# ==============================================================================

set -euo pipefail

BUCKET="peoplepower-radio"
ENDPOINT="https://s3.nl-ams.scw.cloud"
PROFILE="${AWS_PROFILE:-scaleway}"
DIST_DIR="./dist"

if [ ! -d "$DIST_DIR" ]; then
  echo "Fout: ${DIST_DIR} bestaat niet. Draai eerst: python3 build.py" >&2
  exit 1
fi

echo "-> Deploy ${DIST_DIR}/ naar s3://${BUCKET} via ${ENDPOINT}"
echo "   Profile: ${PROFILE}"

aws s3 sync "${DIST_DIR}" "s3://${BUCKET}" \
  --endpoint-url "${ENDPOINT}" \
  --profile "${PROFILE}" \
  --acl public-read \
  --cache-control "max-age=3600" \
  --exclude "*.py" \
  --exclude "*.sh" \
  --exclude "*.pyc" \
  --exclude "__pycache__/*"
  # --delete           # ALLEEN activeren als je bucket 1:1 wilt spiegelen met dist/

echo
echo "Klaar. Controleer de site op:"
echo "  https://peoplepower-radio.s3-website.nl-ams.scw.cloud/"
