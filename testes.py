
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, time
from decimal import Decimal

from enums import StatusPagamento, StatusReserva, StatusSolicitacao
from modelos import (
    Usuario, Administrador, Supervisor, Atleta,
    Quadra, FaixaFuncionamento, Carteira, Equipamento
)
from servicos import SistemaReservas


class TestesSistemaReservas(unittest.TestCase):

    def setUp(self):
        self.sistema = SistemaReservas()

        self.admin = Administrador(
            1, "Administrador", "admin@email.com"
        )

        self.supervisor = self.sistema.cadastrar_supervisor(
            self.admin, "Supervisor", "supervisor@email.com"
        )

        self.atleta = Atleta(
            3, "Atleta", "atleta@email.com"
        )

        self.quadra = self.sistema.cadastrar_quadra(
            self.supervisor,
            "Quadra Central",
            "Futsal",
            20,
            Decimal("100.00")
        )

        self.inicio = (
            datetime.now() + timedelta(days=1)
        ).replace(hour=10, minute=0, second=0, microsecond=0)

        self.fim = self.inicio + timedelta(hours=1)

        faixa = FaixaFuncionamento(
            self.inicio.weekday(),
            time(8, 0),
            time(22, 0)
        )

        self.sistema.definir_disponibilidade(
            self.supervisor, self.quadra, [faixa]
        )

    def test_usuario_abstrato(self):
        with self.assertRaises(TypeError):
            Usuario(1, "Teste", "teste@email.com")

    def test_permissao_administrador(self):
        self.assertTrue(
            self.admin.tem_permissao("qualquer_acao")
        )

    def test_permissao_atleta(self):
        self.assertTrue(
            self.atleta.tem_permissao("criar_reserva")
        )

        self.assertFalse(
            self.atleta.tem_permissao("gerenciar_quadras")
        )

    def test_cadastrar_quadra(self):
        self.assertEqual(self.quadra.nome, "Quadra Central")
        self.assertEqual(self.quadra.modalidade, "Futsal")

    def test_calcular_valor_quadra(self):
        valor = self.quadra.calcular_valor(
            self.inicio, self.fim
        )

        self.assertEqual(valor, Decimal("100.00"))

    def test_criar_reserva(self):
        reserva = self.sistema.criar_reserva(
            self.atleta,
            self.quadra,
            self.inicio,
            self.fim
        )

        self.assertEqual(reserva.valor_total, Decimal("100.00"))

    def test_impedir_reserva_conflitante(self):
        self.sistema.criar_reserva(
            self.atleta,
            self.quadra,
            self.inicio,
            self.fim
        )

        with self.assertRaises(ValueError):
            self.sistema.criar_reserva(
                self.atleta,
                self.quadra,
                self.inicio,
                self.fim
            )

    def test_cancelar_reserva(self):
        reserva = self.sistema.criar_reserva(
            self.atleta,
            self.quadra,
            self.inicio,
            self.fim
        )

        self.sistema.cancelar_reserva(
            self.atleta, reserva
        )

        self.assertEqual(
            reserva.status.value, "Cancelada"
        )

    def test_creditar_carteira(self):
        carteira = Carteira()
        carteira.creditar(200)

        self.assertEqual(
            carteira.saldo, Decimal("200")
        )

    def test_impedir_saldo_insuficiente(self):
        carteira = Carteira()

        with self.assertRaises(ValueError):
            carteira.debitar(100)

    def test_comprar_creditos(self):
        compra = self.sistema.comprar_creditos(
            self.atleta, Decimal("200.00")
        )

        compra.confirmar()

        self.assertEqual(
            self.atleta.carteira.saldo,
            Decimal("200.00")
        )

    def reservar(self, horas_depois=0):
        deslocamento = timedelta(hours=horas_depois)
        return self.sistema.criar_reserva(
            self.atleta, self.quadra, self.inicio + deslocamento, self.fim + deslocamento
        )

    def inscrever(self, reserva, atleta_id):
        convidado = Atleta(atleta_id, self.atleta.nome, f"atleta{atleta_id}@email.com")
        self.sistema.autorizar_participante(self.atleta, reserva, convidado)
        self.sistema.participar_partida(convidado, reserva)
        return convidado

    # Atualização 1 — disponibilidade, conflitos e horários consecutivos.
    def test_disponibilidade_para_criar_e_reagendar(self):
        consultar = self.sistema.consultar_disponibilidade
        self.quadra.desativar()
        self.assertFalse(consultar(self.quadra, self.inicio, self.fim))
        with self.assertRaises(ValueError):
            self.reservar()
        self.quadra.disponibilizar()
        for inicio, fim in (
            (self.inicio - timedelta(days=7), self.fim - timedelta(days=7)),
            (self.inicio, self.inicio),
            (self.inicio, self.fim + timedelta(days=1)),
            (self.inicio, self.fim.replace(hour=23)),
        ):
            with self.subTest(inicio=inicio, fim=fim):
                self.assertFalse(consultar(self.quadra, inicio, fim))
                with self.assertRaises(ValueError):
                    self.sistema.criar_reserva(self.atleta, self.quadra, inicio, fim)
        primeira = self.reservar()
        self.assertFalse(consultar(self.quadra, self.inicio, self.fim))
        seguinte = self.reservar(1)
        self.sistema.reagendar_reserva(self.atleta, primeira, self.inicio, self.fim)
        with self.assertRaises(ValueError):
            self.sistema.reagendar_reserva(self.atleta, primeira, seguinte.inicio, seguinte.fim)

    # Atualização 2 — partida privada com a capacidade cadastrada e o responsável.
    def test_partida_criada_com_a_reserva(self):
        self.sistema.atualizar_quadra(self.supervisor, self.quadra, "Dupla", "Tênis", 2)
        reserva = self.reservar()
        partida = reserva.partida
        self.assertFalse(partida.publica)
        self.assertEqual(partida.limite_participantes, 2)
        self.assertEqual(partida.participantes, [self.atleta])
        convidado = self.inscrever(reserva, 4)
        self.sistema.definir_privacidade(self.atleta, reserva, True)
        self.assertTrue(partida.publica)
        self.assertIs(reserva.partida, partida)
        self.assertEqual(partida.participantes, [self.atleta, convidado])

    # Atualização 3 — centavos, atletas homônimos e preço contratado.
    def test_rateio_por_id_preserva_centavos(self):
        reserva = self.reservar()
        segundo = self.inscrever(reserva, 4)
        terceiro = self.inscrever(reserva, 5)
        self.sistema.definir_preco(self.supervisor, self.quadra, 180)
        self.assertEqual(self.sistema.calcular_rateio(reserva), {
            self.atleta.id: Decimal("33.34"),
            segundo.id: Decimal("33.33"),
            terceiro.id: Decimal("33.33"),
        })

    # Atualização 4 — primeiro débito, duplicidade e modos incompatíveis.
    def test_pagamento_so_fecha_lista_apos_debito(self):
        reserva = self.reservar()
        convidado = self.inscrever(reserva, 4)
        pagar = self.sistema.pagar_reserva
        with self.assertRaises(PermissionError):
            pagar(convidado, reserva, integral=True)
        with self.assertRaises(ValueError):
            pagar(convidado, reserva, integral=False)
        self.assertEqual(convidado.carteira.saldo, 0)
        self.assertIsNone(reserva.modo_pagamento)
        self.assertFalse(reserva.partida.participantes_fechados)
        self.assertEqual(reserva.partida.participantes, [self.atleta, convidado])
        convidado.carteira.creditar(150)
        pagar(convidado, reserva, integral=False)
        self.atleta.carteira.creditar(100)
        with self.assertRaises(ValueError):
            pagar(convidado, reserva, integral=False)
        with self.assertRaises(ValueError):
            pagar(self.atleta, reserva, integral=True)
        with self.assertRaises(ValueError):
            reserva.partida.remover_participante(convidado)
        with self.assertRaises(ValueError):
            self.inscrever(reserva, 5)
        self.assertEqual(len(self.sistema.pagamentos), 1)
        self.assertEqual(self.atleta.carteira.saldo, 100)
        self.assertEqual(convidado.carteira.saldo, 100)

    # Atualização 5 — estorno individual, histórico e devolução ao estoque.
    def test_cancelamento_estorna_cada_pagador_uma_vez(self):
        reserva = self.reservar()
        convidado = self.inscrever(reserva, 4)
        for atleta in (self.atleta, convidado):
            atleta.carteira.creditar(80)
            self.sistema.pagar_reserva(atleta, reserva, integral=False)
        bola = Equipamento(1, "Bola", 3)
        fornecida = self.sistema.solicitar_equipamento(self.atleta, reserva, bola, 2)
        pendente = self.sistema.solicitar_equipamento(self.atleta, reserva, bola, 1)
        self.sistema.fornecer_equipamento(self.supervisor, reserva, fornecida)
        self.assertEqual(bola.quantidade_total, 1)
        self.sistema.banir_usuario(self.admin, convidado, "Teste")
        self.sistema.cancelar_reserva(self.supervisor, reserva)
        with self.assertRaises(ValueError):
            self.sistema.cancelar_reserva(self.supervisor, reserva)
        self.assertEqual((self.atleta.carteira.saldo, convidado.carteira.saldo), (80, 80))
        self.assertEqual(bola.quantidade_total, 3)
        self.assertEqual([p.status for p in self.sistema.pagamentos], [StatusPagamento.ESTORNADO] * 2)
        self.assertEqual([fornecida.status, pendente.status], [StatusSolicitacao.CANCELADA] * 2)

    # Atualização 6 — interdição parcial preserva a reserva no limite do bloqueio.
    def test_interdicao_parcial_estorna_e_mantem_bloqueio(self):
        atingida = self.reservar()
        seguinte = self.reservar(1)
        self.atleta.carteira.creditar(100)
        pagamento = self.sistema.pagar_reserva(self.atleta, atingida)
        inicio = self.inicio + timedelta(minutes=30)
        self.sistema.interditar_quadra(self.admin, self.quadra, inicio, self.fim, "Reparo")
        self.assertEqual(atingida.status, StatusReserva.CANCELADA)
        self.assertEqual(seguinte.status, StatusReserva.ATIVA)
        self.assertEqual(pagamento.status, StatusPagamento.ESTORNADO)
        self.assertEqual(self.atleta.carteira.saldo, 100)
        self.assertFalse(self.sistema.consultar_disponibilidade(self.quadra, inicio, self.fim))

    # Atualização 7 — reagendamento valida todos os saldos e mantém parcelas pendentes.
    def test_reagendamento_financeiro_sem_ajustes_parciais(self):
        reserva = self.reservar()
        segundo = self.inscrever(reserva, 4)
        terceiro = self.inscrever(reserva, 5)
        self.atleta.carteira.creditar(100)
        segundo.carteira.creditar(Decimal("33.33"))
        primeiro_pago = self.sistema.pagar_reserva(self.atleta, reserva, integral=False)
        segundo_pago = self.sistema.pagar_reserva(segundo, reserva, integral=False)
        novo_inicio = self.fim
        novo_fim = novo_inicio + timedelta(hours=2)
        with self.assertRaises(ValueError):
            self.sistema.reagendar_reserva(self.atleta, reserva, novo_inicio, novo_fim)
        self.assertEqual((reserva.inicio, reserva.fim, reserva.valor_total), (self.inicio, self.fim, 100))
        self.assertEqual((primeiro_pago.valor, segundo_pago.valor), (Decimal("33.34"), Decimal("33.33")))
        self.assertEqual((self.atleta.carteira.saldo, segundo.carteira.saldo), (Decimal("66.66"), 0))
        self.sistema.definir_preco(self.supervisor, self.quadra, 30)
        self.sistema.reagendar_reserva(self.atleta, reserva, novo_inicio, novo_fim)
        self.assertEqual((reserva.inicio, reserva.fim, reserva.valor_total), (novo_inicio, novo_fim, 60))
        self.assertEqual((primeiro_pago.valor, segundo_pago.valor), (20, 20))
        self.assertEqual((self.atleta.carteira.saldo, segundo.carteira.saldo), (80, Decimal("13.33")))
        self.sistema.definir_preco(self.supervisor, self.quadra, 45)
        self.sistema.reagendar_reserva(self.atleta, reserva, novo_inicio, novo_fim)
        self.assertEqual((primeiro_pago.valor, segundo_pago.valor), (30, 30))
        self.assertEqual((self.atleta.carteira.saldo, segundo.carteira.saldo), (70, Decimal("3.33")))
        self.assertEqual(self.sistema.pagamentos, [primeiro_pago, segundo_pago])
        terceiro.carteira.creditar(30)
        self.assertEqual(self.sistema.pagar_reserva(terceiro, reserva, integral=False).valor, 30)

    # Atualização 8 — repasse integral do lote e rejeição de repasse repetido.
    def test_repasse_valida_todo_o_lote(self):
        paga = self.reservar()
        pendente = self.reservar(1)
        pendente.concluir()
        self.atleta.carteira.creditar(100)
        self.sistema.pagar_reserva(self.atleta, paga)
        repassar = self.sistema.efetuar_repasse
        with self.assertRaises(ValueError):
            repassar(self.admin, self.supervisor, [paga])
        paga.concluir()
        for lote in ([], [paga, paga], [paga, pendente]):
            with self.subTest(lote=lote), self.assertRaises(ValueError):
                repassar(self.admin, self.supervisor, lote)
        outro = self.sistema.cadastrar_supervisor(self.admin, "Outro", "outro@email.com")
        with self.assertRaises(ValueError):
            repassar(self.admin, outro, [paga])
        with self.assertRaises(PermissionError):
            repassar(self.supervisor, self.supervisor, [paga])
        self.assertEqual(self.sistema.repasses, [])
        repasse = repassar(self.admin, self.supervisor, [paga])
        self.assertEqual(repasse.valor, 100)
        with self.assertRaises(ValueError):
            repassar(self.admin, self.supervisor, [paga])
        self.assertEqual(self.sistema.repasses, [repasse])

    # Atualização 9 — permissões por quadra, por conta e por estado da partida.
    def test_permissoes_no_servico(self):
        reserva = self.reservar()
        outro = self.sistema.cadastrar_supervisor(self.admin, "Outro", "outro@email.com")
        self.assertIn(reserva.partida, self.sistema.consultar_partidas(self.supervisor))
        self.assertNotIn(reserva.partida, self.sistema.consultar_partidas(outro))
        with self.assertRaises(PermissionError):
            self.sistema.cancelar_reserva(outro, reserva)
        with self.assertRaises(PermissionError):
            self.sistema.interditar_quadra(outro, self.quadra, self.inicio, self.fim, "Reparo")
        self.assertEqual(self.sistema.consultar_dados(self.atleta, self.atleta)["id"], self.atleta.id)
        with self.assertRaises(PermissionError):
            self.sistema.consultar_dados(self.atleta, outro)
        self.sistema.banir_usuario(self.admin, self.atleta, "Teste")
        with self.assertRaises(PermissionError):
            self.sistema.comprar_creditos(self.atleta, 100)
        with self.assertRaises(PermissionError):
            self.reservar(1)

    def test_inscricao_em_partida_cancelada_ou_iniciada(self):
        cancelada = self.reservar()
        iniciada = self.reservar(1)
        for reserva in (cancelada, iniciada):
            self.sistema.definir_privacidade(self.atleta, reserva, True)
            self.assertIn(reserva.partida, self.sistema.consultar_partidas_publicas())
        self.sistema.cancelar_reserva(self.atleta, cancelada)
        with patch("servicos.datetime", wraps=datetime) as relogio:
            relogio.now.return_value = iniciada.inicio
            with self.assertRaises(ValueError):
                self.sistema.cancelar_reserva(self.atleta, iniciada)
            for reserva in (cancelada, iniciada):
                self.assertNotIn(reserva.partida, self.sistema.consultar_partidas_publicas())
                with self.assertRaises(ValueError):
                    self.sistema.participar_partida(Atleta(4, "Ana", "ana@email.com"), reserva)

    # Atualização 10 — avaliação exige supervisor, participação, conclusão e nota válida.
    def test_avaliacao_de_atleta(self):
        reserva = self.reservar()
        avaliar = self.sistema.avaliar_atleta
        outro = self.sistema.cadastrar_supervisor(self.admin, "Outro", "outro@email.com")
        with self.assertRaises(ValueError):
            avaliar(self.supervisor, self.atleta, reserva, 5, "Boa partida")
        reserva.concluir()
        with self.assertRaises(PermissionError):
            avaliar(outro, self.atleta, reserva, 5, "Boa partida")
        visitante = Atleta(4, "Ana", "ana@email.com")
        with self.assertRaises(ValueError):
            avaliar(self.supervisor, visitante, reserva, 5, "Boa partida")
        for nota in (0, 6):
            with self.subTest(nota=nota), self.assertRaises(ValueError):
                avaliar(self.supervisor, self.atleta, reserva, nota, "Boa partida")
        self.assertEqual(self.sistema.avaliacoes, [])
        avaliacao = avaliar(self.supervisor, self.atleta, reserva, 5, "Boa partida")
        self.assertIs(avaliacao.supervisor, self.supervisor)
        self.assertIs(avaliacao.atleta, self.atleta)
        self.assertIs(avaliacao.reserva, reserva)
        self.assertEqual((avaliacao.nota, avaliacao.comentario), (5, "Boa partida"))
        self.assertIsInstance(avaliacao.data, datetime)
        self.assertEqual(self.sistema.avaliacoes, [avaliacao])


if __name__ == "__main__":
    unittest.main(verbosity=2)
