
from datetime import datetime
from decimal import Decimal

from modelos import (
    Administrador, Supervisor, Atleta, Quadra, Reserva,
    Avaliacao, Pagamento, CompraCredito, Repasse,
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

    # Atualização 9 — verifica a conta que inicia cada operação.
    @staticmethod
    def _exigir_conta_ativa(autor):
        if autor.banido:
            raise PermissionError("Conta banida.")

    def cadastrar_supervisor(self, autor, nome, email):
        self._exigir_conta_ativa(autor)
        if not isinstance(autor, Administrador):
            raise PermissionError("Somente administrador pode cadastrar supervisor.")

        supervisor = Supervisor(
            len(self.usuarios) + 1, nome, email
        )
        self.usuarios.append(supervisor)
        return supervisor

    def consultar_dados(self, autor, usuario):
        self._exigir_conta_ativa(autor)
        if not autor.tem_permissao("consultar_dados") or (
            isinstance(autor, Atleta) and autor != usuario
        ):
            raise PermissionError("Sem permissão.")

        return usuario.consultar_dados()

    def banir_usuario(self, autor, usuario, motivo):
        self._exigir_conta_ativa(autor)
        if not isinstance(autor, Administrador):
            raise PermissionError("Somente administrador pode banir usuários.")

        usuario.banir(motivo)

    def registrar_denuncia(self, autor, denunciado, motivo):
        self._exigir_conta_ativa(autor)
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
        self._exigir_conta_ativa(autor)
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
        self._exigir_conta_ativa(autor)
        if autor != quadra.supervisor:
            raise PermissionError("Supervisor não autorizado.")

        quadra.atualizar(nome, modalidade, capacidade)

    def excluir_quadra(self, autor, quadra):
        self._exigir_conta_ativa(autor)
        if autor != quadra.supervisor:
            raise PermissionError("Supervisor não autorizado.")

        if any(r.quadra == quadra for r in self.reservas):
            raise ValueError("Quadra possui histórico de reservas.")

        self.quadras.remove(quadra)

    def definir_preco(self, autor, quadra, valor):
        self._exigir_conta_ativa(autor)
        if autor != quadra.supervisor:
            raise PermissionError("Supervisor não autorizado.")

        quadra.definir_preco(valor)

    def disponibilizar_quadra(self, autor, quadra):
        self._exigir_conta_ativa(autor)
        if autor != quadra.supervisor:
            raise PermissionError("Supervisor não autorizado.")

        return quadra.disponibilizar()

    def definir_disponibilidade(self, autor, quadra, faixas):
        self._exigir_conta_ativa(autor)
        if autor != quadra.supervisor:
            raise PermissionError("Supervisor não autorizado.")

        quadra.agenda.faixas = list(faixas)

    # Atualização 1 — consulta, criação e reagendamento verificam o mesmo período.
    def consultar_disponibilidade(self, quadra, inicio, fim, *, ignorar=None):
        return (
            quadra.ativa and datetime.now(inicio.tzinfo) < inicio < fim
            and quadra.agenda.permite_periodo(inicio, fim)
            and not any(
                r is not ignorar and r.quadra == quadra and r.sobrepoe(inicio, fim)
                for r in self.reservas
            )
        )

    def interditar_quadra(self, autor, quadra, inicio, fim, motivo):
        self._exigir_conta_ativa(autor)
        if not isinstance(autor, Administrador) and autor != quadra.supervisor:
            raise PermissionError("Sem permissão para interditar esta quadra.")
        if inicio >= fim:
            raise ValueError("Período de interdição inválido.")

        bloqueio = Bloqueio(inicio, fim, motivo)
        # Atualização 6 — cancela as reservas atingidas e mantém a interdição.
        for reserva in self.reservas:
            if reserva.quadra == quadra and reserva.sobrepoe(inicio, fim):
                self._cancelar_com_estorno(reserva)
        quadra.agenda.adicionar_bloqueio(bloqueio)

        return bloqueio

    # =========================
    # RESERVAS
    # =========================

    def criar_reserva(self, autor, quadra, inicio, fim):
        self._exigir_conta_ativa(autor)
        if not isinstance(autor, Atleta):
            raise PermissionError("Somente atletas podem criar reservas.")

        if inicio >= fim:
            raise ValueError("O início deve ser anterior ao fim.")

        if quadra not in self.quadras:
            raise ValueError("Quadra não cadastrada.")

        if not self.consultar_disponibilidade(quadra, inicio, fim):
            raise ValueError("Horário fora do funcionamento ou bloqueado.")

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
        self._exigir_conta_ativa(autor)
        if autor != reserva.responsavel:
            raise PermissionError("Somente responsável pode alterar a privacidade.")

        reserva.partida.definir_privacidade(publica)

    def cancelar_reserva(self, autor, reserva):
        self._exigir_conta_ativa(autor)
        if autor not in (reserva.responsavel, reserva.quadra.supervisor):
            raise PermissionError("Sem permissão para cancelar.")

        if reserva.inicio <= datetime.now(reserva.inicio.tzinfo):
            raise ValueError("Reserva já iniciada.")
        self._cancelar_com_estorno(reserva)

    def _pagamentos_ativos(self, reserva):
        return [p for p in self.pagamentos
                if p.reserva == reserva and p.status == StatusPagamento.PAGO]

    # Atualização 5 — estorna ao pagador e cancela cada solicitação da reserva.
    def _cancelar_com_estorno(self, reserva):
        reserva.cancelar()
        for pagamento in self._pagamentos_ativos(reserva):
            pagamento.estornar()
        for solicitacao in reserva.solicitacoes:
            solicitacao.cancelar()

    def reagendar_reserva(self, autor, reserva, inicio, fim):
        self._exigir_conta_ativa(autor)
        if autor != reserva.responsavel:
            raise PermissionError("Somente responsável pode reagendar.")

        if reserva.status != StatusReserva.ATIVA:
            raise ValueError("Reserva não está ativa.")

        # Atualização 7 — valida todos os ajustes antes de alterar a reserva.
        if reserva.inicio <= datetime.now(reserva.inicio.tzinfo):
            raise ValueError("Reserva já iniciada.")
        if not self.consultar_disponibilidade(reserva.quadra, inicio, fim, ignorar=reserva):
            raise ValueError("Horário indisponível.")
        novo_total = reserva.quadra.calcular_valor(inicio, fim)
        parcelas = reserva._ratear_valor(novo_total)
        ajustes = []
        for pagamento in self._pagamentos_ativos(reserva):
            novo_valor = (novo_total if reserva.modo_pagamento == "integral"
                          else parcelas[pagamento.pagador.id])
            diferenca = novo_valor - pagamento.valor
            if diferenca > pagamento.pagador.carteira.saldo:
                raise ValueError("Saldo insuficiente para reagendar.")
            ajustes.append((pagamento, novo_valor, diferenca))

        for pagamento, novo_valor, diferenca in ajustes:
            carteira = pagamento.pagador.carteira
            if diferenca > 0:
                carteira.debitar(diferenca)
            elif diferenca < 0:
                carteira.creditar(-diferenca)
            pagamento.valor = novo_valor
        reserva.reagendar(inicio, fim)
        reserva.valor_total = novo_total

    def calcular_rateio(self, reserva):
        if reserva.partida is None:
            raise ValueError("Reserva não possui partida.")

        return reserva.calcular_rateio()

    def pagar_reserva(self, autor, reserva, integral=True):
        self._exigir_conta_ativa(autor)
        if not isinstance(autor, Atleta):
            raise PermissionError("Somente atletas podem pagar.")

        if reserva.status != StatusReserva.ATIVA:
            raise ValueError("Reserva não está ativa.")

        # Atualização 4 — valida modo, pagador e saldo devido antes do débito.
        modo = "integral" if integral else "rateado"
        pagos = self._pagamentos_ativos(reserva)
        if reserva.modo_pagamento not in (None, modo):
            raise ValueError("Modo de pagamento já definido.")
        if any(p.pagador.id == autor.id for p in pagos):
            raise ValueError("Pagamento já realizado.")
        if integral:
            if autor != reserva.responsavel:
                raise PermissionError("Somente o responsável pode pagar integralmente.")
            valor = reserva.valor_total
        else:
            rateio = reserva.calcular_rateio()
            if autor not in reserva.partida.participantes:
                raise ValueError("Atleta não participa da partida.")
            valor = rateio[autor.id]

        if valor + sum(p.valor for p in pagos) > reserva.valor_total:
            raise ValueError("Pagamento excede o total devido.")

        pagamento = Pagamento(
            len(self.pagamentos) + 1,
            valor,
            autor,
            reserva
        )

        pagamento.pagar()
        reserva.modo_pagamento = modo
        reserva.partida.fechar_participantes()
        self.pagamentos.append(pagamento)

        return pagamento

    # =========================
    # PARTIDAS
    # =========================

    def participar_partida(self, atleta, reserva):
        self._exigir_conta_ativa(atleta)
        if reserva.partida is None:
            raise ValueError("Reserva ainda não possui partida.")

        if not isinstance(atleta, Atleta):
            raise PermissionError("Somente atletas podem participar.")

        if not self._aceita_inscricao(reserva):
            raise ValueError("Partida indisponível para inscrição.")
        reserva.partida.adicionar_participante(atleta)

    def autorizar_participante(self, autor, reserva, atleta):
        self._exigir_conta_ativa(autor)
        if autor != reserva.responsavel:
            raise PermissionError("Somente responsável pode autorizar.")

        if reserva.partida is None:
            raise ValueError("Reserva ainda não possui partida.")

        reserva.partida.autorizar_participante(atleta)

    def _aceita_inscricao(self, reserva):
        return (reserva.status == StatusReserva.ATIVA
                and reserva.inicio > datetime.now(reserva.inicio.tzinfo)
                and not reserva.partida.participantes_fechados)

    def consultar_partidas_publicas(self):
        return [
            reserva.partida
            for reserva in self.reservas
            if reserva.partida is not None
            and self._aceita_inscricao(reserva)
            and reserva.partida.publica
        ]

    def consultar_partidas(self, autor):
        self._exigir_conta_ativa(autor)
        return [
            reserva.partida
            for reserva in self.reservas
            if reserva.partida is not None
            and (
                autor == reserva.quadra.supervisor
                or autor == reserva.responsavel
                or autor in reserva.partida.participantes
            )
        ]

    # =========================
    # EQUIPAMENTOS
    # =========================

    def solicitar_equipamento(
        self, autor, reserva, equipamento, quantidade
    ):
        self._exigir_conta_ativa(autor)
        if autor != reserva.responsavel:
            raise PermissionError("Somente responsável pode solicitar.")

        if reserva.status != StatusReserva.ATIVA or quantidade <= 0:
            raise ValueError("Reserva inativa ou quantidade inválida.")

        solicitacao = SolicitacaoEquipamento(
            len(reserva.solicitacoes) + 1,
            quantidade,
            equipamento
        )

        reserva.solicitacoes.append(solicitacao)
        return solicitacao

    def fornecer_equipamento(self, autor, reserva, solicitacao):
        self._exigir_conta_ativa(autor)
        if autor != reserva.quadra.supervisor:
            raise PermissionError("Somente supervisor da quadra pode fornecer.")

        if solicitacao not in reserva.solicitacoes:
            raise ValueError("Solicitação não pertence à reserva.")

        solicitacao.fornecer()

    # =========================
    # CREDITOS
    # =========================

    def comprar_creditos(self, autor, valor):
        self._exigir_conta_ativa(autor)
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
        self._exigir_conta_ativa(autor)
        if not isinstance(autor, Administrador):
            raise PermissionError("Somente administrador pode efetuar repasse.")

        if not isinstance(supervisor, Supervisor):
            raise ValueError("Supervisor inválido.")

        # Atualização 8 — verifica o lote completo antes de registrar o repasse.
        reservas = tuple(reservas)
        if not reservas or len(set(reservas)) != len(reservas):
            raise ValueError("Lote vazio ou com reservas repetidas.")
        repassadas = {r for repasse in self.repasses for r in repasse.reservas}
        for reserva in reservas:
            if (reserva not in self.reservas or reserva.quadra.supervisor != supervisor
                    or reserva.status != StatusReserva.CONCLUIDA or reserva in repassadas):
                raise ValueError("Reserva inválida para este repasse.")
            if sum(p.valor for p in self._pagamentos_ativos(reserva)) != reserva.valor_total:
                raise ValueError("Reserva com pagamento pendente.")

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

    # Atualização 10 — registra a avaliação do participante pelo supervisor da quadra.
    def avaliar_atleta(self, autor, atleta, reserva, nota, comentario):
        self._exigir_conta_ativa(autor)
        if not isinstance(autor, Supervisor) or autor != reserva.quadra.supervisor:
            raise PermissionError("Somente o supervisor da quadra pode avaliar.")
        if reserva.status != StatusReserva.CONCLUIDA:
            raise ValueError("Reserva ainda não concluída.")
        if atleta not in reserva.partida.participantes:
            raise ValueError("Atleta não participou da partida.")
        avaliacao = Avaliacao(nota, comentario, autor, atleta, reserva)
        self.avaliacoes.append(avaliacao)
        return avaliacao
