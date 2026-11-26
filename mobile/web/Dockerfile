# ARGOS web: o app (mobile/www) servido por nginx, com repasse restrito à consulta pública da NFC-e da SEFAZ-MS e
# download do APK. Contexto de build = raiz do repositório, de preferência a partir de um commit exato:
#   git archive --format=tar <commit> mobile | docker build -t argos-web:<commit> -f mobile/web/Dockerfile -
# Nada específico de servidor fica aqui: o endereço do FiscalFlow e o link do APK chegam por variável de ambiente.
FROM mirror.gcr.io/library/nginx:1.30.6-alpine
COPY mobile/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY mobile/web/40-argos-config.sh /docker-entrypoint.d/40-argos-config.sh
COPY mobile/www /usr/share/nginx/html
COPY mobile/releases/*.apk mobile/releases/*.sha256 /usr/share/nginx/downloads/
RUN chmod 755 /docker-entrypoint.d/40-argos-config.sh
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
