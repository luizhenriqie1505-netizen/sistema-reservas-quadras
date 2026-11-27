import sys
from contextlib import closing, contextmanager
from contextvars import ContextVar
from getpass import getpass
from datetime import date, datetime, timedelta, time
from decimal import Decimal, InvalidOperation

from armazenamento import abrir_banco, autenticar, carregar, definir_senha, salvar, serializar
from enums import StatusSolicitacao
from modelos import Administrador, Atleta, FaixaFuncionamento, Reserva, Supervisor


class SelecaoCancelada(Exception):
    pass


_dialogo = ContextVar("dialogo_da_acao", default=None)


@contextmanager
def usar_dialogo(dialogo):
    token = _dialogo.set(dialogo)
    try:
        yield
    finally:
        _dialogo.reset(token)


def perguntar(mensagem):
    dialogo = _dialogo.get()
    return dialogo.perguntar(mensagem) if dialogo else input(mensagem)


def informar(*partes):
    dialogo = _dialogo.get()
    if dialogo:
        dialogo.linhas.append(" ".join(map(str, partes)))
    else:
        print(*partes)


def texto(pergunta):
    resposta = perguntar(pergunta).strip()
    if not resposta:
        raise ValueError("Campo obrigatório.")
    return resposta


def valor_monetario(pergunta):
    valor = Decimal(texto(pergunta).replace(",", "."))
    if not valor.is_finite() or valor < 0:
        raise ValueError("Informe um valor monetário válido.")
    return valor


def ler_senha(mensagem):
    if _dialogo.get():
        return _dialogo.get().perguntar(mensagem, senha=True)
    if sys.stdin.isatty():
        return getpass(mensagem)
    return perguntar(mensagem)


def dados_de_cadastro(sistema):
    nome, email = sistema.validar_cadastro(texto("Nome: "), texto("E-mail: "))
    senha = ler_senha("Senha: ")
    if not senha.strip() or senha != ler_senha("Confirme a senha: "):
        raise ValueError("Senha vazia ou confirmação diferente.")
    return nome, email, senha


def periodo(varios_dias=False):
    data = datetime.strptime(texto("Data (DD/MM/AAAA): "), "%d/%m/%Y").date()
    inicio = datetime.strptime(texto("Início (HH:MM): "), "%H:%M").time()
    data_final = data
    if varios_dias:
        outra_data = perguntar(f"Data final [{data:%d/%m/%Y}]: ").strip()
        if outra_data:
            data_final = datetime.strptime(outra_data, "%d/%m/%Y").date()
    fim = datetime.strptime(texto("Fim (HH:MM): "), "%H:%M").time()
    inicio = datetime.combine(data, inicio)
    fim = datetime.combine(data_final, fim)
    if fim <= inicio:
        raise ValueError("O fim deve ser posterior ao início.")
    return inicio, fim


def ler_faixas():
    dias = texto("Dias (1=seg, 7=dom), separados por espaço: ")
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


DIAS_DA_SEMANA = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def ler_dia_da_agenda(entrada, hoje):
    nome = entrada.strip().casefold().removesuffix("-feira")
    if nome == "hoje":
        return hoje
    if nome in ("amanhã", "amanha"):
        return hoje + timedelta(days=1)
    nome = {"terca": "terça", "sabado": "sábado"}.get(nome, nome)
    if nome in DIAS_DA_SEMANA:
        # Revisão (Luiz) — se hoje é segunda e eu digitar “segunda”, qual data aparece?
        dias = (DIAS_DA_SEMANA.index(nome) - hoje.weekday()) % 7
        return hoje + timedelta(days=dias)
    try:
        return datetime.strptime(nome, "%d/%m/%Y").date()
    except ValueError:
        raise ValueError("Dia ou data inválidos (DD/MM/AAAA).") from None


def ler_periodo_da_agenda(entrada, hoje):
    entrada = entrada.strip().casefold()
    quantidade = entrada.removesuffix(" dias").strip()
    if quantidade.isdecimal():
        dias = int(quantidade)
        if not 1 <= dias <= (date.max - hoje).days + 1:
            raise ValueError("Quantidade de dias inválida.")
        return hoje, hoje + timedelta(days=dias - 1)
    de, separador, ate = entrada.partition(" a ")
    primeiro = ler_dia_da_agenda(de, hoje)
    ultimo = ler_dia_da_agenda(ate, hoje) if separador else primeiro
    return primeiro, ultimo


def mostrar_agenda(sistema, quadra, primeiro=None, ultimo=None):
    tem_horario = False
    for dia, faixas in sistema.consultar_agenda(quadra, primeiro, ultimo):
        horarios = " | ".join(f"{abre:%H:%M}–{fecha:%H:%M}" for abre, fecha in faixas)
        informar(f"{dia:%d/%m/%Y} ({DIAS_DA_SEMANA[dia.weekday()]}): {horarios or 'sem horários livres'}")
        if faixas:
            tem_horario = True
    return tem_horario


def reservar_no_dia(sistema, atleta, quadra, dia, hora):
    inicio = datetime.combine(dia, datetime.strptime(hora, "%H:%M").time())
    fim = datetime.combine(dia, datetime.strptime(texto("Fim (HH:MM): "), "%H:%M").time())
    if not sistema.consultar_disponibilidade(quadra, inicio, fim):
        raise ValueError("Horário indisponível.")
    # Revisão (Ronaldo) — escolher pagamento integral aqui já desconta o valor da carteira?
    informar(f"Total da reserva: R$ {quadra.calcular_valor(inicio, fim):.2f}")
    modos = {"1": "integral", "2": "rateado"}
    modo = modos.get(texto("Pagamento (1 - Integral, 2 - Rateado): "))
    if modo is None:
        raise ValueError("Escolha 1 ou 2.")
    reserva = sistema.criar_reserva(atleta, quadra, inicio, fim, modo)
    return f"Reserva {reserva.id} confirmada para {atleta.nome} em {quadra.nome}."


def consultar_agenda(sistema, usuario):
    atleta = isinstance(usuario, Atleta)
    quadras = sistema.consultar_quadras(usuario)
    if not quadras:
        return "Nenhuma quadra disponível."
    quadra = quadras[0] if len(quadras) == 1 else selecionar(quadras, descricao_quadra)
    informar(f"\n{quadra.nome} — próximos 7 dias — R$ {quadra.valor_hora:.2f}/hora")
    mostrar_agenda(sistema, quadra)
    dia_para_reserva = None
    while True:
        pergunta = "Dia ou período: " if dia_para_reserva is None else "Início ou nova consulta: "
        entrada = perguntar(pergunta).strip()
        if not entrada or entrada == "0":
            return
        try:
            if dia_para_reserva is not None and ":" in entrada:
                return reservar_no_dia(sistema, usuario, quadra, dia_para_reserva, entrada)
            primeiro, ultimo = ler_periodo_da_agenda(entrada, datetime.now().date())
            tem_horario = mostrar_agenda(sistema, quadra, primeiro, ultimo)
            dia_para_reserva = primeiro if atleta and primeiro == ultimo and tem_horario else None
        except ValueError as erro:
            informar(erro)


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
    dialogo = _dialogo.get()
    if dialogo:
        return dialogo.escolher(tuple(por_id.values()), descricao)
    for chave, item in por_id.items():
        informar(f"{chave} - {descricao(item)}")
    chave = int(texto(f"0 - Voltar\n{pergunta}: "))
    if chave == 0:
        raise SelecaoCancelada()
    if chave not in por_id:
        raise ValueError("Escolha um ID da lista.")
    return por_id[chave]


def minhas_reservas(sistema, usuario):
    return sistema.consultar_reservas(usuario)


def mostrar_reservas(reservas):
    if not reservas:
        informar("Nenhuma reserva.")
    for reserva in reservas:
        informar(f"{reserva.id} - {descricao_reserva(reserva)}")


def minhas_partidas(sistema, usuario):
    reservas = minhas_reservas(sistema, usuario)
    if not reservas:
        return "Nenhuma partida."
    for reserva in reservas:
        informar(f"{reserva.id} - {descricao_reserva(reserva)}")
        informar("Participantes:", ", ".join(atleta.nome for atleta in reserva.partida.participantes))
        for pedido in reserva.solicitacoes:
            informar(f"  Material: {pedido.quantidade} x {pedido.equipamento.nome}, {pedido.status.value}")


def descricao_quadra(quadra):
    estado = "ativa" if quadra.ativa else "desativada"
    if any(b.fim_efetivo > datetime.now(b.fim.tzinfo) for b in quadra.agenda.bloqueios):
        estado += ", com interdição"
    return f"{quadra.nome} ({estado})"


def escolher_quadra(sistema, usuario):
    quadras = [quadra for quadra in sistema.consultar_quadras()
               if isinstance(usuario, Administrador) or quadra.supervisor == usuario]
    return selecionar(quadras, descricao_quadra)


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
    alvos = [pessoa for pessoa in sistema.usuarios
             if pessoa != autor and sistema.permite_denuncia_entre_perfis(autor, pessoa)]
    alvo = selecionar(alvos, lambda pessoa: f"{pessoa.nome} ({type(pessoa).__name__})")
    denuncia = sistema.registrar_denuncia(autor, alvo, texto("Motivo: "))
    return f"Denúncia {denuncia.id} registrada."


def dados(sistema, autor):
    alvo = autor
    if isinstance(autor, Administrador):
        alvo = selecionar(sistema.usuarios, lambda pessoa: pessoa.nome)
    for campo, valor in sistema.consultar_dados(autor, alvo).items():
        informar(f"{campo}: {valor}")


def banir(sistema, admin):
    alvos = [pessoa for pessoa in sistema.usuarios if isinstance(pessoa, (Supervisor, Atleta))]
    alvo = selecionar(alvos, lambda pessoa: f"{pessoa.nome} ({type(pessoa).__name__})")
    sistema.banir_usuario(admin, alvo, texto("Justificativa: "))
    return f"Conta de {alvo.nome} banida."


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
    ids = [int(item) for item in texto("IDs das reservas, separados por espaço: ").split()]
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


def atualizar_quadra(sistema, supervisor):
    quadra = escolher_quadra(sistema, supervisor)
    nome, modalidade = texto("Nome: "), texto("Modalidade: ")
    capacidade = int(texto("Capacidade: "))
    sistema.atualizar_quadra(supervisor, quadra, nome, modalidade, capacidade)
    return f"Cadastro de {quadra.nome} atualizado."


def alterar_preco(sistema, supervisor):
    quadra = escolher_quadra(sistema, supervisor)
    sistema.definir_preco(supervisor, quadra, valor_monetario("Novo preço por hora: "))
    return f"{quadra.nome}: R$ {quadra.valor_hora:.2f}/hora."


def definir_funcionamento(sistema, supervisor):
    quadra = escolher_quadra(sistema, supervisor)
    for faixa in quadra.agenda.faixas:
        informar(f"Dia {faixa.dia_semana + 1}: {faixa.abertura:%H:%M} às {faixa.fechamento:%H:%M}")
    acao = texto("Faixas (1 - Acrescentar, 2 - Substituir): ")
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
    return f"{quadra.nome} disponível."


def excluir_quadra(sistema, supervisor):
    quadra = escolher_quadra(sistema, supervisor)
    sistema.excluir_quadra(supervisor, quadra)
    if quadra in sistema.quadras:
        return "Quadra desativada."
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


def fornecer(sistema, supervisor):
    reserva = escolher_reserva(sistema, supervisor)
    pendentes = [p for p in reserva.solicitacoes if p.status == StatusSolicitacao.SOLICITADA]
    pedido = selecionar(pendentes, lambda p: f"{p.quantidade} x {p.equipamento.nome}")
    sistema.fornecer_equipamento(supervisor, reserva, pedido)
    return f"Material fornecido: {pedido.quantidade} x {pedido.equipamento.nome}."


def comprar(sistema, atleta):
    valor = valor_monetario("Valor dos créditos (R$): ")
    compra = sistema.comprar_creditos(atleta, valor)
    confirmacao = texto("Confirmar pagamento simulado (s/n)? ").casefold()
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
    if modo is None:
        modo = texto("Método (integral/rateado): ").lower()
        if modo not in ("integral", "rateado"):
            raise ValueError("Método inválido.")
    pagamento = sistema.pagar_reserva(atleta, reserva, integral=modo == "integral")
    return f"Pagamento confirmado: R$ {pagamento.valor:.2f}."


def rateio(sistema, atleta):
    reserva = escolher_reserva(sistema, atleta, participante=True)
    parcelas = sistema.calcular_rateio(reserva)
    for participante in reserva.partida.participantes:
        informar(f"{participante.nome} (ID {participante.id}): R$ {parcelas[participante.id]:.2f}")


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
    return f"Convite registrado para {atleta.nome}."


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
        ("Ver agenda e horários livres", consultar_agenda),
        ("Definir funcionamento", definir_funcionamento),
        ("Disponibilizar quadra e retirar interdições", disponibilizar),
        ("Atualizar cadastro da quadra", atualizar_quadra),
        ("Excluir quadra (desativar se houver histórico)", excluir_quadra),
        ("Cadastrar equipamento", cadastrar_material),
        ("Fornecer equipamento", fornecer),
        ("Concluir reserva encerrada", concluir),
        ("Registrar denúncia", denunciar),
        ("Meus dados", dados),
    ),
    Atleta: (
        ("Ver agenda, horários livres e reservar", consultar_agenda),
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

    ontem = (datetime.now() - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    anterior = Reserva(1, ontem, ontem + timedelta(hours=1), ana, quadra)
    anterior.valor_total = quadra.calcular_valor(anterior.inicio, anterior.fim)
    sistema.reservas.append(anterior)
    sistema.pagar_reserva(ana, anterior)
    sistema.concluir_reserva(supervisor, anterior)

    amanha = ontem + timedelta(days=2)
    atual = sistema.criar_reserva(ana, quadra, amanha, amanha + timedelta(hours=1), "rateado")
    sistema.autorizar_participante(ana, atual, leo)


@contextmanager
def banco_da_sessao(caminho_banco=None, simular=False):
    # Revisão (Luiz e Ronaldo) — o que fica salvo quando a simulação termina?
    with closing(abrir_banco(":memory:" if simular else caminho_banco)) as banco:
        if simular:
            versao, sistema = carregar(banco)
            preparar_simulacao(sistema)
            salvar(banco, versao, sistema)
        yield banco


def abrir_interface(simular=False):
    from interface import abrir_janela
    with banco_da_sessao(simular=simular) as banco:
        abrir_janela(banco, simular)


def executar_sistema(caminho_banco=None, simular=False):
    conta_id = None
    print("Sistema de reservas de quadras")
    with banco_da_sessao(caminho_banco, simular) as banco:
        if simular:
            print("\nSimulação temporária | Senha: quadra")
            print("Administrador: admin@demo | Supervisor: bia@demo | Atletas: ana@demo e leo@demo")
        try:
            while True:
                versao, sistema = carregar(banco)
                anterior = serializar(sistema)
                usuario = next((u for u in sistema.usuarios if u.id == conta_id), None)
                try:
                    mensagem = None
                    if not sistema.usuarios:
                        print("\nCadastro do administrador")
                        nome, email, senha = dados_de_cadastro(sistema)
                        admin = sistema.cadastrar_administrador_inicial(nome, email)
                        definir_senha(admin, senha)
                        mensagem = "Administrador cadastrado."
                    elif usuario is not None and not usuario.banido:
                        conta_id, mensagem = menu_do_perfil(sistema, usuario)
                    else:
                        conta_id = None
                        opcao = texto("\n1 - Criar conta de atleta\n2 - Entrar\n0 - Encerrar\nOpção: ")
                        if opcao == "0":
                            break
                        if opcao == "1":
                            nome, email, senha = dados_de_cadastro(sistema)
                            atleta = sistema.cadastrar_atleta(nome, email)
                            definir_senha(atleta, senha)
                            mensagem = "Conta criada."
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
    if "--gui" in sys.argv[1:]:
        abrir_interface(simular="--simular" in sys.argv[1:])
    elif "--simular" in sys.argv[1:]:
        abrir_interface(simular=True)
    else:
        try:
            modo = input("1 - Sistema com dados salvos\n2 - Simulação gráfica\n3 - Interface gráfica\n"
                         "0 - Sair\nOpção: ").strip()
            while modo not in ("0", "1", "2", "3"):
                modo = input("Opção (0 a 3): ").strip()
            if modo == "3":
                abrir_interface()
            elif modo == "2":
                abrir_interface(simular=True)
            elif modo == "1":
                executar_sistema()
        except (EOFError, KeyboardInterrupt):
            print("Programa encerrado.")
