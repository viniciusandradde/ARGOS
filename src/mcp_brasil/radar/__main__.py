"""CLI de administração do Radar Brasil.

Uso:
    python -m mcp_brasil.radar criar-admin --email voce@exemplo.com --senha '...'
    python -m mcp_brasil.radar conceder --email cliente@exemplo.com --plano profissional --dias 30
    python -m mcp_brasil.radar usuarios
    python -m mcp_brasil.radar criar-chave --email voce@exemplo.com --nome "Claude Desktop"
    python -m mcp_brasil.radar redefinir-senha --email cliente@exemplo.com
    python -m mcp_brasil.radar coletar [--loop] [--etapas noticias,enso]
    python -m mcp_brasil.radar whatsapp status
    python -m mcp_brasil.radar whatsapp conectar --numero 5567999999999
    python -m mcp_brasil.radar whatsapp teste --numero 5567999999999
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import sys

from . import get_servico, seguranca
from .servico import ErroRadar


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mcp_brasil.radar")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_admin = sub.add_parser("criar-admin", help="Cria um usuário administrador")
    p_admin.add_argument("--email", required=True)
    p_admin.add_argument("--senha", help="Se omitida, será pedida no terminal")
    p_admin.add_argument("--nome", default="")

    p_conc = sub.add_parser("conceder", help="Concede acesso manual a um usuário")
    p_conc.add_argument("--email", required=True)
    p_conc.add_argument("--plano", required=True)
    p_conc.add_argument("--dias", type=int, default=30)

    p_chave = sub.add_parser("criar-chave", help="Gera uma chave de API para um usuário")
    p_chave.add_argument("--email", required=True)
    p_chave.add_argument("--nome", default="cli")

    p_senha = sub.add_parser("redefinir-senha", help="Define uma nova senha para um usuário")
    p_senha.add_argument("--email", required=True)
    p_senha.add_argument("--senha", help="Se omitida, será pedida no terminal")

    sub.add_parser("usuarios", help="Lista usuários e situação do acesso")

    p_coletar = sub.add_parser("coletar", help="Coleta indicadores para o painel e o Metabase")
    p_coletar.add_argument(
        "--loop", action="store_true", help="Repete a cada RADAR_COLETA_MINUTOS"
    )
    p_coletar.add_argument("--etapas", default="", help="Ex: noticias,enso (padrão: todas)")

    p_wa = sub.add_parser("whatsapp", help="Evolution API: status, pareamento e teste")
    p_wa.add_argument("acao", choices=["status", "conectar", "teste"])
    p_wa.add_argument("--numero", default="", help="Número do chip (conectar) ou destino (teste)")

    args = parser.parse_args(argv)
    if args.comando == "whatsapp":
        return _whatsapp(args.acao, args.numero)
    if args.comando == "coletar":
        return _coletar(args.loop, [e for e in args.etapas.split(",") if e])
    servico = get_servico()

    try:
        if args.comando == "criar-admin":
            senha = args.senha or getpass.getpass("Senha: ")
            usuario = servico.cadastrar(args.email, senha, args.nome, papel="admin")
            print(f"Admin criado: {usuario.email} (id {usuario.id})")
        elif args.comando in ("conceder", "criar-chave", "redefinir-senha"):
            usuario_alvo = servico.store.usuario_por_email(args.email)
            if usuario_alvo is None:
                print(f"Usuário {args.email} não encontrado.", file=sys.stderr)
                return 1
            if args.comando == "conceder":
                fim = servico.conceder(usuario_alvo.id, args.plano, args.dias)
                print(f"Acesso de {usuario_alvo.email} válido até {fim:%d/%m/%Y %H:%M} UTC")
            elif args.comando == "redefinir-senha":
                senha = args.senha or getpass.getpass("Nova senha: ")
                if len(senha) < 8:
                    raise ErroRadar("A senha precisa ter pelo menos 8 caracteres.")
                servico.store.atualizar_usuario(
                    usuario_alvo.id, senha_hash=seguranca.hash_senha(senha)
                )
                print(f"Senha de {usuario_alvo.email} redefinida.")
            else:
                chave = servico.criar_chave(usuario_alvo, args.nome)
                print(f"Chave (guarde agora, não será exibida novamente):\n{chave['chave']}")
        else:
            for u in servico.store.listar_usuarios():
                a = servico.store.assinatura(u.id)
                situacao = "ATIVO" if servico.acesso_ativo(u, a) else "sem acesso"
                plano = f"{a.plano} até {a.periodo_fim:%d/%m/%Y}" if a and a.periodo_fim else "-"
                print(f"{u.id:>4}  {u.email:<35} {u.papel:<8} {situacao:<11} {plano}")
    except ErroRadar as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    return 0


def _whatsapp(acao: str, numero: str) -> int:
    from . import get_alertas
    from .notificadores import EvolutionClient, NotificacaoError, normalizar_whatsapp

    cliente = get_alertas().whatsapp
    if not isinstance(cliente, EvolutionClient) or not cliente.configurado:
        print(
            "Configure EVOLUTION_API_URL, EVOLUTION_API_KEY e EVOLUTION_INSTANCIA.",
            file=sys.stderr,
        )
        return 1
    alvo = normalizar_whatsapp(numero) if numero else None
    try:
        if acao == "status":
            print(f"Estado da instância: {asyncio.run(cliente.estado())}  (open = conectado)")
        elif acao == "conectar":
            dados = asyncio.run(cliente.conectar(alvo))
            if dados.get("pairingCode"):
                print(f"Código de pareamento: {dados['pairingCode']}")
                print("No celular do chip: WhatsApp → Aparelhos conectados → Conectar aparelho →")
                print("'Conectar com número de telefone' e digite o código acima.")
            else:
                print("Sem código de pareamento. Use --numero ou leia o QR no Evolution Manager.")
        else:
            if alvo is None:
                print("Informe --numero para o teste.", file=sys.stderr)
                return 1
            asyncio.run(cliente.enviar_alerta(alvo, "Teste ARGOS", "Envio pela Evolution API OK."))
            print(f"Mensagem enviada para {alvo}.")
    except NotificacaoError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    return 0


def _coletar(loop: bool, etapas: list[str]) -> int:
    from mcp_brasil import settings

    from . import config_coleta_from_settings, get_alertas, get_indicadores
    from .coletor import ETAPAS, coletar_tudo, loop_coleta

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    invalidas = [e for e in etapas if e not in ETAPAS]
    if invalidas:
        print(f"Etapas inválidas: {invalidas}. Opções: {', '.join(ETAPAS)}", file=sys.stderr)
        return 1
    ind, cfg = get_indicadores(), config_coleta_from_settings()
    alertas = get_alertas()
    depois = alertas.despachar if alertas.configurado else None
    if loop:
        asyncio.run(loop_coleta(ind, cfg, settings.RADAR_COLETA_MINUTOS, depois))
        return 0
    for etapa, resultado in asyncio.run(coletar_tudo(ind, cfg, etapas or None)).items():
        print(f"{etapa:<14} {resultado}")
    if depois is not None:
        print(f"{'alertas':<14} {asyncio.run(alertas.despachar())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
