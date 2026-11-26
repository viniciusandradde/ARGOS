// Configuração do servidor (opcional). No APK fica vazia: a pessoa informa o endereço do FiscalFlow.
// No container web (mobile/web/), o entrypoint reescreve este arquivo com o endereço do FiscalFlow, o repasse
// da SEFAZ-MS e o link do APK. Nunca coloque segredo aqui: o arquivo é público.
window.ARGOS_CONFIG = window.ARGOS_CONFIG || {};
