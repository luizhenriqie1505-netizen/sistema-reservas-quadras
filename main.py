
from datetime import datetime, timedelta, time
from decimal import Decimal

from modelos import Administrador, Atleta, FaixaFuncionamento
from servicos import SistemaReservas


def executar_sistema():

    print("=" * 45)
    print("       SISTEMA DE RESERVAS DE QUADRAS")
    print("=" * 45)

    sistema = SistemaReservas()

    # 1. Criar administrador
    administrador = Administrador(
        1, "Carlos Administrador", "admin@email.com"
    )

    print("\n[1] Administrador criado!")

    # 2. Cadastrar supervisor
    supervisor = sistema.cadastrar_supervisor(
        administrador,
        "João Supervisor",
        "joao@email.com"
    )

    print("[2] Supervisor cadastrado!")

    # 3. Cadastrar atleta
    atleta = Atleta(
        3, "Luiz, joão e Rodrigo", "luiz@email.com"
    )

    sistema.usuarios.append(atleta)

    print("[3] Atleta cadastrado!")

    # 4. Cadastrar quadra
    quadra = sistema.cadastrar_quadra(
        supervisor,
        "Quadra Central",
        "Futset",
        20,
        Decimal("100.00")
    )

    print("[4] Quadra cadastrada!")

    # 5. Configurar funcionamento
    inicio = (datetime.now() + timedelta(days=1)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )

    fim = inicio + timedelta(hours=1)

    faixa = FaixaFuncionamento(
        inicio.weekday(),
        time(8, 0),
        time(22, 0)
    )

    sistema.definir_disponibilidade(
        supervisor, quadra, [faixa]
    )

    print("[5] Horário de funcionamento configurado!")

    # 6. Criar reserva
    reserva = sistema.criar_reserva(
        atleta, quadra, inicio, fim
    )

    print("[6] Reserva criada!")
    print("Valor:", reserva.valor_total)

    # 7. Tornar a partida pública
    sistema.definir_privacidade(
        atleta, reserva, True
    )

    print("[7] Partida agora é pública!")

    # 8. Comprar créditos
    compra = sistema.comprar_creditos(
        atleta, Decimal("200.00")
    )

    compra.confirmar()

    print("[8] Créditos adicionados!")
    print("Saldo:", atleta.carteira.saldo)

    # 9. Efetuar pagamento
    pagamento = sistema.pagar_reserva(
        atleta, reserva
    )

    print("[9] Pagamento realizado!")
    print("Status:", pagamento.status.value)

    # 10. Consultar dados
    print("\n" + "=" * 45)
    print("             RESULTADO FINAL")
    print("=" * 45)

    print("Atleta:", atleta.nome)
    print("Quadra:", quadra.nome)
    print("Modalidade:", quadra.modalidade)
    print("Início:", inicio.strftime("%d/%m/%Y %H:%M"))
    print("Fim:", fim.strftime("%H:%M"))
    print("Valor da reserva: R$", reserva.valor_total)
    print("Pagamento:", pagamento.status.value)
    print("Saldo restante: R$", atleta.carteira.saldo)

    print("\nSISTEMA EXECUTADO COM SUCESSO!")


if __name__ == "__main__":
    executar_sistema()
