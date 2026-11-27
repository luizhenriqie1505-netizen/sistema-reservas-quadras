
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timedelta, time, timezone
from decimal import Decimal

from enums import StatusPagamento, StatusReserva, StatusSolicitacao
from modelos import (
    Usuario, Administrador, Supervisor, Atleta,
    Quadra, FaixaFuncionamento, Carteira, Equipamento, Pagamento
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

    def concluir_apos_horario(self, reserva):
        with patch("servicos.datetime") as relogio:
            relogio.now.return_value = reserva.fim + timedelta(seconds=1)
            self.sistema.concluir_reserva(self.supervisor, reserva)

    def registrar_pagamento_antigo(self, atleta, reserva, valor):
        pagamento = Pagamento(len(self.sistema.pagamentos) + 1, valor, atleta, reserva)
        pagamento.pagar()
        reserva.modo_pagamento = "rateado"
        reserva.partida.fechar_participantes()
        self.sistema.pagamentos.append(pagamento)
        return pagamento

    def test_rateio_por_id_preserva_centavos(self):
        reserva = self.reservar()
        segundo = self.inscrever(reserva, 4)
        terceiro = self.inscrever(reserva, 5)
        self.sistema.definir_preco(self.supervisor, self.quadra, 180)
        # Revisão (Luiz) — quem paga o centavo que sobra ao dividir R$ 100 entre três atletas?
        with self.assertRaisesRegex(ValueError, "conclusão"):
            self.sistema.calcular_rateio(reserva)
        self.concluir_apos_horario(reserva)
        with patch("servicos.datetime") as relogio:
            relogio.now.return_value = reserva.fim + timedelta(seconds=1)
            parcelas = self.sistema.calcular_rateio(reserva)
        self.assertEqual(parcelas, {
            self.atleta.id: Decimal("33.34"),
            segundo.id: Decimal("33.33"),
            terceiro.id: Decimal("33.33"),
        })

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
        with self.assertRaisesRegex(ValueError, "conclusão"):
            pagar(convidado, reserva, integral=False)
        self.assertEqual(convidado.carteira.saldo, 150)
        self.concluir_apos_horario(reserva)
        with patch("servicos.datetime") as relogio:
            relogio.now.return_value = reserva.fim + timedelta(seconds=1)
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

    def test_cancelamento_estorna_cada_pagador_uma_vez(self):
        reserva = self.reservar()
        convidado = self.inscrever(reserva, 4)
        for atleta in (self.atleta, convidado):
            atleta.carteira.creditar(80)
            self.registrar_pagamento_antigo(atleta, reserva, 50)
        bola = Equipamento(1, "Bola", 3)
        fornecida = self.sistema.solicitar_equipamento(self.atleta, reserva, bola, 2)
        pendente = self.sistema.solicitar_equipamento(self.atleta, reserva, bola, 1)
        self.sistema.fornecer_equipamento(self.supervisor, reserva, fornecida)
        self.assertEqual(bola.quantidade_total, 1)
        self.sistema.banir_usuario(self.admin, convidado, "Teste")
        self.sistema.cancelar_reserva(self.supervisor, reserva)
        with self.assertRaises(ValueError):
            self.sistema.cancelar_reserva(self.supervisor, reserva)
        # Revisão (Ronaldo) — se dois atletas dividiram o pagamento, o estorno volta às duas carteiras?
        self.assertEqual((self.atleta.carteira.saldo, convidado.carteira.saldo), (80, 80))
        self.assertEqual(bola.quantidade_total, 3)
        self.assertEqual([p.status for p in self.sistema.pagamentos], [StatusPagamento.ESTORNADO] * 2)
        self.assertEqual([fornecida.status, pendente.status], [StatusSolicitacao.CANCELADA] * 2)

    def test_interdicao_parcial_estorna_e_mantem_bloqueio(self):
        atingida = self.reservar()
        seguinte = self.reservar(1)
        self.atleta.carteira.creditar(100)
        pagamento = self.sistema.pagar_reserva(self.atleta, atingida)
        inicio = self.inicio + timedelta(minutes=30)
        atingidas, estornos = self.sistema.impacto_interdicao(self.admin, self.quadra, inicio, self.fim)
        self.assertEqual(atingidas, [atingida])
        self.assertEqual(estornos, Decimal("100"))
        self.assertEqual(atingida.status, StatusReserva.ATIVA)
        self.sistema.interditar_quadra(self.admin, self.quadra, inicio, self.fim, "Reparo")
        self.assertEqual(atingida.status, StatusReserva.CANCELADA)
        self.assertEqual(seguinte.status, StatusReserva.ATIVA)
        self.assertEqual(pagamento.status, StatusPagamento.ESTORNADO)
        self.assertEqual(self.atleta.carteira.saldo, 100)
        self.assertFalse(self.sistema.consultar_disponibilidade(self.quadra, inicio, self.fim))

    def test_reagendamento_financeiro_sem_ajustes_parciais(self):
        reserva = self.reservar()
        segundo = self.inscrever(reserva, 4)
        terceiro = self.inscrever(reserva, 5)
        self.atleta.carteira.creditar(100)
        segundo.carteira.creditar(Decimal("33.33"))
        primeiro_pago = self.registrar_pagamento_antigo(self.atleta, reserva, "33.34")
        segundo_pago = self.registrar_pagamento_antigo(segundo, reserva, "33.33")
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
        self.concluir_apos_horario(reserva)
        with patch("servicos.datetime") as relogio:
            relogio.now.return_value = reserva.fim + timedelta(seconds=1)
            self.assertEqual(self.sistema.pagar_reserva(terceiro, reserva, integral=False).valor, 30)

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

    def test_pedidos_reservam_unidades_sem_baixa_em_duplicidade(self):
        reserva = self.reservar()
        bola = Equipamento(1, "Bola", 3)
        pedir = self.sistema.solicitar_equipamento
        primeira = pedir(self.atleta, reserva, bola, 2)
        self.assertEqual(bola.quantidade_total, 3)
        self.sistema.fornecer_equipamento(self.supervisor, reserva, primeira)
        self.assertEqual(bola.quantidade_total, 1)
        with self.assertRaises(ValueError):
            pedir(self.atleta, reserva, bola, 2)
        ultima = pedir(self.atleta, reserva, bola, 1)
        ultima.cancelar()
        self.assertEqual(self.sistema.unidades_livres(self.quadra, bola, self.inicio, self.fim), 1)
        reserva.concluir()
        self.assertEqual(primeira.status, StatusSolicitacao.DEVOLVIDA)
        self.assertEqual(bola.quantidade_total, 3)
        with self.assertRaises(ValueError):
            primeira.devolver()

    def test_estoque_compartilhado_em_horarios_consecutivos(self):
        primeira, segunda = self.reservar(), self.reservar(1)
        bolas = Equipamento(1, "Bolas", 3)
        for reserva in (primeira, segunda):
            self.sistema.solicitar_equipamento(self.atleta, reserva, bolas, 2)
        livres = self.sistema.unidades_livres
        self.assertEqual(livres(self.quadra, bolas, primeira.inicio, segunda.fim), 1)
        outra = self.sistema.cadastrar_quadra(self.supervisor, "Anexa", "Futsal", 10, 100)
        self.sistema.definir_disponibilidade(self.supervisor, outra, self.quadra.agenda.faixas)
        paralela = self.sistema.criar_reserva(self.atleta, outra, self.inicio, self.fim)
        with self.assertRaises(ValueError):
            self.sistema.solicitar_equipamento(self.atleta, paralela, bolas, 2)
        self.sistema.solicitar_equipamento(self.atleta, paralela, bolas, 1)
        self.assertEqual(livres(outra, bolas, self.inicio, self.fim), 0)
        self.assertEqual(livres(outra, bolas, segunda.inicio, segunda.fim), 1)

    def test_reagendamento_soma_pedidos_do_mesmo_equipamento(self):
        reserva = self.reservar()
        bola = Equipamento(1, "Bola", 3)
        pedir = self.sistema.solicitar_equipamento
        pedir(self.atleta, reserva, bola, 1)
        extra = pedir(self.atleta, reserva, bola, 1)
        outra = self.sistema.cadastrar_quadra(self.supervisor, "Anexa", "Futsal", 10, 100)
        self.sistema.definir_disponibilidade(self.supervisor, outra, self.quadra.agenda.faixas)
        novo_fim = self.fim + timedelta(hours=1)
        paralela = self.sistema.criar_reserva(self.atleta, outra, self.fim, novo_fim)
        pedir(self.atleta, paralela, bola, 2)
        self.atleta.carteira.creditar(150)
        pagamento = self.sistema.pagar_reserva(self.atleta, reserva)
        self.sistema.definir_preco(self.supervisor, self.quadra, 120)
        with self.assertRaises(ValueError):
            self.sistema.reagendar_reserva(self.atleta, reserva, self.fim, novo_fim)
        self.assertEqual((reserva.inicio, reserva.fim), (self.inicio, self.fim))
        self.assertEqual((reserva.valor_total, pagamento.valor, self.atleta.carteira.saldo), (100, 100, 50))
        extra.cancelar()
        self.sistema.reagendar_reserva(self.atleta, reserva, self.fim, novo_fim)
        self.assertEqual((reserva.inicio, reserva.fim), (self.fim, novo_fim))

    def test_cota_da_quadra_e_supervisor_banido(self):
        reserva = self.reservar()
        bola = Equipamento(1, "Bola", 3)
        self.quadra.estoque_equipamentos[bola] = 1
        with self.assertRaises(ValueError):
            self.sistema.solicitar_equipamento(self.atleta, reserva, bola, 2)
        pedido = self.sistema.solicitar_equipamento(self.atleta, reserva, bola, 1)
        self.sistema.banir_usuario(self.admin, self.supervisor, "Teste")
        with self.assertRaises(PermissionError):
            self.sistema.fornecer_equipamento(self.supervisor, reserva, pedido)
        self.assertEqual(pedido.status, StatusSolicitacao.SOLICITADA)
        self.assertEqual(bola.quantidade_total, 3)

    def test_avaliacao_desativada(self):
        reserva = self.reservar()
        reserva.concluir()
        self.assertFalse(self.supervisor.tem_permissao("avaliar_atleta"))
        with self.assertRaises(PermissionError):
            self.sistema.avaliar_atleta(self.supervisor, self.atleta, reserva, 5, "Boa partida")
        self.assertEqual(self.sistema.avaliacoes, [])

    def test_supervisor_nao_denuncia_administrador(self):
        with self.assertRaises(PermissionError):
            self.sistema.registrar_denuncia(self.supervisor, self.admin, "Motivo")
        self.assertEqual(self.sistema.denuncias, [])
        primeira = self.sistema.registrar_denuncia(self.supervisor, self.atleta, "Motivo")
        segunda = self.sistema.registrar_denuncia(self.atleta, self.admin, "Outro motivo")
        self.assertEqual(self.sistema.denuncias, [primeira, segunda])

    def test_agenda_desconta_reservas_interdicoes_e_intervalos_fechados(self):
        dia = self.inicio.date()
        semana = dia.weekday()
        self.sistema.definir_disponibilidade(self.supervisor, self.quadra, [
            FaixaFuncionamento(semana, time(8), time(12)),
            FaixaFuncionamento(semana, time(11), time(13)),
            FaixaFuncionamento(semana, time(13), time(14)),
            FaixaFuncionamento(semana, time(15), time(18)),
        ])
        self.sistema.criar_reserva(self.atleta, self.quadra, datetime.combine(dia, time(9, 30)),
                                   datetime.combine(dia, time(10, 15)))
        self.sistema.interditar_quadra(self.supervisor, self.quadra, datetime.combine(dia, time(10, 15)),
                                       datetime.combine(dia, time(11, 45)), "Piso")
        self.sistema.interditar_quadra(self.supervisor, self.quadra, datetime.combine(dia, time(11, 30)),
                                       datetime.combine(dia, time(12, 15)), "Chuva")
        cancelada = self.sistema.criar_reserva(self.atleta, self.quadra, datetime.combine(dia, time(15)),
                                               datetime.combine(dia, time(16)))
        self.sistema.cancelar_reserva(self.atleta, cancelada)
        horarios = dict(self.sistema.consultar_agenda(self.quadra, dia))[dia]
        self.assertEqual(horarios, [(time(8), time(9, 30)), (time(12, 15), time(14)), (time(15), time(18))])
        for de, ate in horarios:
            self.assertTrue(self.sistema.consultar_disponibilidade(
                self.quadra, datetime.combine(dia, de), datetime.combine(dia, ate)))
        self.assertFalse(self.sistema.consultar_disponibilidade(
            self.quadra, datetime.combine(dia, time(13)), datetime.combine(dia, time(16))))

    def test_agenda_local_com_horarios_gravados_com_fuso(self):
        dia = self.inicio.date()
        self.sistema.criar_reserva(self.atleta, self.quadra, self.inicio.astimezone(), self.fim.astimezone())
        self.sistema.interditar_quadra(
            self.supervisor, self.quadra, self.fim.astimezone(timezone.utc),
            (self.fim + timedelta(hours=1)).astimezone(timezone.utc), "Reparo")
        horarios = dict(self.sistema.consultar_agenda(self.quadra, dia))[dia]
        self.assertEqual(horarios, [(time(8), time(10)), (time(12), time(22))])
        self.assertFalse(self.sistema.consultar_disponibilidade(self.quadra, self.inicio, self.fim))
        self.sistema.disponibilizar_quadra(self.supervisor, self.quadra)
        self.assertTrue(self.sistema.consultar_disponibilidade(
            self.quadra, self.fim, self.fim + timedelta(hours=1)))

    def test_agenda_padrao_sete_dias_e_periodo_personalizado(self):
        agora = self.inicio.replace(minute=12, second=30)
        hoje = agora.date()
        with patch("servicos.datetime", wraps=datetime) as relogio:
            relogio.now.return_value = agora
            semana = dict(self.sistema.consultar_agenda(self.quadra))
            self.assertEqual(list(semana), [hoje + timedelta(days=n) for n in range(7)])
            self.assertEqual(semana[hoje], [(time(10, 13), time(22))])
            self.assertEqual(semana[hoje + timedelta(days=1)], [])
            historico = dict(self.sistema.consultar_agenda(self.quadra, hoje - timedelta(days=7)))
            self.assertEqual(historico[hoje - timedelta(days=7)], [])
            dias = dict(self.sistema.consultar_agenda(self.quadra, hoje, hoje + timedelta(days=13)))
            self.assertEqual(len(dias), 14)
            self.assertEqual(dias[hoje + timedelta(days=7)], [(time(8), time(22))])
            with self.assertRaises(ValueError):
                list(self.sistema.consultar_agenda(self.quadra, hoje, hoje - timedelta(days=1)))
            self.quadra.desativar()
            self.assertEqual(dict(self.sistema.consultar_agenda(self.quadra, hoje))[hoje], [])

    def test_disponibilizar_encerra_interdicoes_apenas_da_quadra_escolhida(self):
        agora = datetime.now()
        reserva = self.reservar()
        self.atleta.carteira.creditar(100)
        self.sistema.pagar_reserva(self.atleta, reserva)
        antiga = self.sistema.interditar_quadra(self.admin, self.quadra, agora - timedelta(days=2),
                                                agora - timedelta(days=1), "Encerrada")
        atual = self.sistema.interditar_quadra(self.admin, self.quadra, agora - timedelta(hours=1),
                                               self.fim, "Em andamento")
        futura = self.sistema.interditar_quadra(self.admin, self.quadra, self.inicio, self.fim, "Agendada")
        del futura.liberado_em
        outra = self.sistema.cadastrar_quadra(self.supervisor, "Anexa", "Tênis", 4, 50)
        alheia = self.sistema.interditar_quadra(self.admin, outra, self.inicio, self.fim, "Chuva")
        with self.assertRaises(PermissionError):
            self.sistema.disponibilizar_quadra(self.atleta, self.quadra)
        self.assertFalse(self.sistema.consultar_disponibilidade(self.quadra, self.inicio, self.fim))
        self.sistema.disponibilizar_quadra(self.supervisor, self.quadra)
        self.assertTrue(self.sistema.consultar_disponibilidade(self.quadra, self.inicio, self.fim))
        self.assertEqual(antiga.fim_efetivo, antiga.fim)
        self.assertTrue(atual.sobrepoe(agora - timedelta(minutes=20), agora))
        self.assertFalse(futura.sobrepoe(self.inicio - timedelta(minutes=1), self.fim))
        self.assertTrue(alheia.sobrepoe(self.inicio, self.fim))
        self.assertEqual(reserva.status, StatusReserva.CANCELADA)
        self.assertEqual(self.atleta.carteira.saldo, 100)

    def test_dados_proprios_e_desativacao_com_historico(self):
        self.assertEqual(self.sistema.consultar_dados(self.supervisor, self.supervisor)["id"],
                         self.supervisor.id)
        with self.assertRaises(PermissionError):
            self.sistema.consultar_dados(self.supervisor, self.atleta)
        reserva = self.reservar()
        self.sistema.excluir_quadra(self.supervisor, self.quadra)
        self.assertFalse(self.quadra.ativa)
        self.assertIn(self.quadra, self.sistema.quadras)
        self.assertIn(reserva, self.sistema.reservas)
        self.sistema.disponibilizar_quadra(self.supervisor, self.quadra)
        self.assertTrue(self.quadra.ativa)

    def test_limite_de_cancelamento_e_interdicao(self):
        reserva = self.reservar()
        self.atleta.carteira.creditar(100)
        self.sistema.pagar_reserva(self.atleta, reserva)
        with patch("servicos.datetime", wraps=datetime) as relogio:
            relogio.now.return_value = self.inicio - timedelta(minutes=119)
            with self.assertRaises(ValueError):
                self.sistema.cancelar_reserva(self.atleta, reserva)
            self.assertEqual(reserva.status, StatusReserva.ATIVA)
            self.sistema.interditar_quadra(self.admin, self.quadra, self.inicio, self.fim, "Chuva")
        self.assertEqual(self.atleta.carteira.saldo, 100)
        self.assertEqual(reserva.status, StatusReserva.CANCELADA)

    def test_cancelamento_com_duas_horas_exatas(self):
        reserva = self.reservar()
        with patch("servicos.datetime", wraps=datetime) as relogio:
            relogio.now.return_value = self.inicio - timedelta(hours=2)
            self.sistema.cancelar_reserva(self.atleta, reserva)
        self.assertEqual(reserva.status, StatusReserva.CANCELADA)

    def test_metodo_contratado_antes_do_primeiro_debito(self):
        reserva = self.sistema.criar_reserva(self.atleta, self.quadra, self.inicio, self.fim, "rateado")
        self.atleta.carteira.creditar(100)
        with self.assertRaises(ValueError):
            self.sistema.pagar_reserva(self.atleta, reserva, integral=True)
        self.assertEqual(self.atleta.carteira.saldo, 100)
        self.assertFalse(reserva.partida.participantes_fechados)

    def test_convite_privado_lotacao_e_duplicidade(self):
        self.sistema.atualizar_quadra(self.supervisor, self.quadra, "Dupla", "Tênis", 2)
        reserva = self.reservar()
        convidada = Atleta(4, "Beatriz", "bia@teste")
        opcoes = self.sistema.consultar_opcoes_de_inscricao
        self.assertNotIn(reserva, opcoes(convidada))
        with self.assertRaises(PermissionError):
            self.sistema.participar_partida(convidada, reserva)
        self.sistema.autorizar_participante(self.atleta, reserva, convidada)
        self.assertIn(reserva, opcoes(convidada))
        self.sistema.participar_partida(convidada, reserva)
        self.sistema.definir_privacidade(self.atleta, reserva, True)
        self.assertNotIn(reserva.partida, self.sistema.consultar_partidas_publicas())
        with self.assertRaises(ValueError):
            self.sistema.participar_partida(convidada, reserva)
        self.assertEqual(reserva.partida.participantes, [self.atleta, convidada])

    def test_fornecimento_reconfere_estoque_no_periodo(self):
        reserva = self.reservar()
        bola = self.sistema.cadastrar_equipamento(self.supervisor, self.quadra, "Bola", 3)
        primeiro = self.sistema.solicitar_equipamento(self.atleta, reserva, bola, 2)
        segundo = self.sistema.solicitar_equipamento(self.atleta, reserva, bola, 1)
        bola.atualizar_quantidade(-1)
        with self.assertRaises(ValueError):
            self.sistema.fornecer_equipamento(self.supervisor, reserva, segundo)
        self.assertEqual(segundo.status, StatusSolicitacao.SOLICITADA)
        self.assertEqual(bola.quantidade_total, 2)
        primeiro.cancelar()
        self.sistema.fornecer_equipamento(self.supervisor, reserva, segundo)
        self.assertEqual(bola.quantidade_total, 1)


class TesteTerminal(unittest.TestCase):
    def test_interdicao_reabertura_reserva_e_denuncia_no_terminal(self):
        amanha = datetime.now().date() + timedelta(days=1)
        data = amanha.strftime("%d/%m/%Y")
        fim_da_quinzena = (amanha + timedelta(days=12)).strftime("%d/%m/%Y")
        outro_dia = (amanha + timedelta(days=20)).strftime("%d/%m/%Y")
        entradas = [
            "2", "bia@demo", "quadra",
            "14", "1", "14", "3", "Conduta em quadra",
            "5", "1", data, "09:00", "", "10:30", "Manutenção",
            "6", "amanhã", "14 dias", f"{outro_dia} a {outro_dia}", "",
            "8", "1", "6", "amanhã", "", "0",
            "2", "ana@demo", "quadra",
            "1", "amanhã", "14 dias", data, "09:00", "10:30", "1", "0", "0",
        ]
        resultado = subprocess.run(
            [sys.executable, "-c", "from main import executar_sistema; executar_sistema(simular=True)"],
            cwd=Path(__file__).parent,
            input="\n".join(entradas) + "\n", capture_output=True, encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=30, check=True,
        )
        saida = resultado.stdout
        self.assertNotIn("1 - Admin (Administrador)", saida)
        self.assertIn("3 - Ana (Atleta)", saida)
        self.assertEqual(saida.count("Operação recusada"), 1)
        self.assertIn("Escolha um ID da lista.", saida)
        self.assertIn("Denúncia 1 registrada.", saida)
        self.assertIn("próximos 7 dias", saida)
        self.assertIn("Dia ou período: ", saida)
        self.assertIn("Início ou nova consulta: ", saida)
        self.assertNotIn("Enter para voltar", saida)
        self.assertNotIn("Para reservar, escolha", saida)
        antes, depois = saida.split("Central disponível.")
        self.assertIn("08:00–09:00 | 10:30–18:00 | 19:00–22:00", antes)
        self.assertIn(fim_da_quinzena, antes)
        self.assertIn(outro_dia, antes)
        self.assertIn("08:00–18:00 | 19:00–22:00", depois)
        self.assertIn("Reserva 3 confirmada para Ana em Central.", depois)

    def test_apresentacao_interativa_dos_tres_perfis(self):
        entradas = [
            "2", "leo@demo", "quadra", "10", "2", "0",
            "2", "ana@demo", "quadra", "12", "2", "1", "1", "0",
            "2", "bia@demo", "quadra", "12", "2", "1", "15", "0",
            "2", "admin@demo", "quadra", "6", "2", "1", "0", "0",
        ]
        with tempfile.TemporaryDirectory() as pasta:
            p = subprocess.run([sys.executable, "-c", "from main import executar_sistema; executar_sistema(simular=True)"],
                               cwd=Path(__file__).parent,
                               input="\n".join(entradas) + "\n", capture_output=True,
                               encoding="utf-8", timeout=30, check=True,
                               env={**os.environ, "LOCALAPPDATA": pasta, "PYTHONIOENCODING": "utf-8"})
            self.assertNotIn("Operação recusada", p.stdout)
            self.assertIn("Léo entrou na partida", p.stdout)
            self.assertIn("Material fornecido: 1 x Bola.", p.stdout)
            self.assertNotIn("Avaliar atleta", p.stdout)
            self.assertIn("Repasse 1: R$ 100.00", p.stdout)
            self.assertFalse(list(Path(pasta).rglob("*.sqlite3")))

    def test_cadastro_login_reserva_e_reabertura(self):
        data = (datetime.now() + timedelta(days=2)).strftime("%d/%m/%Y")
        with tempfile.TemporaryDirectory() as pasta:
            def executar(linhas):
                resultado = subprocess.run(
                    [sys.executable, str(Path(__file__).with_name("main.py"))],
                    input="\n".join(["1", *linhas]) + "\n", capture_output=True,
                    encoding="utf-8", timeout=30, check=True,
                    env={**os.environ, "LOCALAPPDATA": pasta, "PYTHONIOENCODING": "utf-8"},
                )
                return resultado.stdout

            saida = executar([
                "Admin", "admin@teste", "senha-a", "senha-a",
                "2", "admin@teste", "senha-errada",
                "2", "admin@teste", "senha-a", "1", "Supervisor", "sup@teste", "senha-s", "senha-s", "0",
                "2", "sup@teste", "senha-s", "1", "Central", "Futsal", "10", "100",
                "1 2 3 4 5 6 7", "08:00", "22:00", "0",
                "1", "Atleta", "atleta@teste", "senha-t", "senha-t",
                "2", "atleta@teste", "senha-t", "1", data, "19:00", "20:00", "1",
                "4", "150", "s", "5", "1", "0", "0",
            ])
            self.assertIn("Cadastro do administrador", saida)
            self.assertIn("E-mail ou senha inválidos", saida)
            self.assertIn("Reserva 1 confirmada", saida)
            self.assertIn("Pagamento confirmado", saida)
            saida = executar(["2", "atleta@teste", "senha-t", "2", "3", "1", "0", "0"])
            self.assertIn("1 - Central", saida)
            self.assertIn("Saldo: R$ 50.00", saida)
            self.assertIn("Reserva cancelada.", saida)
            self.assertIn("Saldo: R$ 150.00", saida)
            self.assertNotIn("Cadastro do administrador", saida)


class TesteInterfaceGrafica(unittest.TestCase):
    def test_login_perfis_e_reserva_pelos_botoes(self):
        try:
            import tkinter as tk
            from tkinter import ttk
        except ImportError:
            self.skipTest("Tkinter indisponível.")
        try:
            janela = tk.Tk()
        except tk.TclError as erro:
            self.skipTest(f"Ambiente sem janela Tk disponível: {erro}")
        self.addCleanup(janela.destroy)
        janela.withdraw()

        from armazenamento import carregar
        from interface import InterfaceReservas
        from main import banco_da_sessao

        def descendentes(pai, tipo):
            for filho in pai.winfo_children():
                if isinstance(filho, tipo):
                    yield filho
                yield from descendentes(filho, tipo)

        def botoes(pai):
            return {b.cget("text"): b for b in descendentes(pai, ttk.Button)}

        def preencher(pai, valores):
            campos = [c for c in descendentes(pai, ttk.Entry) if not isinstance(c, ttk.Combobox)]
            self.assertEqual(len(campos), len(valores))
            for campo, valor in zip(campos, valores):
                campo.delete(0, tk.END)
                campo.insert(0, valor)

        with banco_da_sessao(simular=True) as banco, patch("tkinter.messagebox.showerror") as aviso:
            tela = InterfaceReservas(janela, banco, simular=True)
            preencher(janela, ["ana@demo", "errada"])
            botoes(janela)["Entrar"].invoke()
            aviso.assert_called_once()
            self.assertIsNone(tela.conta_id)
            aviso.reset_mock()
            preencher(janela, ["ANA@DEMO", "quadra"])
            botoes(janela)["Entrar"].invoke()
            self.assertNotIn("Cadastrar quadra", botoes(janela))
            self.assertNotIn("Usuários", botoes(janela))
            self.assertEqual(tela.registros.get(0), "Central")
            hoje = datetime.now().date()
            with patch("servicos.datetime", wraps=datetime) as relogio:
                relogio.now.return_value = datetime.combine(hoje, time(14, 37))
                tela.form_reserva(1, hoje)
                seletor = next(descendentes(tela.corpo, ttk.Combobox))
                self.assertEqual(seletor.cget("values"), tuple(f"{h}:00" for h in range(15, 22)))
                preencher(tela.corpo, ["2"])
                self.assertEqual(seletor.cget("values")[-1], "20:00")
                preencher(tela.corpo, ["1,5"])
                self.assertFalse(seletor.cget("values"))
                botoes(tela.corpo)["Voltar"].invoke()

            botoes(janela)["Reservar"].invoke()
            from interface import Calendario
            formulario = tela.corpo
            calendario = next(descendentes(formulario, Calendario))
            dia = calendario.dia
            botoes(calendario)[str(dia.day)].invoke()
            horas = list(descendentes(formulario, ttk.Combobox))[0]
            self.assertNotIn("18:30", horas.cget("values"))
            self.assertIn("19:00", horas.cget("values"))
            self.assertTrue(all(h.endswith(":00") for h in horas.cget("values")))
            horas.set("18:30")
            botoes(formulario)["Confirmar reserva"].invoke()
            aviso.assert_called_once()
            self.assertIn("horário", str(aviso.call_args.args[1]).casefold())
            self.assertEqual(len(carregar(banco)[1].reservas), 2)

            horas.set("19:00")
            preencher(formulario, ["2"])
            botoes(formulario)["Confirmar reserva"].invoke()
            aviso.assert_called_once()
            _, sistema = carregar(banco)
            self.assertEqual(len(sistema.reservas), 3)
            nova = sistema.reservas[-1]
            self.assertEqual((nova.responsavel.nome, nova.quadra.nome, nova.valor_total),
                             ("Ana", "Central", Decimal("200.00")))
            self.assertEqual(tela.pagina, "Reservas")
            self.assertEqual(tela.selecionado("uma reserva"), nova.id)
            self.assertEqual(nova.fim - nova.inicio, timedelta(hours=2))
            botoes(janela)["Reagendar"].invoke()
            list(descendentes(tela.corpo, ttk.Combobox))[0].set("20:00")
            botoes(tela.corpo)["Confirmar reagendamento"].invoke()
            reagendada = carregar(banco)[1].reservas[-1]
            self.assertEqual(reagendada.inicio.hour, 20)
            self.assertEqual(reagendada.fim.hour, 22)

            botoes(janela)["Sair da conta"].invoke()
            preencher(janela, ["bia@demo", "quadra"])
            botoes(janela)["Entrar"].invoke()
            self.assertEqual(tela.pagina, "Hoje")
            botoes(janela)["Quadras"].invoke()
            self.assertIn("Cadastrar quadra", botoes(janela))
            self.assertNotIn("Reservar", botoes(janela))

            botoes(janela)["Sair da conta"].invoke()
            preencher(janela, ["leo@demo", "quadra"])
            botoes(janela)["Entrar"].invoke()
            botoes(janela)["Partidas"].invoke()
            self.assertEqual(tuple(tela.itens), (2,))
            botoes(janela)["Entrar na partida"].invoke()
            botoes(janela)["Carteira"].invoke()
            self.assertEqual(tela.usuario.carteira.saldo, Decimal("250"))
            botoes(janela)["Reservas"].invoke()
            self.assertTrue(botoes(janela)["Pagar"].instate(["disabled"]))

            reserva = carregar(banco)[1].reservas[1]
            depois = reserva.fim + timedelta(seconds=1)
            botoes(janela)["Sair da conta"].invoke()
            botoes(janela)["Bia"].invoke()
            with patch("servicos.datetime") as servico, patch("interface.datetime") as tela_relogio:
                servico.now.return_value = tela_relogio.now.return_value = depois
                botoes(janela)["Reservas"].invoke()
                tela.registros.selection_clear(0, "end")
                tela.registros.selection_set(tuple(tela.itens).index(2))
                janela.deiconify()
                janela.update()
                tela.registros.event_generate("<<ListboxSelect>>")
                janela.update()
                with patch("tkinter.messagebox.askyesno", return_value=True):
                    botoes(janela)["Concluir"].invoke()
            self.assertEqual(carregar(banco)[1].reservas[1].status, StatusReserva.CONCLUIDA)

            botoes(janela)["Sair da conta"].invoke()
            botoes(janela)["Léo"].invoke()
            botoes(janela)["Reservas"].invoke()
            with patch("servicos.datetime") as relogio, patch("tkinter.messagebox.askyesno", return_value=True):
                relogio.now.return_value = depois
                botoes(janela)["Pagar"].invoke()
            _, sistema = carregar(banco)
            leo = next(u for u in sistema.usuarios if u.email == "leo@demo")
            self.assertEqual(leo.carteira.saldo, Decimal("200"))
            self.assertIn(leo, sistema.reservas[1].partida.participantes)
            self.assertEqual(sistema.pagamentos[-1].pagador, leo)
            self.assertEqual(sistema.pagamentos[-1].valor, Decimal("50"))

            botoes(janela)["Sair da conta"].invoke()
            botoes(janela)["Admin"].invoke()
            botoes(janela)["Repasses"].invoke()
            self.assertEqual(tuple(tela.itens), (1,))
            with patch("tkinter.messagebox.askyesno", return_value=True):
                botoes(janela)["Efetuar repasse"].invoke()
            self.assertEqual(carregar(banco)[1].repasses[-1].valor, Decimal("100"))
            self.assertNotIn("Efetuar repasse", botoes(janela))
            botoes(janela)["Histórico"].invoke()
            self.assertIn("Bia", tela.registros.get(0))
            botoes(janela)["Usuários"].invoke()
            preencher(tela.corpo, ["leo@demo"])
            self.assertEqual(tuple(tela.itens), (4,))
            botoes(janela)["Banir conta"].invoke()
            preencher(tela.corpo, ["Teste de confirmação"])
            with patch("tkinter.messagebox.askyesno", return_value=False):
                botoes(janela)["Salvar"].invoke()
            self.assertFalse(carregar(banco)[1].usuarios[3].banido)

    def test_entradas_da_simulacao_abrem_janela(self):
        import runpy
        from unittest.mock import Mock
        janela = Mock()
        modulo = Mock(abrir_janela=janela)
        for argumentos, entradas in [(["--simular"], []), (["--gui", "--simular"], []), ([], ["2"])]:
            janela.reset_mock()
            with self.subTest(argumentos=argumentos), patch.dict(sys.modules, {"interface": modulo}), patch.object(
                sys, "argv", ["main.py", *argumentos]
            ), patch("builtins.input", side_effect=entradas):
                runpy.run_path(str(Path(__file__).with_name("main.py")), run_name="__main__")
            janela.assert_called_once()
            self.assertTrue(janela.call_args.args[1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
