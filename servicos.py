
from datetime import datetime
from decimal import Decimal

from modelos import (
    Administrador, Supervisor, Atleta, Quadra, Reserva,
    Partida, Pagamento, CompraCredito, Repasse,
    Denuncia, SolicitacaoEquipamento, Bloqueio
)

from enums import StatusReserva, StatusPagamento


class SistemaReservas:

    def __init__(self):
        self.usuarios = []
        self.quadras = []
        self.reservas = []
        self.compras_credito = []
        self.pagamentos = []
        self.repasses = []
        self.avaliacoes = []
        self.denuncias = []

    # =========================
    # USUARIOS
    # =========================

    def cadastrar_supervisor(self, autor, nome, email):
        if not isinstance(autor, Administrador):
            raise PermissionError("Somente administrador pode cadastrar supervisor.")

        supervisor = Supervisor(
            len(self.usuarios) + 1, nome, email
        )
        self.usuarios.append(supervisor)
        return supervisor

    def consultar_dados(self, autor, usuario):
        if not autor.tem_permissao("consultar_dados"):
            raise PermissionError("Sem permissão.")

        return usuario.consultar_dados()

    def banir_usuario(self, autor, usuario, motivo):
        if not isinstance(autor, Administrador):
            raise PermissionError("Somente administrador pode banir usuários.")

        usuario.banir(motivo)

    def registrar_denuncia(self, autor, denunciado, motivo):
        if autor.banido:
            raise PermissionError("Usuário banido não pode denunciar.")

        denuncia = Denuncia(
            len(self.denuncias) + 1,
            motivo,
            autor,
            denunciado
        )

        self.denuncias.append(denuncia)
        return denuncia

    # =========================
    # QUADRAS
    # =========================

    def cadastrar_quadra(
        self, autor, nome, modalidade,
        capacidade, valor_hora
    ):
        if not isinstance(autor, Supervisor):
            raise PermissionError("Somente supervisor pode cadastrar quadras.")

        quadra = Quadra(
            len(self.quadras) + 1,
            nome,
            modalidade,
            capacidade,
            valor_hora,
            autor
        )

        self.quadras.append(quadra)
        return quadra

    def consultar_quadras(self):
        return self.quadras.copy()

    def atualizar_quadra(
        self, autor, quadra, nome, modalidade, capacidade
    ):
        if autor != quadra.supervisor:
            raise PermissionError("Supervisor não autorizado.")

        quadra.atualizar(nome, modalidade, capacidade)

    def excluir_quadra(self, autor, quadra):
        if autor != quadra.supervisor:
            raise PermissionError("Supervisor não autorizado.")

        if any(r.quadra == quadra for r in self.reservas):
            raise ValueError("Quadra possui histórico de reservas.")

        self.quadras.remove(quadra)

    def definir_preco(self, autor, quadra, valor):
        if autor != quadra.supervisor:
            raise PermissionError("Supervisor não autorizado.")

        quadra.definir_preco(valor)

    def disponibilizar_quadra(self, autor, quadra):
        if autor != quadra.supervisor:
            raise PermissionError("Supervisor não autorizado.")

        return quadra.disponibilizar()

    def definir_disponibilidade(self, autor, quadra, faixas):
        if autor != quadra.supervisor:
            raise PermissionError("Supervisor não autorizado.")

        quadra.agenda.faixas = list(faixas)

    def consultar_disponibilidade(self, quadra, inicio, fim):
        return quadra.agenda.permite_periodo(inicio, fim)

    def interditar_quadra(self, autor, quadra, inicio, fim, motivo):
        if not isinstance(autor, Supervisor):
            raise PermissionError("Somente supervisor pode interditar quadras.")

        bloqueio = Bloqueio(inicio, fim, motivo)
        quadra.agenda.adicionar_bloqueio(bloqueio)

        return bloqueio

    # =========================
    # RESERVAS
    # =========================

    def criar_reserva(self, autor, quadra, inicio, fim):
        if not isinstance(autor, Atleta):
            raise PermissionError("Somente atletas podem criar reservas.")

        if autor.banido:
            raise PermissionError("Usuário banido não pode reservar.")

        if inicio >= fim:
            raise ValueError("O início deve ser anterior ao fim.")

        if quadra not in self.quadras:
            raise ValueError("Quadra não cadastrada.")

        if not self.consultar_disponibilidade(quadra, inicio, fim):
            raise ValueError("Horário fora do funcionamento ou bloqueado.")

        for reserva in self.reservas:
            if reserva.quadra == quadra and reserva.sobrepoe(inicio, fim):
                raise ValueError("Já existe uma reserva nesse horário.")

        reserva = Reserva(
            len(self.reservas) + 1,
            inicio,
            fim,
            autor,
            quadra
        )

        reserva.valor_total = quadra.calcular_valor(inicio, fim)

        self.reservas.append(reserva)
        return reserva

    def definir_privacidade(self, autor, reserva, publica):
        if autor != reserva.responsavel:
            raise PermissionError("Somente responsável pode alterar a privacidade.")

        if reserva.partida is None:
            reserva.partida = Partida(publica, 20)
        else:
            reserva.partida.definir_privacidade(publica)

    def cancelar_reserva(self, autor, reserva):
        if autor not in (reserva.responsavel,) and not isinstance(autor, Supervisor):
            raise PermissionError("Sem permissão para cancelar.")

        reserva.cancelar()

    def reagendar_reserva(self, autor, reserva, inicio, fim):
        if autor != reserva.responsavel:
            raise PermissionError("Somente responsável pode reagendar.")

        if reserva.status != StatusReserva.ATIVA:
            raise ValueError("Reserva não está ativa.")

        if not self.consultar_disponibilidade(reserva.quadra, inicio, fim):
            raise ValueError("Horário indisponível.")

        for outra in self.reservas:
            if outra != reserva and outra.quadra == reserva.quadra:
                if outra.sobrepoe(inicio, fim):
                    raise ValueError("Horário já reservado.")

        reserva.reagendar(inicio, fim)
        reserva.valor_total = reserva.quadra.calcular_valor(inicio, fim)

    def calcular_rateio(self, reserva):
        if reserva.partida is None:
            raise ValueError("Reserva não possui partida.")

        return reserva.calcular_rateio()

    def pagar_reserva(self, autor, reserva, integral=True):
        if not isinstance(autor, Atleta):
            raise PermissionError("Somente atletas podem pagar.")

        if reserva.status != StatusReserva.ATIVA:
            raise ValueError("Reserva não está ativa.")

        if integral:
            valor = reserva.valor_total
        else:
            rateio = reserva.calcular_rateio()
            if autor not in reserva.partida.participantes:
                raise ValueError("Atleta não participa da partida.")
            valor = rateio[autor.nome]

        pagamento = Pagamento(
            len(self.pagamentos) + 1,
            valor,
            autor,
            reserva
        )

        pagamento.pagar()
        self.pagamentos.append(pagamento)

        return pagamento

    # =========================
    # PARTIDAS
    # =========================

    def participar_partida(self, atleta, reserva):
        if reserva.partida is None:
            raise ValueError("Reserva ainda não possui partida.")

        if not isinstance(atleta, Atleta):
            raise PermissionError("Somente atletas podem participar.")

        reserva.partida.adicionar_participante(atleta)

    def autorizar_participante(self, autor, reserva, atleta):
        if autor != reserva.responsavel:
            raise PermissionError("Somente responsável pode autorizar.")

        if reserva.partida is None:
            raise ValueError("Reserva ainda não possui partida.")

        reserva.partida.autorizar_participante(atleta)

    def consultar_partidas_publicas(self):
        return [
            reserva.partida
            for reserva in self.reservas
            if reserva.partida is not None
            and reserva.partida.publica
        ]

    def consultar_partidas(self, autor):
        return [
            reserva.partida
            for reserva in self.reservas
            if reserva.partida is not None
            and (
                autor == reserva.responsavel
                or autor in reserva.partida.participantes
            )
        ]

    # =========================
    # EQUIPAMENTOS
    # =========================

    def solicitar_equipamento(
        self, autor, reserva, equipamento, quantidade
    ):
        if autor != reserva.responsavel:
            raise PermissionError("Somente responsável pode solicitar.")

        solicitacao = SolicitacaoEquipamento(
            len(reserva.solicitacoes) + 1,
            quantidade,
            equipamento
        )

        reserva.solicitacoes.append(solicitacao)
        return solicitacao

    def fornecer_equipamento(self, autor, reserva, solicitacao):
        if autor != reserva.quadra.supervisor:
            raise PermissionError("Somente supervisor da quadra pode fornecer.")

        if solicitacao not in reserva.solicitacoes:
            raise ValueError("Solicitação não pertence à reserva.")

        solicitacao.fornecer()

    # =========================
    # CREDITOS
    # =========================

    def comprar_creditos(self, autor, valor):
        if not isinstance(autor, Atleta):
            raise PermissionError("Somente atletas podem comprar créditos.")

        compra = CompraCredito(
            len(self.compras_credito) + 1,
            valor,
            autor.carteira
        )

        self.compras_credito.append(compra)
        return compra

    def efetuar_repasse(self, autor, supervisor, reservas):
        if not isinstance(autor, Administrador):
            raise PermissionError("Somente administrador pode efetuar repasse.")

        if not isinstance(supervisor, Supervisor):
            raise ValueError("Supervisor inválido.")

        valor = sum(
            (r.valor_total for r in reservas),
            Decimal("0")
        )

        repasse = Repasse(
            len(self.repasses) + 1,
            valor,
            supervisor,
            reservas
        )

        repasse.efetuar()
        self.repasses.append(repasse)

        return repasse
