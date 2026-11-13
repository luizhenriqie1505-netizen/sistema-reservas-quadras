
import unittest
from datetime import datetime, timedelta, time
from decimal import Decimal

from modelos import (
    Usuario, Administrador, Supervisor, Atleta,
    Quadra, FaixaFuncionamento, Carteira
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
