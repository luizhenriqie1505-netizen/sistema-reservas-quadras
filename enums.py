
from enum import Enum


class StatusReserva(Enum):
    ATIVA = "Ativa"
    CANCELADA = "Cancelada"
    CONCLUIDA = "Concluida"


class StatusCompraCredito(Enum):
    PENDENTE = "Pendente"
    CONFIRMADA = "Confirmada"
    CANCELADA = "Cancelada"


class StatusPagamento(Enum):
    PENDENTE = "Pendente"
    PAGO = "Pago"
    ESTORNADO = "Estornado"


class StatusRepasse(Enum):
    PENDENTE = "Pendente"
    EFETUADO = "Efetuado"


class StatusSolicitacao(Enum):
    SOLICITADA = "Solicitada"
    FORNECIDA = "Fornecida"
    CANCELADA = "Cancelada"


class StatusDenuncia(Enum):
    ABERTA = "Aberta"
    ENCERRADA = "Encerrada"
