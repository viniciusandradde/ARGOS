#!/usr/bin/env bash
# Gera uma VARIANTE do APK (pacote e nome próprios), instalável ao lado do ARGOS oficial, com config.js embutido.
# Nada específico de servidor fica aqui: tudo chega por variável de ambiente.
#   ARGOS_APP_ID      pacote, ex.: br.com.vsa.argos.familia          (obrigatório)
#   ARGOS_APP_NOME    nome no Android, ex.: "ARGOS Família"           (obrigatório)
#   ARGOS_CONFIG_JS   arquivo config.js a embutir (endereço do FiscalFlow, link do APK) (opcional)
#   ARGOS_SAIDA       pasta de saída (obrigatório; fora do Git)
#   ARGOS_KEYSTORE, ARGOS_KEYSTORE_SENHA, ARGOS_KEY_ALIAS, ARGOS_KEY_SENHA   assinatura (obrigatórios)
set -euo pipefail
cd "$(dirname "$0")/.."
: "${ARGOS_APP_ID:?}" "${ARGOS_APP_NOME:?}" "${ARGOS_SAIDA:?}" "${ARGOS_KEYSTORE:?}" "${ARGOS_KEYSTORE_SENHA:?}" "${ARGOS_KEY_SENHA:?}"
[[ "$ARGOS_APP_ID" =~ ^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$ ]] || { echo "ARGOS_APP_ID inválido" >&2; exit 1; }
export ANDROID_HOME="${ANDROID_HOME:-$HOME/android-sdk}"
VERSAO=$(node -p "require('./package.json').version")
STRINGS=android/app/src/main/res/values/strings.xml
# Restaura os arquivos versionados mesmo se o build falhar.
trap 'git checkout -- "$STRINGS" www/js/config.js 2>/dev/null || true' EXIT
NOME_XML=$(printf '%s' "$ARGOS_APP_NOME" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')
sed -i -E "s#<string name=\"app_name\">[^<]*</string>#<string name=\"app_name\">$NOME_XML</string>#; s#<string name=\"title_activity_main\">[^<]*</string>#<string name=\"title_activity_main\">$NOME_XML</string>#" "$STRINGS"
if [[ -n "${ARGOS_CONFIG_JS:-}" ]]; then cp "$ARGOS_CONFIG_JS" www/js/config.js; fi
npx cap sync android >/dev/null
(cd android && ./gradlew --no-daemon -q assembleRelease -PargosAppId="$ARGOS_APP_ID")
BASE=$(echo "$ARGOS_APP_ID" | awk -F. '{print $NF}')
mkdir -p "$ARGOS_SAIDA"
DESTINO="$ARGOS_SAIDA/argos-$BASE-$VERSAO.apk"
cp android/app/build/outputs/apk/release/app-release.apk "$DESTINO"
cp "$DESTINO" "$ARGOS_SAIDA/argos-$BASE-ultima.apk"
(cd "$ARGOS_SAIDA" && sha256sum "argos-$BASE-$VERSAO.apk" > "argos-$BASE-$VERSAO.apk.sha256" && sha256sum "argos-$BASE-ultima.apk" > "argos-$BASE-ultima.apk.sha256")
echo "APK: $DESTINO ($(du -h "$DESTINO" | cut -f1)) · pacote $ARGOS_APP_ID · versão $VERSAO"
