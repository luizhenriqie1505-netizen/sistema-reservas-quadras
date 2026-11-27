from collections import Counter
from datetime import datetime, time, timedelta
from decimal import Decimal

from modelos import (
    Administrador, Supervisor, Atleta, Quadra, Reserva,
    Equipamento, Pagamento, CompraCredito, Repasse,
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

    @staticmethod
    def _exigir_conta_ativa(autor):
        # Revisão (João) — uma conta banida ainda consegue iniciar uma reserva?
        if autor.banido:
            raise PermissionError("Conta banida.")

    def validar_cadastro(self, nome, email):
        nome, email = nome.strip(), email.strip().casefold()
        if not nome or not email:
            raise ValueError("Informe o nome e o e-mail.")
        if any(u.email.casefold() == email for u in self.usuarios):
            raise ValueError("E-mail já cadastrado.")
        return nome, email

    def _cadastrar_usuario(self, perfil, nome, email):
        nome, email = self.validar_cadastro(nome, email)
        identificador = max((u.id for u in self.usuarios), default=0) + 1
        usuario = perfil(identificador, nome, email)
        self.usuarios.append(usuario)
        return usuario

    def cadastrar_administrador_inicial(self, nome, email):
        if self.usuarios:
            raise PermissionError("O administrador inicial já foi cadastrado.")
        return self._cadastrar_usuario(Administrador, nome, email)

    def cadastrar_atleta(self, nome, email):
        return self._cadastrar_usuario(Atleta, nome, email)

    def cadastrar_supervisor(self, autor, nome, email):
        self._exigir_conta_ativa(autor)
        if not isinstance(autor, Administrador):
            raise PermissionError("Somente administrador pode cadastrar supervisor.")
        return self._cadastrar_usuario(Supervisor, nome, email)

    def consultar_usuarios(self, autor):
        self._exigir_conta_ativa(autor)
        if not isinstance(autor, Administrador):
            raise PermissionError("Somente o administrador pode listar todos os usuários.")
        return self.usuarios.copy()

    def consultar_dados(self, autor, usuario):
        self._exigir_conta_ativa(autor)
        if not autor.tem_permissao("consultar_dados") or (
            not isinstance(autor, Administrador) and autor != usuario
        ):
            raise PermissionError("Sem permissão.")

        return usuario.consultar_dados()

    def banir_usuario(self, autor, usuario, motivo):
        self._exigir_conta_ativa(autor)
        if not isinstance(autor, Administrador):
            raise PermissionError("Somente administrador pode banir usuários.")

        if isinstance(usuario, Administrador):
            raise PermissionError("Selecione um atleta ou supervisor.")
        usuario.banir(motivo)

    @staticmethod
    def permite_denuncia_entre_perfis(autor, denunciado):
        # Revisão (João) — o supervisor pode denunciar o administrador chamando o serviço diretamente?
        return not (isinstance(autor, Supervisor) and isinstance(denunciado, Administrador))

    def registrar_denuncia(self, autor, denunciado, motivo):
        self._exigir_conta_ativa(autor)
        if not self.permite_denuncia_entre_perfis(autor, denunciado):
            raise PermissionError("Supervisores não podem denunciar administradores.")
        if not motivo or not motivo.strip():
            raise ValueError("Informe o motivo da denúncia.")
        denuncia = Denuncia(
            len(self.denuncias) + 1,
            motivo,
            autor,
            denunciado
        )

        self.denuncias.append(denuncia)
        return denuncia

    def cadastrar_quadra(
        self, autor, nome, modalidade,
        capacidade, valor_hora
    ):
        self._exigir_conta_ativa(autor)
        if not isinstance(autor, Supervisor):
            raise PermissionError("Somente supervisor pode cadastrar quadras.")

        quadra = Quadra(
            max((q.id for q in self.quadras), default=0) + 1,
            nome,
            modalidade,
            capacidade,
            valor_hora,
            autor
        )

        self.quadras.append(quadra)
        return quadra

    def consultar_quadras(self, autor=None):
        if autor is not None:
            self._exigir_conta_ativa(autor)
            if isinstance(autor, Supervisor):
                return [q for q in self.quadras if q.supervisor == autor]
            if isinstance(autor, Atleta):
                return [q for q in self.quadras if q.ativa]
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
            quadra.desativar()
            return

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

        quadra.disponibilizar()

    def definir_disponibilidade(self, autor, quadra, faixas):
        self._exigir_conta_ativa(autor)
        if autor != quadra.supervisor:
            raise PermissionError("Supervisor não autorizado.")

        quadra.agenda.faixas = list(faixas)

    def _intervalos_disponiveis(self, quadra, inicio, fim, ignorar=None):
        if not quadra.ativa or inicio >= fim:
            return []
        # Revisão (João) — o conflito de horários foi corrigido?
        ocupados = ((r.inicio, r.fim) for r in self.reservas
                    if r.quadra == quadra and r is not ignorar and r.status == StatusReserva.ATIVA)
        return quadra.agenda.horarios_livres(inicio, fim, ocupados)

    def consultar_disponibilidade(self, quadra, inicio, fim, *, ignorar=None):
        return (
            datetime.now(inicio.tzinfo) < inicio < fim
            and (inicio, fim) in self._intervalos_disponiveis(quadra, inicio, fim, ignorar)
        )

    def consultar_agenda(self, quadra, primeiro_dia=None, ultimo_dia=None, *, ignorar=None):
        agora = datetime.now()
        if primeiro_dia is None:
            primeiro_dia = agora.date()
            if ultimo_dia is None:
                # Revisão (João) — hoje conta como o primeiro dos sete dias da agenda?
                ultimo_dia = primeiro_dia + timedelta(days=6)
        if ultimo_dia is None:
            ultimo_dia = primeiro_dia
        if ultimo_dia < primeiro_dia:
            raise ValueError("A data final deve ser igual ou posterior à inicial.")

        um_minuto = timedelta(minutes=1)
        proximo_minuto = agora.replace(second=0, microsecond=0) + um_minuto
        for deslocamento in range((ultimo_dia - primeiro_dia).days + 1):
            dia = primeiro_dia + timedelta(days=deslocamento)
            inicio = max(datetime.combine(dia, time.min), proximo_minuto)
            fim = datetime.combine(dia, time.max)
            livres = []
            for de, ate in self._intervalos_disponiveis(quadra, inicio, fim, ignorar):
                primeiro_minuto = de.replace(second=0, microsecond=0)
                if primeiro_minuto < de:
                    primeiro_minuto += um_minuto
                ultimo_minuto = ate.replace(second=0, microsecond=0)
                if primeiro_minuto < ultimo_minuto:
                    livres.append((primeiro_minuto.time(), ultimo_minuto.time()))
            yield dia, livres

    def impacto_interdicao(self, autor, quadra, inicio, fim):
        self._exigir_conta_ativa(autor)
        if not isinstance(autor, Administrador) and autor != quadra.supervisor:
            raise PermissionError("Sem permissão para interditar esta quadra.")
        if inicio >= fim:
            raise ValueError("Período de interdição inválido.")

        atingidas = [r for r in self.reservas if r.quadra == quadra and r.sobrepoe(inicio, fim)]
        estornos = sum((p.valor for r in atingidas for p in self._pagamentos_ativos(r)), Decimal("0"))
        return atingidas, estornos

    def interditar_quadra(self, autor, quadra, inicio, fim, motivo):
        atingidas, _ = self.impacto_interdicao(autor, quadra, inicio, fim)
        bloqueio = Bloqueio(inicio, fim, motivo)
        for reserva in atingidas:
            self._cancelar_com_estorno(reserva)
        quadra.agenda.adicionar_bloqueio(bloqueio)

        return bloqueio

    def criar_reserva(self, autor, quadra, inicio, fim, modo=None):
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
            quadra,
            modo
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

        antecedencia = reserva.inicio - datetime.now(reserva.inicio.tzinfo)
        if antecedencia <= timedelta(0):
            raise ValueError("Reserva já iniciada.")
        # Revisão (João) — ainda dá para cancelar quando faltam exatamente duas horas?
        if antecedencia < timedelta(hours=2):
            raise ValueError("O cancelamento exige pelo menos duas horas de antecedência.")
        self._cancelar_com_estorno(reserva)

    def _pagamentos_ativos(self, reserva):
        return [p for p in self.pagamentos
                if p.reserva == reserva and p.status == StatusPagamento.PAGO]

    def _cancelar_com_estorno(self, reserva):
        reserva.cancelar()
        for pagamento in self._pagamentos_ativos(reserva):
            pagamento.estornar()
        # Revisão (João) — além do estorno, a bola já entregue volta ao estoque?
        for solicitacao in reserva.solicitacoes:
            solicitacao.cancelar()

    def reagendar_reserva(self, autor, reserva, inicio, fim):
        self._exigir_conta_ativa(autor)
        if autor != reserva.responsavel:
            raise PermissionError("Somente responsável pode reagendar.")

        if reserva.status != StatusReserva.ATIVA:
            raise ValueError("Reserva não está ativa.")

        if reserva.inicio <= datetime.now(reserva.inicio.tzinfo):
            raise ValueError("Reserva já iniciada.")
        if not self.consultar_disponibilidade(reserva.quadra, inicio, fim, ignorar=reserva):
            raise ValueError("Horário indisponível.")
        for equipamento, quantidade in reserva.quantidades_solicitadas().items():
            livres = self.unidades_livres(
                reserva.quadra, equipamento, inicio, fim, ignorar=reserva
            )
            if quantidade > livres:
                raise ValueError("Equipamento indisponível no novo horário.")
        novo_total = reserva.quadra.calcular_valor(inicio, fim)
        parcelas = reserva._ratear_valor(novo_total)
        ajustes = []
        for pagamento in self._pagamentos_ativos(reserva):
            novo_valor = (novo_total if reserva.modo_pagamento == "integral"
                          else parcelas[pagamento.pagador.id])
            diferenca = novo_valor - pagamento.valor
            # Revisão (João) — se faltar saldo a um atleta, o horário e os pagamentos anteriores ficam como estavam?
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
        reserva.reagendar(inicio, fim, novo_total)

    def calcular_rateio(self, reserva):
        if reserva.status != StatusReserva.CONCLUIDA or reserva.fim > datetime.now(reserva.fim.tzinfo):
            raise ValueError("O rateio fica disponível após a conclusão da reserva.")
        if reserva.metodo_pagamento not in (None, "rateado"):
            raise ValueError("A reserva foi contratada com pagamento integral.")
        if reserva.partida is None:
            raise ValueError("Reserva não possui partida.")

        return reserva.calcular_rateio()

    def pagar_reserva(self, autor, reserva, integral=True):
        self._exigir_conta_ativa(autor)
        if not isinstance(autor, Atleta):
            raise PermissionError("Somente atletas podem pagar.")

        if integral and reserva.status != StatusReserva.ATIVA:
            raise ValueError("Reserva não está ativa.")

        modo = "integral" if integral else "rateado"
        pagos = self._pagamentos_ativos(reserva)
        if reserva.metodo_pagamento not in (None, modo):
            raise ValueError("Modo de pagamento já definido.")
        # Revisão (João) — uma segunda tentativa da mesma pessoa pode cobrar a parcela de novo?
        if any(p.pagador.id == autor.id for p in pagos):
            raise ValueError("Pagamento já realizado.")
        if integral:
            if autor != reserva.responsavel:
                raise PermissionError("Somente o responsável pode pagar integralmente.")
            valor = reserva.valor_total
        else:
            rateio = self.calcular_rateio(reserva)
            if autor not in reserva.partida.participantes:
                raise ValueError("Atleta não participa da partida.")
            valor = rateio[autor.id]

        if valor == 0:
            raise ValueError("Não há valor a pagar nesta parcela.")
        if valor + sum(p.valor for p in pagos) > reserva.valor_total:
            raise ValueError("Pagamento excede o total devido.")

        pagamento = Pagamento(
            len(self.pagamentos) + 1,
            valor,
            autor,
            reserva
        )

        # Revisão (João) — se o primeiro débito falhar, a lista da partida continua aberta?
        pagamento.pagar()
        reserva.modo_pagamento = modo
        reserva.partida.fechar_participantes()
        self.pagamentos.append(pagamento)

        return pagamento

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
        if not self._aceita_inscricao(reserva):
            raise ValueError("Partida indisponível para convites.")
        if not isinstance(atleta, Atleta) or atleta.banido:
            raise ValueError("O convidado deve ser um atleta com conta ativa.")
        if atleta in reserva.partida.participantes:
            raise ValueError("Atleta já está na partida.")
        reserva.partida.autorizar_participante(atleta)

    def _aceita_inscricao(self, reserva):
        partida = reserva.partida
        return (
            reserva.status == StatusReserva.ATIVA
            and reserva.inicio > datetime.now(reserva.inicio.tzinfo)
            and not partida.participantes_fechados
            and len(partida.participantes) < partida.limite_participantes
        )

    def consultar_opcoes_de_inscricao(self, atleta):
        self._exigir_conta_ativa(atleta)
        if not isinstance(atleta, Atleta):
            raise PermissionError("Somente atletas podem se inscrever.")
        return [reserva for reserva in self.reservas
                if self._aceita_inscricao(reserva)
                and atleta not in reserva.partida.participantes
                and (reserva.partida.publica or atleta in reserva.partida.autorizados)]

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

    def consultar_reservas(self, autor):
        if isinstance(autor, Administrador):
            self._exigir_conta_ativa(autor)
            return self.reservas.copy()
        partidas = set(self.consultar_partidas(autor))
        return [r for r in self.reservas if r.partida in partidas]

    def cadastrar_equipamento(self, autor, quadra, nome, quantidade):
        self._exigir_conta_ativa(autor)
        if autor != quadra.supervisor:
            raise PermissionError("Supervisor não autorizado.")
        if type(quantidade) is not int or quantidade < 1:
            raise ValueError("Estoque inicial deve ser um inteiro positivo.")
        equipamento = Equipamento(len(quadra.equipamentos) + 1, nome, quantidade)
        quadra.equipamentos.append(equipamento)
        return equipamento

    def concluir_reserva(self, autor, reserva):
        self._exigir_conta_ativa(autor)
        if autor != reserva.quadra.supervisor:
            raise PermissionError("Supervisor não autorizado.")
        if reserva.fim > datetime.now(reserva.fim.tzinfo):
            raise ValueError("O horário da reserva ainda não terminou.")
        reserva.concluir()

    def unidades_livres(self, quadra, equipamento, inicio, fim, *, ignorar=None):
        if inicio >= fim:
            raise ValueError("O início deve ser anterior ao fim.")
        capacidade = equipamento.quantidade_total + equipamento.quantidade_emprestada
        cota = quadra.estoque_equipamentos.get(equipamento, capacidade)
        movimentos = Counter()
        pico_na_quadra = 0
        for reserva in self.reservas:
            if reserva is ignorar or not reserva.sobrepoe(inicio, fim):
                continue
            quantidade = reserva.quantidades_solicitadas()[equipamento]
            if quantidade:
                movimentos[max(inicio, reserva.inicio)] += quantidade
                movimentos[min(fim, reserva.fim)] -= quantidade
                if reserva.quadra == quadra:
                    pico_na_quadra = max(pico_na_quadra, quantidade)

        em_uso = pico = 0
        for instante in sorted(movimentos):
            em_uso += movimentos[instante]
            pico = max(pico, em_uso)
        return max(0, min(capacidade - pico, cota - pico_na_quadra))

    def solicitar_equipamento(
        self, autor, reserva, equipamento, quantidade
    ):
        self._exigir_conta_ativa(autor)
        if autor != reserva.responsavel:
            raise PermissionError("Somente responsável pode solicitar.")

        if reserva.status != StatusReserva.ATIVA:
            raise ValueError("Reserva não está ativa.")

        if (not isinstance(quantidade, int) or isinstance(quantidade, bool)
                or quantidade <= 0):
            raise ValueError("Quantidade deve ser um inteiro positivo.")

        livres = self.unidades_livres(
            reserva.quadra, equipamento, reserva.inicio, reserva.fim
        )
        if quantidade > livres:
            raise ValueError(f"Apenas {livres} unidade(s) disponível(is).")

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

        if reserva.status != StatusReserva.ATIVA:
            raise ValueError("Reserva não está ativa.")
        if solicitacao not in reserva.solicitacoes:
            raise ValueError("Solicitação não pertence à reserva.")

        equipamento = solicitacao.equipamento
        livres = self.unidades_livres(reserva.quadra, equipamento, reserva.inicio,
                                      reserva.fim, ignorar=reserva)
        if reserva.quantidades_solicitadas()[equipamento] > livres:
            raise ValueError("Estoque insuficiente no período da reserva.")
        solicitacao.fornecer()

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

    def _erro_de_repasse(self, supervisor, reserva, repassadas):
        if (reserva.quadra.supervisor != supervisor
                or reserva.status != StatusReserva.CONCLUIDA or reserva in repassadas
                or reserva not in self.reservas):
            return "Reserva inválida para este repasse."
        if sum(p.valor for p in self._pagamentos_ativos(reserva)) != reserva.valor_total:
            return "Reserva com pagamento pendente."
        return None

    def consultar_reservas_para_repasse(self, autor):
        self._exigir_conta_ativa(autor)
        if not isinstance(autor, Administrador):
            raise PermissionError("Somente administrador pode consultar repasses.")
        repassadas = {r for repasse in self.repasses for r in repasse.reservas}
        return [r for r in self.reservas if not self._erro_de_repasse(r.quadra.supervisor, r, repassadas)]

    def efetuar_repasse(self, autor, supervisor, reservas):
        self._exigir_conta_ativa(autor)
        if not isinstance(autor, Administrador):
            raise PermissionError("Somente administrador pode efetuar repasse.")

        if not isinstance(supervisor, Supervisor):
            raise ValueError("Supervisor inválido.")

        reservas = tuple(reservas)
        if not reservas or len(set(reservas)) != len(reservas):
            raise ValueError("Lote vazio ou com reservas repetidas.")
        repassadas = {r for repasse in self.repasses for r in repasse.reservas}
        for reserva in reservas:
            erro = self._erro_de_repasse(supervisor, reserva, repassadas)
            if erro:
                raise ValueError(erro)

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

    def avaliar_atleta(self, autor, atleta, reserva, nota, comentario):
        # Revisão (João) — mesmo depois de uma partida concluída, o supervisor pode dar nota ao atleta?
        raise PermissionError("A avaliação de atletas foi desativada.")
