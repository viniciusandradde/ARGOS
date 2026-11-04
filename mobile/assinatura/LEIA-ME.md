# Chave de assinatura do APK

O APK do ARGOS é assinado com a chave `argos-sideload.jks` (alias `argos`, RSA 4096, válida por 10.000 dias).

- Certificado: `CN=ARGOS, O=VSA Solucoes em Tecnologia, L=Dourados, ST=MS, C=BR`
- SHA-256: `30:d4:19:26:b5:59:80:f9:32:49:3e:02:b2:7e:7f:f2:1f:30:01:5f:d9:fa:a9:8f:33:a8:92:61:f9:dd:94:7b`

**A chave e a senha NÃO ficam no Git** (`*.jks` e `*.properties` estão no `.gitignore`).

O Android só instala uma atualização por cima se ela vier assinada com **a mesma chave**. Se a chave
se perder, a próxima versão exige desinstalar o app, o que apaga os dados locais.

## Guardar

1. Mantenha `argos-sideload.jks` e a senha num cofre (gerenciador de senhas) e numa cópia offline.
2. Para builds do Claude em nuvem, cadastre como *secrets* do ambiente:
   - `ARGOS_KEYSTORE_B64`: `base64 -w0 argos-sideload.jks`
   - `ARGOS_KEYSTORE_SENHA` e `ARGOS_KEY_SENHA`

## Usar num build

Ou crie `mobile/assinatura/assinatura.properties`, que fica fora do Git:

```properties
storeFile=../../assinatura/argos-sideload.jks
keyAlias=argos
storePassword=...
keyPassword=...
```

ou exporte as variáveis `ARGOS_KEYSTORE`, `ARGOS_KEYSTORE_SENHA`, `ARGOS_KEY_ALIAS` e `ARGOS_KEY_SENHA`.
Com `ARGOS_KEYSTORE_B64` definido, o `scripts/gerar_apk.sh` restaura o `.jks` sozinho.
