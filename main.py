import sys
from contextlib import closing
from getpass import getpass
from datetime import datetime, timedelta, time
from decimal import Decimal, InvalidOperation

from armazenamento import abrir_banco, autenticar, carregar, definir_senha, salvar, serializar
from enums import StatusReserva, StatusSolicitacao
from modelos import Administrador, Atleta, FaixaFuncionamento, Reserva, Supervisor


class SelecaoCancelada(Exception):
    """O usuário escolheu voltar à tela anterior."""


def texto(pergunta):
    resposta = input(pergunta).strip()
    if not resposta:
        raise ValueError("Preencha o campo.")
    return resposta


def valor_monetario(pergunta):
    valor = Decimal(texto(pergunta).replace(",", "."))
    if not valor.is_finite() or valor < 0:
        raise ValueError("Informe um valor monetário válido.")
    return valor


def ler_senha(mensagem):
    if sys.stdin.isatty():
        return getpass(mensagem)
    return input(mensagem)


def dados_de_cadastro(sistema):
    nome = texto("Nome: ")
    email = texto("E-mail: ").casefold()
    if any(u.email.casefold() == email for u in sistema.usuarios):
        raise ValueError("E-mail já cadastrado.")
    senha = ler_senha("Senha: ")
    if not senha.strip() or senha != ler_senha("Confirme a senha: "):
        raise ValueError("Informe uma senha e repita a mesma senha na confirmação.")
    return nome, email, senha


def periodo(varios_dias=False):
    data = datetime.strptime(texto("Data (DD/MM/AAAA): "), "%d/%m/%Y").date()
    inicio = datetime.strptime(texto("Início (HH:MM): "), "%H:%M").time()
    data_final = data
    if varios_dias:
        outra_data = input("Data final (Enter para o mesmo dia): ").strip()
        if outra_data:
            data_final = datetime.strptime(outra_data, "%d/%m/%Y").date()
    fim = datetime.strptime(texto("Fim (HH:MM): "), "%H:%M").time()
    inicio = datetime.combine(data, inicio)
    fim = datetime.combine(data_final, fim)
    if fim <= inicio:
        raise ValueError("O fim deve ser posterior ao início.")
    return inicio, fim


def ler_faixas():
    dias = texto("Dias da semana (1=seg, 7=dom, separados por espaço): ")
    dias = sorted({int(dia) for dia in dias.split()})
    if any(dia < 1 or dia > 7 for dia in dias):
        raise ValueError("Use os números de 1 a 7.")
    abertura = datetime.strptime(texto("Abertura (HH:MM): "), "%H:%M").time()
    fechamento = datetime.strptime(texto("Fechamento (HH:MM): "), "%H:%M").time()
    return [FaixaFuncionamento(dia - 1, abertura, fechamento) for dia in dias]


def cadastrar_quadra(sistema, supervisor):
    nome = texto("Nome da quadra: ")
    modalidade = texto("Modalidade: ")
    capacidade = int(texto("Capacidade: "))
    if capacidade < 1:
        raise ValueError("A capacidade deve ser positiva.")
    preco = valor_monetario("Preço por hora (R$): ")
    faixas = ler_faixas()
    quadra = sistema.cadastrar_quadra(supervisor, nome, modalidade, capacidade, preco)
    sistema.definir_disponibilidade(supervisor, quadra, faixas)
    return f"Quadra cadastrada: {quadra.nome}."


def consultar_e_reservar(sistema, atleta):
    if not sistema.consultar_quadras():
        print("Ainda não há quadras cadastradas.")
        return
    inicio, fim = periodo()
    livres = [q for q in sistema.consultar_quadras()
              if sistema.consultar_disponibilidade(q, inicio, fim)]
    if not livres:
        print("Nenhuma quadra livre nesse período.")
        return
    for quadra in livres:
        total = quadra.calcular_valor(inicio, fim)
        print(f"{quadra.id} - {quadra.nome} ({quadra.modalidade}), total R$ {total:.2f}")
    escolha = int(texto("ID da quadra para reservar (0 para voltar): "))
    if escolha == 0:
        return
    quadra = next((q for q in livres if q.id == escolha), None)
    if quadra is None:
        raise ValueError("Escolha uma quadra da lista.")
    modos = {"1": "integral", "2": "rateado"}
    modo = modos.get(texto("Método de pagamento: 1 - Integral, 2 - Rateado: "))
    if modo is None:
        raise ValueError("Escolha 1 ou 2.")
    reserva = sistema.criar_reserva(atleta, quadra, inicio, fim, modo)
    return f"Reserva {reserva.id} confirmada para {atleta.nome} em {quadra.nome}."


def descricao_reserva(reserva):
    privacidade = "pública" if reserva.partida.publica else "privada"
    inscritos = len(reserva.partida.participantes)
    capacidade = reserva.partida.limite_participantes
    metodo = reserva.metodo_pagamento or "a definir"
    return (f"{reserva.quadra.nome}, {reserva.inicio:%d/%m/%Y %H:%M} às {reserva.fim:%H:%M}, "
            f"{reserva.status.value}, R$ {reserva.valor_total:.2f} ({metodo}), "
            f"partida {privacidade}, {inscritos}/{capacidade} inscritos")


def selecionar(itens, descricao, pergunta="ID"):
    por_id = {item.id: item for item in itens}
    if not por_id:
        raise ValueError("Nenhuma opção disponível.")
    for chave, item in por_id.items():
        print(f"{chave} - {descricao(item)}")
    chave = int(texto(f"{pergunta} (0 para voltar): "))
    if chave == 0:
        raise SelecaoCancelada()
    if chave not in por_id:
        raise ValueError("Escolha um ID da lista.")
    return por_id[chave]


def minhas_reservas(sistema, usuario):
    partidas = sistema.consultar_partidas(usuario)
    return [reserva for reserva in sistema.reservas if reserva.partida in partidas]


def mostrar_reservas(reservas):
    if not reservas:
        print("Nenhuma reserva nesta lista.")
    for reserva in reservas:
        print(f"{reserva.id} - {descricao_reserva(reserva)}")


def minhas_partidas(sistema, usuario):
    reservas = minhas_reservas(sistema, usuario)
    if not reservas:
        return "Nenhuma partida neste perfil."
    for reserva in reservas:
        print(f"{reserva.id} - {descricao_reserva(reserva)}")
        print("Participantes:", ", ".join(atleta.nome for atleta in reserva.partida.participantes))
        for pedido in reserva.solicitacoes:
            print(f"  Material: {pedido.quantidade} x {pedido.equipamento.nome}, {pedido.status.value}")


def escolher_quadra(sistema, usuario):
    quadras = [quadra for quadra in sistema.consultar_quadras()
               if isinstance(usuario, Administrador) or quadra.supervisor == usuario]
    return selecionar(quadras, lambda q: f"{q.nome} ({'ativa' if q.ativa else 'inativa'})")


def escolher_reserva(sistema, usuario, participante=False):
    candidatas = minhas_reservas(sistema, usuario)
    if isinstance(usuario, Atleta) and not participante:
        candidatas = [reserva for reserva in candidatas if reserva.responsavel == usuario]
    return selecionar(candidatas, descricao_reserva)


def cadastro_supervisor(sistema, admin):
    nome, email, senha = dados_de_cadastro(sistema)
    supervisor = sistema.cadastrar_supervisor(admin, nome, email)
    definir_senha(supervisor, senha)
    return f"Supervisor cadastrado: {nome}."


def denunciar(sistema, autor):
    alvo = selecionar((pessoa for pessoa in sistema.usuarios if pessoa != autor), lambda pessoa: pessoa.nome)
    denuncia = sistema.registrar_denuncia(autor, alvo, texto("Motivo: "))
    return f"Denúncia {denuncia.id} registrada."


def dados(sistema, autor):
    alvo = autor
    if isinstance(autor, Administrador):
        alvo = selecionar(sistema.usuarios, lambda pessoa: pessoa.nome)
    for campo, valor in sistema.consultar_dados(autor, alvo).items():
        print(f"{campo}: {valor}")


def banir(sistema, admin):
    alvos = [pessoa for pessoa in sistema.usuarios if isinstance(pessoa, (Supervisor, Atleta))]
    alvo = selecionar(alvos, lambda pessoa: f"{pessoa.nome} ({type(pessoa).__name__})")
    sistema.banir_usuario(admin, alvo, texto("Justificativa: "))
    return f"Conta de {alvo.nome} banida. Histórico preservado."


def interditar(sistema, autor):
    quadra = escolher_quadra(sistema, autor)
    inicio, fim = periodo(varios_dias=True)
    sistema.interditar_quadra(autor, quadra, inicio, fim, texto("Motivo: "))
    return f"{quadra.nome} interditada de {inicio:%d/%m %H:%M} a {fim:%d/%m %H:%M}."


def repassar(sistema, admin):
    supervisores = [pessoa for pessoa in sistema.usuarios if isinstance(pessoa, Supervisor)]
    supervisor = selecionar(supervisores, lambda pessoa: pessoa.nome)
    reservas = {r.id: r for r in sistema.reservas if r.quadra.supervisor == supervisor}
    mostrar_reservas(list(reservas.values()))
    if not reservas:
        return
    ids = [int(item) for item in texto("IDs das reservas do lote, separados por espaço: ").split()]
    if any(chave not in reservas for chave in ids):
        raise ValueError("O lote possui reserva inválida.")
    lote = [reservas[chave] for chave in ids]
    repasse = sistema.efetuar_repasse(admin, supervisor, lote)
    return f"Repasse {repasse.id}: R$ {repasse.valor:.2f}."


def cancelar(sistema, autor):
    reserva = escolher_reserva(sistema, autor)
    sistema.cancelar_reserva(autor, reserva)
    return "Reserva cancelada."


def reagendar(sistema, atleta):
    reserva = escolher_reserva(sistema, atleta)
    inicio, fim = periodo()
    sistema.reagendar_reserva(atleta, reserva, inicio, fim)
    return f"Reserva reagendada: {descricao_reserva(reserva)}."


def disponibilidade(sistema, supervisor):
    quadra = escolher_quadra(sistema, supervisor)
    if sistema.consultar_disponibilidade(quadra, *periodo()):
        return "Quadra disponível nesse período."
    return "Quadra indisponível nesse período."


def atualizar_quadra(sistema, supervisor):
    quadra = escolher_quadra(sistema, supervisor)
    nome, modalidade = texto("Nome: "), texto("Modalidade: ")
    capacidade = int(texto("Capacidade: "))
    sistema.atualizar_quadra(supervisor, quadra, nome, modalidade, capacidade)
    return f"Cadastro de {quadra.nome} atualizado."


def alterar_preco(sistema, supervisor):
    quadra = escolher_quadra(sistema, supervisor)
    sistema.definir_preco(supervisor, quadra, valor_monetario("Novo preço por hora: "))
    return f"{quadra.nome}: R$ {quadra.valor_hora:.2f} por hora para novas reservas."


def definir_funcionamento(sistema, supervisor):
    quadra = escolher_quadra(sistema, supervisor)
    for faixa in quadra.agenda.faixas:
        print(f"Dia {faixa.dia_semana + 1}: {faixa.abertura:%H:%M} às {faixa.fechamento:%H:%M}")
    acao = texto("1 - Acrescentar faixas, 2 - Substituir o funcionamento: ")
    if acao not in ("1", "2"):
        raise ValueError("Escolha 1 ou 2.")
    faixas = ler_faixas()
    if acao == "1":
        faixas = quadra.agenda.faixas + faixas
    sistema.definir_disponibilidade(supervisor, quadra, faixas)
    return "Funcionamento atualizado."


def disponibilizar(sistema, supervisor):
    quadra = escolher_quadra(sistema, supervisor)
    sistema.disponibilizar_quadra(supervisor, quadra)
    return f"{quadra.nome} está ativa."


def excluir_quadra(sistema, supervisor):
    quadra = escolher_quadra(sistema, supervisor)
    sistema.excluir_quadra(supervisor, quadra)
    if quadra in sistema.quadras:
        return "Quadra desativada. O histórico de reservas foi preservado."
    return "Quadra excluída."


def cadastrar_material(sistema, supervisor):
    quadra = escolher_quadra(sistema, supervisor)
    nome = texto("Nome do material: ")
    quantidade = int(texto("Unidades: "))
    sistema.cadastrar_equipamento(supervisor, quadra, nome, quantidade)
    return f"Estoque de {quadra.nome}: {quantidade} x {nome} cadastrado."


def concluir(sistema, supervisor):
    reserva = escolher_reserva(sistema, supervisor)
    sistema.concluir_reserva(supervisor, reserva)
    return f"Reserva {reserva.id} concluída."


def avaliar(sistema, supervisor):
    concluidas = [r for r in minhas_reservas(sistema, supervisor) if r.status == StatusReserva.CONCLUIDA]
    reserva = selecionar(concluidas, descricao_reserva)
    atleta = selecionar(reserva.partida.participantes, lambda pessoa: pessoa.nome)
    nota = int(texto("Nota de 1 a 5: "))
    sistema.avaliar_atleta(supervisor, atleta, reserva, nota, input("Comentário: "))
    return f"Avaliação registrada para {atleta.nome}: {nota}/5."


def fornecer(sistema, supervisor):
    reserva = escolher_reserva(sistema, supervisor)
    pendentes = [p for p in reserva.solicitacoes if p.status == StatusSolicitacao.SOLICITADA]
    pedido = selecionar(pendentes, lambda p: f"{p.quantidade} x {p.equipamento.nome}")
    sistema.fornecer_equipamento(supervisor, reserva, pedido)
    return f"Material fornecido: {pedido.quantidade} x {pedido.equipamento.nome}."


def comprar(sistema, atleta):
    valor = valor_monetario("Valor dos créditos (R$): ")
    compra = sistema.comprar_creditos(atleta, valor)
    confirmacao = texto("Confirmar pagamento simulado? (s/n): ").casefold()
    if confirmacao == "s":
        compra.confirmar()
        return "Créditos adicionados."
    if confirmacao == "n":
        compra.cancelar()
        return "Compra cancelada."
    raise ValueError("Responda s ou n.")


def pagar(sistema, atleta):
    reserva = escolher_reserva(sistema, atleta, participante=True)
    modo = reserva.metodo_pagamento
    if modo is None:  # Reservas anteriores à escolha do método no cadastro.
        modo = texto("Método (integral/rateado): ").lower()
        if modo not in ("integral", "rateado"):
            raise ValueError("Método inválido.")
    pagamento = sistema.pagar_reserva(atleta, reserva, integral=modo == "integral")
    return f"Pagamento confirmado: R$ {pagamento.valor:.2f}."


def rateio(sistema, atleta):
    reserva = escolher_reserva(sistema, atleta, participante=True)
    parcelas = sistema.calcular_rateio(reserva)
    for participante in reserva.partida.participantes:
        print(f"{participante.nome} (ID {participante.id}): R$ {parcelas[participante.id]:.2f}")


def privacidade(sistema, atleta):
    reserva = escolher_reserva(sistema, atleta)
    escolha = texto("1 - Pública, 2 - Privada: ")
    if escolha not in ("1", "2"):
        raise ValueError("Escolha 1 ou 2.")
    sistema.definir_privacidade(atleta, reserva, escolha == "1")
    return "Privacidade atualizada."


def convidar(sistema, responsavel):
    reserva = escolher_reserva(sistema, responsavel)
    candidatos = [p for p in sistema.usuarios if isinstance(p, Atleta) and not p.banido
                  and p not in reserva.partida.participantes and p not in reserva.partida.autorizados]
    atleta = selecionar(candidatos, lambda pessoa: pessoa.nome)
    sistema.autorizar_participante(responsavel, reserva, atleta)
    return f"{atleta.nome} poderá usar a opção ‘Entrar em partida ou aceitar convite’."


def listar_publicas(sistema, atleta):
    publicas = sistema.consultar_partidas_publicas()
    mostrar_reservas([r for r in sistema.reservas if r.partida in publicas])


def participar(sistema, atleta):
    reserva = selecionar(sistema.consultar_opcoes_de_inscricao(atleta), descricao_reserva)
    sistema.participar_partida(atleta, reserva)
    return f"{atleta.nome} entrou na partida da reserva {reserva.id}."


def solicitar(sistema, atleta):
    reserva = escolher_reserva(sistema, atleta)
    equipamento = selecionar(reserva.quadra.equipamentos, lambda item: item.nome)
    quantidade = int(texto("Quantidade: "))
    pedido = sistema.solicitar_equipamento(atleta, reserva, equipamento, quantidade)
    return f"Pedido {pedido.id} registrado: {quantidade} x {equipamento.nome}."


# Cada opção chama o mesmo serviço usado nos testes, com o usuário autenticado.
MENUS = {
    Administrador: (
        ("Cadastrar supervisor", cadastro_supervisor),
        ("Consultar dados cadastrais", dados),
        ("Registrar denúncia", denunciar),
        ("Banir atleta ou supervisor", banir),
        ("Interditar quadra", interditar),
        ("Pagar supervisor por lote", repassar),
    ),
    Supervisor: (
        ("Cadastrar quadra e funcionamento", cadastrar_quadra),
        ("Consultar partidas e reservas", minhas_partidas),
        ("Cancelar reserva", cancelar),
        ("Alterar preço da quadra", alterar_preco),
        ("Interditar quadra", interditar),
        ("Consultar disponibilidade", disponibilidade),
        ("Definir funcionamento", definir_funcionamento),
        ("Disponibilizar quadra", disponibilizar),
        ("Atualizar cadastro da quadra", atualizar_quadra),
        ("Excluir quadra ou desativar se houver histórico", excluir_quadra),
        ("Cadastrar equipamento", cadastrar_material),
        ("Fornecer equipamento", fornecer),
        ("Concluir reserva encerrada", concluir),
        ("Avaliar atleta", avaliar),
        ("Registrar denúncia", denunciar),
        ("Meus dados", dados),
    ),
    Atleta: (
        ("Consultar disponibilidade e reservar", consultar_e_reservar),
        ("Minhas reservas e partidas", minhas_partidas),
        ("Cancelar reserva", cancelar),
        ("Comprar créditos", comprar),
        ("Pagar reserva", pagar),
        ("Reagendar", reagendar),
        ("Definir privacidade", privacidade),
        ("Convidar atleta", convidar),
        ("Consultar partidas públicas", listar_publicas),
        ("Entrar em partida ou aceitar convite", participar),
        ("Calcular rateio", rateio),
        ("Solicitar equipamento", solicitar),
        ("Registrar denúncia", denunciar),
        ("Meus dados", dados),
    ),
}


def menu_do_perfil(sistema, usuario):
    print(f"\n{type(usuario).__name__}: {usuario.nome}")
    if isinstance(usuario, Atleta):
        print(f"Saldo: R$ {usuario.carteira.saldo:.2f}")
    acoes = MENUS[type(usuario)]
    for numero, (rotulo, _) in enumerate(acoes, 1):
        print(f"{numero} - {rotulo}")
    opcao = int(texto("0 - Sair da conta\nOpção: "))
    if opcao == 0:
        return None, None
    if not 1 <= opcao <= len(acoes):
        raise ValueError("Opção inválida.")
    _, acao = acoes[opcao - 1]
    return usuario.id, acao(sistema, usuario)


def preparar_simulacao(sistema):
    admin = Administrador(1, "Admin", "admin@demo")
    sistema.usuarios.append(admin)
    supervisor = sistema.cadastrar_supervisor(admin, "Bia", "bia@demo")
    ana = Atleta(3, "Ana", "ana@demo")
    leo = Atleta(4, "Léo", "leo@demo")
    sistema.usuarios.extend([ana, leo])
    for usuario in sistema.usuarios:
        definir_senha(usuario, "quadra")
    quadra = sistema.cadastrar_quadra(supervisor, "Central", "Futsal", 10, 100)
    faixas = [FaixaFuncionamento(dia, time(8), time(22)) for dia in range(7)]
    sistema.definir_disponibilidade(supervisor, quadra, faixas)
    sistema.cadastrar_equipamento(supervisor, quadra, "Bola", 3)
    for atleta in (ana, leo):
        sistema.comprar_creditos(atleta, 250).confirmar()

    # Histórico fictício permite demonstrar avaliação e repasse sem esperar uma partida acabar.
    ontem = (datetime.now() - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    anterior = Reserva(1, ontem, ontem + timedelta(hours=1), ana, quadra)
    anterior.valor_total = quadra.calcular_valor(anterior.inicio, anterior.fim)
    sistema.reservas.append(anterior)
    sistema.pagar_reserva(ana, anterior)
    sistema.concluir_reserva(supervisor, anterior)

    amanha = ontem + timedelta(days=2)
    atual = sistema.criar_reserva(ana, quadra, amanha, amanha + timedelta(hours=1), "rateado")
    sistema.autorizar_participante(ana, atual, leo)
    print("\nSIMULAÇÃO TEMPORÁRIA — senha das quatro contas: quadra")
    print("Administrador: admin@demo | Supervisor: bia@demo | Atletas: ana@demo e leo@demo")
    print("Reserva 1: concluída e paga, disponível para avaliação e repasse.")
    print(f"Reserva 2: {amanha:%d/%m/%Y %H:%M}, privada, com convite para Léo.")
    print("Entre como Léo e aceite o convite. Cada atleta poderá pagar R$ 50.")


def executar_sistema(caminho_banco=None, simular=False):
    conta_id = None
    print("Sistema de reservas de quadras")
    with closing(abrir_banco(":memory:" if simular else caminho_banco)) as banco:
        if simular:
            versao, sistema = carregar(banco)
            preparar_simulacao(sistema)
            salvar(banco, versao, sistema)
        try:
            while True:
                versao, sistema = carregar(banco)
                anterior = serializar(sistema)
                usuario = next((u for u in sistema.usuarios if u.id == conta_id), None)
                try:
                    mensagem = None
                    if not sistema.usuarios:
                        print("\nPrimeiro acesso: cadastre o administrador do sistema.")
                        nome, email, senha = dados_de_cadastro(sistema)
                        admin = Administrador(1, nome, email)
                        definir_senha(admin, senha)
                        sistema.usuarios.append(admin)
                        mensagem = "Administrador cadastrado. Entre com seu e-mail e senha."
                    elif usuario is not None and not usuario.banido:
                        conta_id, mensagem = menu_do_perfil(sistema, usuario)
                    else:
                        conta_id = None
                        opcao = texto("\n1 - Criar conta de atleta\n2 - Entrar com e-mail e senha\n"
                                      "0 - Encerrar programa\nOpção: ")
                        if opcao == "0":
                            break
                        if opcao == "1":
                            nome, email, senha = dados_de_cadastro(sistema)
                            atleta = Atleta(len(sistema.usuarios) + 1, nome, email)
                            definir_senha(atleta, senha)
                            sistema.usuarios.append(atleta)
                            mensagem = "Conta criada. Use a opção 2 para entrar."
                        elif opcao == "2":
                            email = texto("E-mail: ")
                            usuario = autenticar(sistema, email, ler_senha("Senha: "))
                            conta_id = usuario.id
                        else:
                            print("Opção inválida.")
                    if serializar(sistema) != anterior:
                        salvar(banco, versao, sistema)
                    if mensagem:
                        print(mensagem)
                except SelecaoCancelada:
                    continue
                except (ValueError, PermissionError, InvalidOperation) as erro:
                    print(f"Operação recusada: {erro}")
        except (EOFError, KeyboardInterrupt):
            print()
    print("Programa encerrado.")


if __name__ == "__main__":
    if "--simular" in sys.argv[1:]:
        executar_sistema(simular=True)
    else:
        try:
            modo = input("1 - Abrir sistema com dados salvos\n2 - Simulação para apresentação\n"
                         "0 - Sair\nOpção: ").strip()
            while modo not in ("0", "1", "2"):
                modo = input("Escolha 0, 1 ou 2: ").strip()
            if modo != "0":
                executar_sistema(simular=modo == "2")
        except (EOFError, KeyboardInterrupt):
            print("Programa encerrado.")
