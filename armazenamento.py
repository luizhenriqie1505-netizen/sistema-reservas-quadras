"""Armazenamento local da sessão e autenticação dos usuários do terminal."""
import hashlib
import hmac
import json
import os
import sqlite3
from datetime import datetime, time
from decimal import Decimal
from enum import Enum
from pathlib import Path

import enums
import modelos
from servicos import SistemaReservas


def definir_senha(usuario, senha):
    if not senha.strip():
        raise ValueError("A senha não pode ser vazia.")
    sal = os.urandom(16)
    usuario._sal = sal.hex()
    usuario._verificador = derivar_senha(senha, sal)


def derivar_senha(senha, sal):
    return hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, 600_000).hex()


def autenticar(sistema, email, senha):
    conta = next((u for u in sistema.usuarios if u.email.casefold() == email.casefold()), None)
    if conta is None or not hmac.compare_digest(
        derivar_senha(senha, bytes.fromhex(conta._sal)), conta._verificador
    ) or conta.banido:
        raise PermissionError("E-mail ou senha inválidos, ou conta indisponível.")
    return conta


# A reserva e o pagamento precisam apontar para a mesma carteira após reabrir.
# Os índices abaixo preservam as referências compartilhadas entre os objetos.
CLASSES = {classe.__name__: classe for classe in (
    SistemaReservas, modelos.Administrador, modelos.Supervisor, modelos.Atleta,
    modelos.Carteira, modelos.Quadra, modelos.Agenda, modelos.FaixaFuncionamento,
    modelos.Bloqueio, modelos.Reserva, modelos.Partida, modelos.Pagamento,
    modelos.CompraCredito, modelos.Equipamento, modelos.SolicitacaoEquipamento,
    modelos.Repasse, modelos.Denuncia, modelos.Avaliacao,
)}
ESTADOS = {classe.__name__: classe for classe in (
    enums.StatusReserva, enums.StatusPagamento, enums.StatusCompraCredito,
    enums.StatusRepasse, enums.StatusSolicitacao, enums.StatusDenuncia,
)}


def serializar(sistema):
    registros = []
    indices = {}

    def gravar(valor):
        if isinstance(valor, list):
            return [gravar(item) for item in valor]
        if isinstance(valor, tuple):
            return {"tupla": [gravar(item) for item in valor]}
        if isinstance(valor, dict):
            return {"pares": [[gravar(k), gravar(v)] for k, v in valor.items()]}
        if isinstance(valor, Enum):
            return {"estado": [type(valor).__name__, valor.name]}
        if isinstance(valor, Decimal):
            return {"decimal": str(valor)}
        if isinstance(valor, (datetime, time)):
            return {type(valor).__name__: valor.isoformat()}
        if type(valor).__name__ in CLASSES:
            chave = id(valor)
            if chave not in indices:
                indices[chave] = len(registros)
                registro = {"classe": type(valor).__name__}
                registros.append(registro)
                registro["campos"] = {k: gravar(v) for k, v in vars(valor).items()}
            return {"ref": indices[chave]}
        return valor

    gravar(sistema)
    return json.dumps(registros, ensure_ascii=False)


def restaurar(conteudo):
    registros = json.loads(conteudo)
    objetos = [object.__new__(CLASSES[r["classe"]]) for r in registros]

    def ler(valor):
        if isinstance(valor, list):
            return [ler(item) for item in valor]
        if not isinstance(valor, dict):
            return valor
        tipo, dado = next(iter(valor.items()))
        if tipo == "ref":
            return objetos[dado]
        if tipo == "pares":
            return {ler(k): ler(v) for k, v in dado}
        if tipo == "tupla":
            return tuple(ler(v) for v in dado)
        if tipo == "estado":
            return ESTADOS[dado[0]][dado[1]]
        return {"datetime": datetime.fromisoformat, "time": time.fromisoformat,
                "decimal": Decimal}[tipo](dado)

    for objeto, registro in zip(objetos, registros):
        vars(objeto).update({k: ler(v) for k, v in registro["campos"].items()})
    return objetos[0]


def abrir_banco(caminho=None):
    if caminho is None:
        pasta = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "SistemaReservasQuadras"
        pasta.mkdir(parents=True, exist_ok=True)
        caminho = pasta / "reservas.sqlite3"
    banco = sqlite3.connect(caminho)
    with banco:
        banco.execute("CREATE TABLE IF NOT EXISTS sistema "
                      "(id INTEGER PRIMARY KEY, versao INTEGER, dados TEXT NOT NULL)")
        banco.execute("INSERT OR IGNORE INTO sistema VALUES (1, 0, ?)",
                      (serializar(SistemaReservas()),))
    return banco


def carregar(banco):
    versao, dados = banco.execute("SELECT versao, dados FROM sistema WHERE id=1").fetchone()
    return versao, restaurar(dados)


def salvar(banco, versao, sistema):
    with banco:
        resultado = banco.execute("UPDATE sistema SET versao=versao+1, dados=? "
                                  "WHERE id=1 AND versao=?", (serializar(sistema), versao))
        if resultado.rowcount != 1:
            raise ValueError("Outra sessão alterou os dados. Repita a operação.")
