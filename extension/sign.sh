#!/bin/sh
# Has Mozilla sign the Firefox/Zen build ("unlisted": signed for self-distribution, never listed on
# addons.mozilla.org), keeps it in signed/ (committed), and puts it where Daf's Preferences
# download it from. build.sh starts dist/ over, so run this after any build.
#
#   extension/sign.sh
#
# Needs AMO_JWT_ISSUER and AMO_JWT_SECRET in an .env file (made at
# https://addons.mozilla.org/developers/addon/api/key/). Mozilla signs each version once, so
# bump "version" in manifest.json before signing a change. Node needn't be on the server: web-ext runs
# in the node:22 image. The key is passed in the environment, never on a command line.
set -eu
cd "$(dirname "$0")"
STATE=${DAF_STATE:-/srv/docker/daf}
# The .env with the AMO keys: $AMO_ENV_FILE, or AMO_ENV_FILE= in the state folder's daf.env, else daf.env itself.
ENV_FILE=${AMO_ENV_FILE:-$(sed -n "s/^AMO_ENV_FILE=//p" "$STATE/daf.env" 2>/dev/null | tail -1)}
ENV_FILE=${ENV_FILE:-$STATE/daf.env}
get(){ sed -n "s/^$1=//p" "$ENV_FILE" | tail -1 | sed "s/^['\"]//; s/['\"]$//"; }
AMO_JWT_ISSUER=$(get AMO_JWT_ISSUER); AMO_JWT_SECRET=$(get AMO_JWT_SECRET)
if [ -z "$AMO_JWT_ISSUER" ] || [ -z "$AMO_JWT_SECRET" ]; then
  echo "No AMO_JWT_ISSUER / AMO_JWT_SECRET in $ENV_FILE. Make them at https://addons.mozilla.org/developers/addon/api/key/" >&2
  exit 1
fi
./build.sh
VERSION=$(python3 -c 'import json; print(json.load(open("manifest.json"))["version"])')
mkdir -p signed
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e WEB_EXT_API_KEY="$AMO_JWT_ISSUER" -e WEB_EXT_API_SECRET="$AMO_JWT_SECRET" \
  -v "$PWD/dist:/dist" -v "$PWD/signed:/signed" -w /dist node:22 \
  npx --yes web-ext@8 sign --channel=unlisted --source-dir=/dist/firefox --artifacts-dir=/signed --approval-timeout=900000
SIGNED=$(ls -t signed/*.xpi 2>/dev/null | head -1)
if [ -z "$SIGNED" ]; then echo "Mozilla didn't send a signed file back (see above)." >&2; exit 1; fi
cp "$SIGNED" dist/daf-extension.xpi
echo "Signed $VERSION: $SIGNED, now served as Preferences → Account → Browser extension → Firefox or Zen."
