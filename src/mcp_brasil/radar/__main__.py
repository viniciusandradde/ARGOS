"""CLI de administração do Radar Brasil.

Uso:
    python -m mcp_brasil.radar criar-admin --email voce@exemplo.com --senha '...'
    python -m mcp_brasil.radar conceder --email cliente@exemplo.com --plano profissional --dias 30
    python -m mcp_brasil.radar usuarios
    python -m mcp_brasil.radar criar-chave --email voce@exemplo.com --nome "Claude Desktop"
    python -m mcp_brasil.radar redefinir-senha --email cliente@exemplo.com
"""

from __future__ import annotations

import argparse
import getpass
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

    args = parser.parse_args(argv)
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


if __name__ == "__main__":
    sys.exit(main())
