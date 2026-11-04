#!/usr/bin/env bash
# Builds the signed ARGOS APK and versions it in mobile/releases/.
#   bash mobile/scripts/gerar_apk.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export ANDROID_HOME="${ANDROID_HOME:-$HOME/android-sdk}"
VERSAO=$(node -p "require('./package.json').version")

# Signing key: restore from a base64 secret when running in a fresh environment
if [[ -n "${ARGOS_KEYSTORE_B64:-}" && ! -f assinatura/argos-sideload.jks ]]; then
  (umask 077; echo "$ARGOS_KEYSTORE_B64" | base64 -d > assinatura/argos-sideload.jks)
fi
if [[ ! -f assinatura/argos-sideload.jks && -z "${ARGOS_KEYSTORE:-}" ]]; then
  echo "Chave de assinatura ausente: veja mobile/assinatura/LEIA-ME.md" >&2; exit 1
fi

# Keep the native version in sync with package.json (versionCode = MAJOR*10000 + MINOR*100 + PATCH)
IFS=. read -r MA MI PA <<<"$VERSAO"
CODIGO=$((MA * 10000 + MI * 100 + PA))
sed -i -E "s/versionCode [0-9]+/versionCode $CODIGO/; s/versionName \"[^\"]+\"/versionName \"$VERSAO\"/" android/app/build.gradle
sed -i -E "s/const VERSAO = \"[^\"]+\"/const VERSAO = \"$VERSAO\"/" www/js/app.js

npx cap sync android
(cd android && ./gradlew --no-daemon -q assembleRelease)

mkdir -p releases
DESTINO="releases/argos-$VERSAO.apk"
cp android/app/build/outputs/apk/release/app-release.apk "$DESTINO"
cp "$DESTINO" releases/argos-ultima.apk
(cd releases && sha256sum "argos-$VERSAO.apk" > "argos-$VERSAO.apk.sha256")
echo "APK: mobile/$DESTINO ($(du -h "$DESTINO" | cut -f1)) · versionCode $CODIGO"
