
from abc import ABC, abstractmethod
from collections import Counter
from datetime import datetime, time
from decimal import Decimal
from itertools import chain

from enums import (
    StatusReserva,
    StatusCompraCredito,
    StatusPagamento,
    StatusRepasse,
    StatusSolicitacao,
    StatusDenuncia
)


class Usuario(ABC):
    def __init__(self, id, nome, email):
        self._id = id
        self._nome = nome
        self._email = email
        self._banido = False
        self._motivo_banimento = None

    @property
    def id(self):
        return self._id

    @property
    def nome(self):
        return self._nome

    @property
    def email(self):
        return self._email

    @property
    def banido(self):
        return self._banido

    @abstractmethod
    def tem_permissao(self, acao):
        pass

    def consultar_dados(self):
        return {
            "id": self.id,
            "nome": self.nome,
            "email": self.email,
            "banido": self.banido,
            "motivo_banimento": self._motivo_banimento
        }

    def banir(self, motivo):
        if not motivo or not motivo.strip():
            raise ValueError("Informe o motivo do banimento.")
        self._banido = True
        self._motivo_banimento = motivo.strip()


class Administrador(Usuario):
    def tem_permissao(self, acao):
        return True


class Supervisor(Usuario):
    def tem_permissao(self, acao):
        return acao in {
            "consultar_dados", "registrar_denuncia", "gerenciar_quadras", "cadastrar_quadra",
            "atualizar_quadra", "excluir_quadra", "definir_preco", "disponibilizar_quadra",
            "definir_disponibilidade", "consultar_disponibilidade", "consultar_reservas",
            "consultar_partidas", "cancelar_reserva", "interditar_quadra", "concluir_reserva",
            "cadastrar_equipamento", "fornecer_equipamento",
        }


class Atleta(Usuario):
    def __init__(self, id, nome, email):
        super().__init__(id, nome, email)
        self._carteira = Carteira()

    @property
    def carteira(self):
        return self._carteira

    def tem_permissao(self, acao):
        return acao in {
            "consultar_dados", "registrar_denuncia", "consultar_disponibilidade",
            "criar_reserva", "cancelar_reserva", "reagendar_reserva", "definir_privacidade",
            "calcular_rateio", "pagar_reserva", "comprar_creditos", "participar_partida",
            "autorizar_participante", "consultar_partidas", "consultar_partidas_publicas",
            "solicitar_equipamento",
        }


def _horario_no_fuso(horario, fuso):
    if horario.tzinfo == fuso:
        return horario
    convertido = horario.astimezone(fuso)
    return convertido if fuso is not None else convertido.replace(tzinfo=None)


def _intersecao(inicio, fim, de, ate):
    inicio_comum = max(inicio, _horario_no_fuso(de, inicio.tzinfo))
    fim_comum = min(fim, _horario_no_fuso(ate, inicio.tzinfo))
    if inicio_comum < fim_comum:
        return inicio_comum, fim_comum
    return None


class Bloqueio:
    def __init__(self, inicio, fim, motivo):
        self.inicio = inicio
        self.fim = fim
        self.motivo = motivo
        self.liberado_em = None

    @property
    def fim_efetivo(self):
        liberado_em = getattr(self, "liberado_em", None)
        return min(self.fim, liberado_em) if liberado_em is not None else self.fim

    def sobrepoe(self, inicio, fim):
        return _intersecao(inicio, fim, self.inicio, self.fim_efetivo) is not None


class FaixaFuncionamento:
    def __init__(self, dia_semana, abertura, fechamento):
        if abertura >= fechamento:
            raise ValueError("Horário de abertura inválido.")

        self.dia_semana = dia_semana
        self.abertura = abertura
        self.fechamento = fechamento

    def contem(self, inicio, fim):
        return (
            inicio.date() == fim.date()
            and inicio.weekday() == self.dia_semana
            and inicio.time() >= self.abertura
            and fim.time() <= self.fechamento
        )


class Agenda:
    def __init__(self):
        self.faixas = []
        self.bloqueios = []

    def adicionar_faixa(self, faixa):
        self.faixas.append(faixa)

    def remover_faixa(self, faixa):
        self.faixas.remove(faixa)

    def adicionar_bloqueio(self, bloqueio):
        self.bloqueios.append(bloqueio)

    def remover_bloqueio(self, bloqueio):
        self.bloqueios.remove(bloqueio)

    def horarios_livres(self, inicio, fim, ocupados=()):
        if inicio >= fim or inicio.date() != fim.date():
            return []

        funcionamento = []
        do_dia = (f for f in self.faixas if f.dia_semana == inicio.weekday())
        for faixa in sorted(do_dia, key=lambda f: f.abertura):
            abre = max(inicio, datetime.combine(inicio.date(), faixa.abertura, inicio.tzinfo))
            fecha = min(fim, datetime.combine(inicio.date(), faixa.fechamento, inicio.tzinfo))
            if abre >= fecha:
                continue
            if funcionamento and abre <= funcionamento[-1][1]:
                anterior, fechamento = funcionamento[-1]
                funcionamento[-1] = (anterior, max(fechamento, fecha))
            else:
                funcionamento.append((abre, fecha))

        if not funcionamento:
            return []
        impedimentos = []
        bloqueios = ((b.inicio, b.fim_efetivo) for b in self.bloqueios)
        for de, ate in chain(ocupados, bloqueios):
            trecho = _intersecao(inicio, fim, de, ate)
            if trecho:
                impedimentos.append(trecho)
        impedimentos.sort()
        livres = []
        for cursor, fechamento in funcionamento:
            for de, ate in impedimentos:
                if de >= fechamento or cursor >= fechamento:
                    break
                if ate <= cursor:
                    continue
                if cursor < de:
                    livres.append((cursor, de))
                cursor = ate
            if cursor < fechamento:
                livres.append((cursor, fechamento))
        return livres

    def permite_periodo(self, inicio, fim):
        return (inicio, fim) in self.horarios_livres(inicio, fim)


class Equipamento:
    def __init__(self, id, nome, quantidade_total):
        self.id = id
        self.nome = nome
        self.quantidade_total = quantidade_total
        self.quantidade_emprestada = 0

    def atualizar_quantidade(self, quantidade):
        if self.quantidade_total + quantidade < 0:
            raise ValueError("Quantidade insuficiente.")
        self.quantidade_total += quantidade


class SolicitacaoEquipamento:
    def __init__(self, id, quantidade, equipamento):
        self.id = id
        self.quantidade = quantidade
        self.equipamento = equipamento
        self.status = StatusSolicitacao.SOLICITADA

    def fornecer(self):
        if self.status != StatusSolicitacao.SOLICITADA:
            raise ValueError("Solicitação já processada.")
        if self.equipamento.quantidade_total < self.quantidade:
            raise ValueError("Equipamento indisponível.")

        self.equipamento.atualizar_quantidade(-self.quantidade)
        self.equipamento.quantidade_emprestada += self.quantidade
        self.status = StatusSolicitacao.FORNECIDA

    def devolver(self):
        if self.status != StatusSolicitacao.FORNECIDA:
            raise ValueError("Somente equipamento fornecido pode ser devolvido.")
        self.equipamento.atualizar_quantidade(self.quantidade)
        self.equipamento.quantidade_emprestada -= self.quantidade
        self.status = StatusSolicitacao.DEVOLVIDA

    def cancelar(self):
        if self.status == StatusSolicitacao.FORNECIDA:
            self.devolver()
        self.status = StatusSolicitacao.CANCELADA


class Quadra:
    def __init__(self, id, nome, modalidade, capacidade,
                 valor_hora, supervisor):
        self.id = id
        self.atualizar(nome, modalidade, capacidade)
        self.ativa = True
        self.definir_preco(valor_hora)
        self.supervisor = supervisor
        self.agenda = Agenda()
        self.equipamentos = []
        self.estoque_equipamentos = {}

    def atualizar(self, nome, modalidade, capacidade):
        if type(capacidade) is not int or capacidade < 1:
            raise ValueError("A capacidade deve ser um inteiro positivo.")
        self.nome = nome
        self.modalidade = modalidade
        self.capacidade = capacidade

    def definir_preco(self, valor):
        valor = Decimal(str(valor))
        if not valor.is_finite() or valor < 0:
            raise ValueError("Informe um preço válido.")
        self.valor_hora = valor

    def disponibilizar(self):
        self.ativa = True
        # Revisão (João) — reabrir a quadra hoje também retira a interdição marcada para amanhã?
        for bloqueio in self.agenda.bloqueios:
            agora = datetime.now(bloqueio.inicio.tzinfo)
            if bloqueio.fim_efetivo > agora:
                bloqueio.liberado_em = agora

    def desativar(self):
        self.ativa = False

    def calcular_valor(self, inicio, fim):
        horas = Decimal(str((fim - inicio).total_seconds())) / Decimal("3600")
        return (self.valor_hora * horas).quantize(Decimal("0.01"))


class Partida:
    def __init__(self, publica, limite_participantes):
        self.publica = publica
        self.limite_participantes = limite_participantes
        self.participantes = []
        self.autorizados = []
        self.participantes_fechados = False

    def definir_privacidade(self, publica):
        self.publica = publica

    def autorizar_participante(self, atleta):
        if atleta not in self.autorizados:
            self.autorizados.append(atleta)

    def adicionar_participante(self, atleta):
        if self.participantes_fechados:
            raise ValueError("Lista de participantes fechada.")

        if any(inscrito.id == atleta.id for inscrito in self.participantes):
            raise ValueError("Atleta já está na partida.")

        if len(self.participantes) >= self.limite_participantes:
            raise ValueError("Partida lotada.")

        if not self.publica and atleta not in self.autorizados:
            raise PermissionError("Atleta não autorizado.")

        self.participantes.append(atleta)

    def remover_participante(self, atleta):
        if self.participantes_fechados:
            raise ValueError("Lista de participantes fechada.")
        if atleta in self.participantes:
            self.participantes.remove(atleta)

    def fechar_participantes(self):
        self.participantes_fechados = True


class Reserva:
    def __init__(self, id, inicio, fim, responsavel, quadra, modo=None):
        if modo not in (None, "integral", "rateado"):
            raise ValueError("Modo de pagamento inválido.")
        if inicio >= fim:
            raise ValueError("O início deve ser anterior ao fim.")
        self.id = id
        self.inicio = inicio
        self.fim = fim
        self.valor_total = Decimal("0")
        self.status = StatusReserva.ATIVA
        self.responsavel = responsavel
        self.quadra = quadra
        # Revisão (João) — a partida começa privada e já inclui quem fez a reserva?
        self.partida = Partida(False, quadra.capacidade)
        self.partida.autorizar_participante(responsavel)
        self.partida.adicionar_participante(responsavel)
        self.modo_contratado = modo
        self.modo_pagamento = None
        self.solicitacoes = []

    @property
    def metodo_pagamento(self):
        return getattr(self, "modo_contratado", None) or self.modo_pagamento

    def sobrepoe(self, inicio, fim):
        return (
            self.status == StatusReserva.ATIVA
            and _intersecao(inicio, fim, self.inicio, self.fim) is not None
        )

    def quantidades_solicitadas(self):
        quantidades = Counter()
        for pedido in self.solicitacoes:
            if pedido.status in (StatusSolicitacao.SOLICITADA, StatusSolicitacao.FORNECIDA):
                quantidades[pedido.equipamento] += pedido.quantidade
        return quantidades

    def calcular_rateio(self):
        return self._ratear_valor(self.valor_total)

    def _ratear_valor(self, valor):
        participantes = self.partida.participantes
        if not participantes:
            return {}
        centavos = int(valor * 100)
        base, sobra = divmod(centavos, len(participantes))
        # Revisão (João) — dois atletas com o mesmo nome continuam com parcelas separadas?
        return {
            atleta.id: Decimal(base + (indice < sobra)).scaleb(-2)
            for indice, atleta in enumerate(participantes)
        }

    def reagendar(self, inicio, fim, valor=None):
        if inicio >= fim:
            raise ValueError("O início deve ser anterior ao fim.")
        self.inicio = inicio
        self.fim = fim
        if valor is not None:
            self.valor_total = valor

    def cancelar(self):
        if self.status != StatusReserva.ATIVA:
            raise ValueError("Reserva não está ativa.")
        self.status = StatusReserva.CANCELADA

    def concluir(self):
        if self.status != StatusReserva.ATIVA:
            raise ValueError("Reserva não está ativa.")
        for pedido in self.solicitacoes:
            if pedido.status == StatusSolicitacao.FORNECIDA:
                pedido.devolver()
            elif pedido.status == StatusSolicitacao.SOLICITADA:
                pedido.cancelar()
        self.partida.fechar_participantes()
        self.status = StatusReserva.CONCLUIDA


class Carteira:
    def __init__(self):
        self.saldo = Decimal("0")

    def creditar(self, valor):
        valor = Decimal(str(valor))
        if valor <= 0:
            raise ValueError("Valor inválido.")
        self.saldo += valor

    def debitar(self, valor):
        valor = Decimal(str(valor))
        if valor <= 0 or valor > self.saldo:
            raise ValueError("Saldo insuficiente ou valor inválido.")
        self.saldo -= valor


class CompraCredito:
    def __init__(self, id, valor, carteira):
        self.id = id
        self.valor = Decimal(str(valor))
        if not self.valor.is_finite() or self.valor <= 0:
            raise ValueError("O valor da compra deve ser positivo.")
        self.status = StatusCompraCredito.PENDENTE
        self.criada_em = datetime.now()
        self.confirmada_em = None
        self.carteira = carteira

    def confirmar(self):
        if self.status != StatusCompraCredito.PENDENTE:
            raise ValueError("Compra já processada.")
        self.carteira.creditar(self.valor)
        self.status = StatusCompraCredito.CONFIRMADA
        self.confirmada_em = datetime.now()

    def cancelar(self):
        if self.status != StatusCompraCredito.PENDENTE:
            raise ValueError("Compra já processada.")
        self.status = StatusCompraCredito.CANCELADA


class Pagamento:
    def __init__(self, id, valor, pagador, reserva):
        self.id = id
        self.valor = Decimal(str(valor))
        self.status = StatusPagamento.PENDENTE
        self.pago_em = None
        self.pagador = pagador
        self.reserva = reserva

    def pagar(self):
        if self.status != StatusPagamento.PENDENTE:
            raise ValueError("Pagamento já processado.")
        self.pagador.carteira.debitar(self.valor)
        self.status = StatusPagamento.PAGO
        self.pago_em = datetime.now()

    def estornar(self):
        if self.status != StatusPagamento.PAGO:
            raise ValueError("Pagamento não pode ser estornado.")
        if self.valor:
            self.pagador.carteira.creditar(self.valor)
        self.status = StatusPagamento.ESTORNADO


class Repasse:
    def __init__(self, id, valor, supervisor, reservas):
        self.id = id
        self.valor = Decimal(str(valor))
        self.status = StatusRepasse.PENDENTE
        self.efetuado_em = None
        self.supervisor = supervisor
        self.reservas = reservas

    def calcular_total(self):
        return sum(
            (reserva.valor_total for reserva in self.reservas),
            Decimal("0")
        )

    def efetuar(self):
        if self.status != StatusRepasse.PENDENTE:
            raise ValueError("Repasse já efetuado.")
        self.status = StatusRepasse.EFETUADO
        self.efetuado_em = datetime.now()


class Denuncia:
    def __init__(self, id, motivo, autor, denunciado):
        self.id = id
        self.motivo = motivo
        self.data = datetime.now()
        self.status = StatusDenuncia.ABERTA
        self.autor = autor
        self.denunciado = denunciado

    def encerrar(self):
        if self.status == StatusDenuncia.ENCERRADA:
            raise ValueError("Denúncia já encerrada.")
        self.status = StatusDenuncia.ENCERRADA


class Avaliacao:
    def __init__(self, nota, comentario, supervisor, atleta, reserva):
        if not 1 <= nota <= 5:
            raise ValueError("A nota deve estar entre 1 e 5.")
        self.nota = nota
        self.comentario = comentario
        self.supervisor = supervisor
        self.atleta = atleta
        self.reserva = reserva
        self.data = datetime.now()
