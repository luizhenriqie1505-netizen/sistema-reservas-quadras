
from abc import ABC, abstractmethod
from datetime import datetime, time
from decimal import Decimal

from enums import (
    StatusReserva,
    StatusCompraCredito,
    StatusPagamento,
    StatusRepasse,
    StatusSolicitacao,
    StatusDenuncia
)


# =========================
# USUARIOS - CLASSE ABSTRATA
# =========================

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
            "banido": self.banido
        }

    def banir(self, motivo):
        if not motivo:
            raise ValueError("Informe o motivo do banimento.")
        self._banido = True
        self._motivo_banimento = motivo


class Administrador(Usuario):
    def tem_permissao(self, acao):
        return True


class Supervisor(Usuario):
    def tem_permissao(self, acao):
        return acao in [
            "gerenciar_quadras",
            "consultar_reservas",
            "fornecer_equipamento",
            "efetuar_repasse"
        ]


class Atleta(Usuario):
    def __init__(self, id, nome, email):
        super().__init__(id, nome, email)
        self._carteira = Carteira()

    @property
    def carteira(self):
        return self._carteira

    def tem_permissao(self, acao):
        return acao in [
            "criar_reserva",
            "cancelar_reserva",
            "reagendar_reserva",
            "participar_partida",
            "solicitar_equipamento"
        ]


# =========================
# AGENDA E FUNCIONAMENTO
# =========================

class Bloqueio:
    def __init__(self, inicio, fim, motivo):
        self.inicio = inicio
        self.fim = fim
        self.motivo = motivo

    def sobrepoe(self, inicio, fim):
        return inicio < self.fim and fim > self.inicio


class FaixaFuncionamento:
    def __init__(self, dia_semana, abertura, fechamento):
        if abertura >= fechamento:
            raise ValueError("Horário de abertura inválido.")

        self.dia_semana = dia_semana
        self.abertura = abertura
        self.fechamento = fechamento

    def contem(self, inicio, fim):
        return (
            inicio.weekday() == self.dia_semana
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

    def permite_periodo(self, inicio, fim):
        funcionamento = any(
            faixa.contem(inicio, fim) for faixa in self.faixas
        )

        bloqueado = any(
            bloqueio.sobrepoe(inicio, fim)
            for bloqueio in self.bloqueios
        )

        return funcionamento and not bloqueado


# =========================
# EQUIPAMENTOS
# =========================

class Equipamento:
    def __init__(self, id, nome, quantidade_total):
        self.id = id
        self.nome = nome
        self.quantidade_total = quantidade_total

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
        self.status = StatusSolicitacao.FORNECIDA

    def cancelar(self):
        if self.status == StatusSolicitacao.FORNECIDA:
            self.equipamento.atualizar_quantidade(self.quantidade)
        self.status = StatusSolicitacao.CANCELADA


# =========================
# QUADRA
# =========================

class Quadra:
    def __init__(self, id, nome, modalidade, capacidade,
                 valor_hora, supervisor):
        self.id = id
        self.nome = nome
        self.modalidade = modalidade
        self.capacidade = capacidade
        self.valor_hora = Decimal(str(valor_hora))
        self.supervisor = supervisor
        self.agenda = Agenda()
        self.equipamentos = []

    def atualizar(self, nome, modalidade, capacidade):
        self.nome = nome
        self.modalidade = modalidade
        self.capacidade = capacidade

    def definir_preco(self, valor):
        valor = Decimal(str(valor))
        if valor < 0:
            raise ValueError("Preço não pode ser negativo.")
        self.valor_hora = valor

    def disponibilizar(self):
        return True

    def desativar(self):
        return False

    def calcular_valor(self, inicio, fim):
        horas = Decimal(str((fim - inicio).total_seconds())) / Decimal("3600")
        return self.valor_hora * horas


# =========================
# PARTIDAS
# =========================

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

        if len(self.participantes) >= self.limite_participantes:
            raise ValueError("Partida lotada.")

        if not self.publica and atleta not in self.autorizados:
            raise PermissionError("Atleta não autorizado.")

        if atleta not in self.participantes:
            self.participantes.append(atleta)

    def remover_participante(self, atleta):
        if atleta in self.participantes:
            self.participantes.remove(atleta)

    def fechar_participantes(self):
        self.participantes_fechados = True


# =========================
# RESERVAS
# =========================

class Reserva:
    def __init__(self, id, inicio, fim, responsavel, quadra):
        self.id = id
        self.inicio = inicio
        self.fim = fim
        self.valor_total = Decimal("0")
        self.status = StatusReserva.ATIVA
        self.responsavel = responsavel
        self.quadra = quadra
        self.partida = None
        self.solicitacoes = []

        if inicio >= fim:
            raise ValueError("O início deve ser anterior ao fim.")

    def sobrepoe(self, inicio, fim):
        return (
            self.inicio < fim
            and self.fim > inicio
            and self.status == StatusReserva.ATIVA
        )

    def calcular_rateio(self):
        if self.partida is None or not self.partida.participantes:
            return {}

        valor = self.quadra.calcular_valor(self.inicio, self.fim)
        quantidade = len(self.partida.participantes)
        valor_individual = (valor / quantidade).quantize(
            Decimal("0.01")
        )

        return {
            atleta.nome: valor_individual
            for atleta in self.partida.participantes
        }

    def reagendar(self, inicio, fim):
        if inicio >= fim:
            raise ValueError("O início deve ser anterior ao fim.")
        self.inicio = inicio
        self.fim = fim

    def cancelar(self):
        if self.status != StatusReserva.ATIVA:
            raise ValueError("Reserva não está ativa.")
        self.status = StatusReserva.CANCELADA

    def concluir(self):
        if self.status != StatusReserva.ATIVA:
            raise ValueError("Reserva não está ativa.")
        self.status = StatusReserva.CONCLUIDA


# =========================
# CARTEIRA E CRÉDITOS
# =========================

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


# =========================
# PAGAMENTOS E REPASSES
# =========================

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


# =========================
# DENUNCIAS E AVALIACOES
# =========================

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
    def __init__(self, nota, comentario, autor, quadra):
        if not 1 <= nota <= 5:
            raise ValueError("A nota deve estar entre 1 e 5.")
        self.nota = nota
        self.comentario = comentario
        self.autor = autor
        self.quadra = quadra
