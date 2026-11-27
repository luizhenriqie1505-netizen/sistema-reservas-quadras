import calendar
import sqlite3
import tkinter as tk
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from tkinter import font, messagebox, ttk

from armazenamento import ConflitoDeVersao, autenticar, carregar, definir_senha, salvar
from enums import StatusPagamento, StatusReserva, StatusSolicitacao
from modelos import Administrador, Atleta, FaixaFuncionamento, Supervisor


TITULO = "Sistema de Reservas de Quadras"
FUNDO = "#edf5ff"
AZUL = "#14365c"
AZUL_CLARO = "#dcecff"
LARANJA = "#ffad59"
MESES = ("Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
         "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro")
DIAS = {"Todos os dias": range(7), "Segunda a sexta": range(5), "Sábado e domingo": (5, 6)}


def ler_data(texto):
    try:
        return datetime.strptime(texto.strip(), "%d/%m/%Y").date()
    except ValueError:
        raise ValueError("Informe a data no formato DD/MM/AAAA.") from None


def ler_hora(texto):
    try:
        return datetime.strptime(texto.strip(), "%H:%M").time()
    except ValueError:
        raise ValueError("Informe o horário no formato HH:MM.") from None


def reais(valor):
    return f"R$ {valor:.2f}".replace(".", ",")


def por_id(itens, codigo):
    for item in itens:
        if item.id == codigo:
            return item
    raise ValueError("O registro selecionado já não está disponível.")


def criar_lista(pai, altura=8):
    quadro = ttk.Frame(pai)
    quadro.pack(fill="both", expand=True)
    lista = tk.Listbox(quadro, height=altura, background=FUNDO, foreground=AZUL,
                       selectbackground=AZUL_CLARO, selectforeground=AZUL,
                       relief="flat", highlightthickness=0, activestyle="none", exportselection=False)
    barra = ttk.Scrollbar(quadro, orient="vertical", command=lista.yview)
    lista.configure(yscrollcommand=barra.set)
    barra.pack(side="right", fill="y")
    lista.pack(side="left", fill="both", expand=True)
    return lista


class Calendario(ttk.Frame):
    def __init__(self, pai, dia, ao_escolher):
        super().__init__(pai)
        self.dia = dia
        self.mes = dia.replace(day=1)
        self.ao_escolher = ao_escolher
        self.mostrar()

    def mudar_mes(self, passo):
        outro = self.mes - timedelta(days=1) if passo < 0 else self.mes + timedelta(days=32)
        self.mes = outro.replace(day=1)
        self.mostrar()

    def escolher(self, dia):
        self.dia = dia
        self.mostrar()
        self.ao_escolher(dia)

    def mostrar(self):
        for widget in self.winfo_children():
            widget.destroy()
        ttk.Button(self, text="‹", width=3, command=lambda: self.mudar_mes(-1)).grid(row=0, column=0)
        ttk.Label(self, text=f"{MESES[self.mes.month - 1]} {self.mes.year}",
                  anchor="center").grid(row=0, column=1, columnspan=5, sticky="ew")
        ttk.Button(self, text="›", width=3, command=lambda: self.mudar_mes(1)).grid(row=0, column=6)
        for coluna, nome in enumerate(("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")):
            self.columnconfigure(coluna, weight=1, uniform="dia")
            ttk.Label(self, text=nome, anchor="center").grid(row=1, column=coluna, sticky="ew")
        semanas = calendar.Calendar().monthdayscalendar(self.mes.year, self.mes.month)
        for linha, semana in enumerate(semanas, 2):
            for coluna, numero in enumerate(semana):
                if numero:
                    dia = self.mes.replace(day=numero)
                    botao = ttk.Button(self, text=str(numero), width=3,
                                       style="Ativa.TButton" if dia == self.dia else "TButton",
                                       command=lambda d=dia: self.escolher(d))
                    botao.grid(row=linha, column=coluna, sticky="ew", padx=1, pady=1)
                    if dia < date.today():
                        botao.state(["disabled"])


class DialogoDeAcao:
    def __init__(self, pai, titulo):
        self.pai = pai
        self.titulo = titulo
        self.linhas = []

    def escolher(self, itens, descricao):
        from main import SelecaoCancelada
        janela = tk.Toplevel(self.pai, background=FUNDO)
        janela.title(self.titulo)
        janela.transient(self.pai)
        janela.geometry("550x265")
        quadro = ttk.Frame(janela, padding=14)
        quadro.pack(fill="both", expand=True)
        botoes = ttk.Frame(quadro)
        botoes.pack(side="bottom", fill="x", pady=(8, 0))
        lista = criar_lista(quadro, altura=5)
        for item in itens:
            lista.insert("end", descricao(item))
        lista.selection_set(0)
        resposta = []

        def confirmar(evento=None):
            selecao = lista.curselection()
            if selecao:
                resposta.append(itens[selecao[0]])
                janela.destroy()

        ttk.Button(botoes, text="Continuar", command=confirmar, style="Ativa.TButton").pack(side="left")
        ttk.Button(botoes, text="Voltar", command=janela.destroy).pack(side="left", padx=6)
        lista.bind("<Double-Button-1>", confirmar)
        janela.bind("<Return>", confirmar)
        janela.bind("<Escape>", lambda evento: janela.destroy())
        janela.grab_set()
        lista.focus_set()
        self.pai.wait_window(janela)
        if not resposta:
            raise SelecaoCancelada()
        return resposta[0]

    def perguntar(self, mensagem, senha=False):
        from main import SelecaoCancelada
        janela = tk.Toplevel(self.pai, background=FUNDO)
        janela.title(self.titulo)
        janela.transient(self.pai)
        corpo = ttk.Frame(janela, padding=14)
        corpo.pack(fill="both", expand=True)
        if self.linhas:
            from tkinter.scrolledtext import ScrolledText
            texto = ScrolledText(corpo, width=68, height=min(14, len(self.linhas) + 2), wrap="word")
            texto.insert("1.0", "\n".join(self.linhas))
            texto.configure(state="disabled")
            texto.pack(fill="both", expand=True, pady=(0, 8))
            self.linhas.clear()
        ttk.Label(corpo, text=mensagem.strip()).pack(anchor="w")
        entrada = ttk.Entry(corpo, show="*" if senha else "")
        entrada.pack(fill="x", pady=5)
        resposta = []

        def confirmar(evento=None):
            resposta.append(entrada.get())
            janela.destroy()

        ttk.Button(corpo, text="Continuar", command=confirmar).pack(side="left")
        ttk.Button(corpo, text="Cancelar", command=janela.destroy).pack(side="right")
        janela.bind("<Return>", confirmar)
        janela.bind("<Escape>", lambda evento: janela.destroy())
        janela.grab_set()
        entrada.focus_set()
        self.pai.wait_window(janela)
        if not resposta:
            raise SelecaoCancelada()
        return resposta[0]


class InterfaceReservas:
    def __init__(self, janela, banco, simular=False):
        self.janela = janela
        self.banco = banco
        self.simular = simular
        self.conta_id = None
        self.pagina = "Quadras"
        self.reserva_em_foco = None
        self.status = tk.StringVar(janela)
        self.contexto = tk.StringVar(janela)
        janela.title(TITULO)
        janela.geometry("650x515")
        janela.minsize(585, 480)
        janela.configure(background=FUNDO)
        estilo = ttk.Style(janela)
        estilo.theme_use("clam")
        padrao = font.nametofont("TkDefaultFont", root=janela)
        padrao.configure(family="Segoe UI", size=10)
        font.nametofont("TkTextFont", root=janela).configure(family="Segoe UI", size=10)
        estilo.configure(".", font=padrao, background=FUNDO, foreground=AZUL)
        estilo.configure("Titulo.TLabel", font=("Segoe UI", 16, "bold"))
        estilo.configure("TButton", background=AZUL_CLARO, foreground=AZUL, borderwidth=0, padding=(8, 4))
        estilo.map("TButton", background=[("active", "#c5e1ff")])
        estilo.configure("Aba.TButton", background=AZUL, foreground="white")
        estilo.map("Aba.TButton", background=[("active", "#204c79")])
        estilo.configure("Painel.TFrame", background="#ffffff")
        estilo.configure("Painel.TLabel", background="#ffffff", foreground=AZUL)
        estilo.configure("Ativa.TButton", background=LARANJA)
        estilo.map("Ativa.TButton", background=[("active", "#ffc78d")])
        estilo.configure("TEntry", fieldbackground="#ffffff")
        estilo.configure("TCombobox", fieldbackground="#ffffff")
        topo = tk.Frame(janela, background=AZUL, padx=14, pady=9)
        topo.pack(fill="x")
        desenho = tk.Canvas(topo, width=44, height=30, background=AZUL, highlightthickness=0)
        desenho.create_rectangle(2, 3, 42, 27, outline=LARANJA, width=2)
        desenho.create_line(22, 3, 22, 27, fill=LARANJA, width=2)
        desenho.create_oval(16, 9, 28, 21, outline=LARANJA, width=2)
        desenho.pack(side="left", padx=(0, 9))
        textos = tk.Frame(topo, background=AZUL)
        textos.pack(side="left", fill="x", expand=True)
        tk.Label(textos, text=TITULO, background=AZUL, foreground="white",
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(textos, textvariable=self.contexto, background=AZUL,
                 foreground=AZUL_CLARO).pack(anchor="w")
        self.painel = ttk.Frame(janela, padding=(15, 10, 15, 0))
        self.painel.pack(fill="both", expand=True)
        ttk.Label(janela, textvariable=self.status, padding=(15, 6)).pack(fill="x")
        self.atualizar()

    def tentar(self, acao, pai):
        try:
            acao()
        except ConflitoDeVersao as erro:
            if pai != self.janela:
                pai.destroy()
            self.atualizar()
            messagebox.showwarning("Dados atualizados", str(erro), parent=self.janela)
        except (ValueError, PermissionError, InvalidOperation, sqlite3.Error) as erro:
            messagebox.showerror("Operação recusada", str(erro), parent=pai)

    def botao(self, pai, texto, acao, *, ativo=False, lado="left", estilo=None):
        janela = pai.winfo_toplevel()
        botao = ttk.Button(pai, text=texto, command=lambda: self.tentar(acao, janela),
                           style=estilo or ("Ativa.TButton" if ativo else "TButton"))
        botao.pack(side=lado, padx=(0, 5))
        return botao

    def atualizar(self, pagina=None):
        self.versao, self.sistema = carregar(self.banco)
        self.usuario = next((u for u in self.sistema.usuarios if u.id == self.conta_id), None)
        for widget in self.painel.winfo_children():
            widget.destroy()
        self.corpo = ttk.Frame(self.painel)
        self.status.set("")
        modo = "Simulação" if self.simular else "Dados locais"
        if self.usuario is None or self.usuario.banido:
            self.conta_id = None
            self.contexto.set(modo)
            self.corpo.pack(fill="both", expand=True)
            self.entrada()
            return
        self.contexto.set(f"{modo}  |  {self.usuario.nome} ({type(self.usuario).__name__})")
        self.pagina = pagina or self.pagina
        paginas = {"Quadras": self.quadras, "Reservas": self.reservas, "Configurações": self.configuracoes}
        if isinstance(self.usuario, Administrador):
            paginas["Usuários"] = self.usuarios
            paginas["Repasses"] = self.repasses
        if isinstance(self.usuario, Supervisor):
            paginas = {"Hoje": self.hoje, **paginas}
        if isinstance(self.usuario, Atleta):
            paginas = {"Quadras": self.quadras, "Reservas": self.reservas,
                       "Partidas": self.partidas, "Carteira": self.carteira,
                       "Configurações": self.configuracoes}
        navegacao = ttk.Frame(self.painel)
        navegacao.pack(fill="x", pady=(0, 15))
        for nome in paginas:
            self.botao(navegacao, nome, lambda n=nome: self.atualizar(n), estilo="Aba.TButton" if nome == self.pagina else None)
        self.botao(navegacao, "Sair da conta", self.sair, lado="right")
        self.corpo.pack(fill="both", expand=True)
        if self.pagina not in paginas:
            self.pagina = next(iter(paginas))
        paginas[self.pagina]()

    def configuracoes(self):
        from main import MENUS
        grupos = {
            Administrador: (
                ("Gestão", {"denunciar"}),
            ),
            Supervisor: (
                ("Quadras e equipamentos", {"definir_funcionamento", "cadastrar_material"}),
                ("Conta", {"denunciar", "dados"}),
            ),
            Atleta: (
                ("Minha conta", {"denunciar", "dados"}),
            ),
        }
        for titulo, funcoes in grupos[type(self.usuario)]:
            ttk.Label(self.corpo, text=titulo, style="Titulo.TLabel").pack(anchor="w", pady=(6, 3))
            grade = ttk.Frame(self.corpo)
            grade.pack(fill="x", pady=(0, 3))
            acoes = ((nome, acao) for nome, acao in MENUS[type(self.usuario)] if acao.__name__ in funcoes)
            for indice, (nome, acao) in enumerate(acoes):
                def abrir(rotulo=nome, funcao=acao):
                    self.tentar(lambda: self.executar_acao(rotulo, funcao), self.janela)
                ttk.Button(grade, text=nome, command=abrir).grid(
                    row=indice // 2, column=indice % 2, sticky="ew", padx=3, pady=2)
            for coluna in range(2):
                grade.columnconfigure(coluna, weight=1, uniform="acao")

    def partidas(self):
        from main import MENUS
        ttk.Label(self.corpo, text="Partidas abertas e convites", style="Titulo.TLabel").pack(anchor="w")
        opcoes = self.sistema.consultar_opcoes_de_inscricao(self.usuario)
        acoes = self.lista((r.id, f"  {r.quadra.nome} · {r.inicio:%d/%m às %H:%M} · "
                            f"{r.responsavel.nome} · {'Pública' if r.partida.publica else 'Convite'}"
                            f" · {r.partida.limite_participantes - len(r.partida.participantes)} vaga(s)")
                           for r in opcoes)

        def entrar():
            codigo = self.selecionado("uma partida")

            def aceitar(sistema, autor):
                sistema.participar_partida(autor, por_id(sistema.reservas, codigo))
                return "Você entrou na partida."
            self.gravar(aceitar)

        if opcoes:
            self.botao(acoes, "Entrar na partida", entrar, ativo=True)
        for nome, acao in MENUS[Atleta]:
            if acao.__name__ in {"privacidade", "convidar", "solicitar"}:
                self.botao(acoes, nome, lambda n=nome, a=acao: self.executar_acao(n, a))

    def carteira(self):
        ttk.Label(self.corpo, text="Carteira", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(self.corpo, text=f"Saldo disponível · {reais(self.usuario.carteira.saldo)}").pack(anchor="w", pady=7)
        pagamentos = [p for p in self.sistema.pagamentos if p.pagador == self.usuario]
        acoes = self.lista((p.id, f"  {p.reserva.quadra.nome} · {p.reserva.inicio:%d/%m} · "
                            f"{p.status.value} · {reais(p.valor)}") for p in reversed(pagamentos))

        def comprar(sistema, autor, dados):
            compra = sistema.comprar_creditos(autor, Decimal(dados["Valor em reais"].replace(",", ".")))
            compra.confirmar()
            return f"{reais(compra.valor)} adicionados à carteira."

        self.botao(acoes, "Adicionar créditos", lambda: self.formulario(
            "Comprar créditos (pagamento simulado)", {"Valor em reais": ""}, comprar), ativo=True)

    def hoje(self):
        self.reservas(diaria=True)

    def executar_acao(self, nome, acao):
        from main import SelecaoCancelada, usar_dialogo
        from armazenamento import serializar
        sistema, autor = self.dados_atuais()
        anterior = serializar(sistema)
        dialogo = DialogoDeAcao(self.janela, nome)
        try:
            with usar_dialogo(dialogo):
                mensagem = acao(sistema, autor)
        except SelecaoCancelada:
            return
        if anterior != serializar(sistema):
            salvar(self.banco, self.versao, sistema)
        self.atualizar()
        if dialogo.linhas:
            messagebox.showinfo(nome, "\n".join(dialogo.linhas), parent=self.janela)
        if mensagem:
            self.status.set(mensagem)

    def entrada(self):
        caixa = ttk.Frame(self.corpo)
        caixa.place(relx=0.5, rely=0.45, anchor="center")
        if not self.sistema.usuarios:
            ttk.Label(caixa, text="Primeiro acesso", style="Titulo.TLabel").pack(pady=(0, 15))
            self.botao(caixa, "Cadastrar administrador", lambda: self.form_conta(Administrador))
            return
        ttk.Label(caixa, text="Entrar", style="Titulo.TLabel").pack(anchor="w", pady=(0, 10))
        ttk.Label(caixa, text="E-mail").pack(anchor="w")
        email = ttk.Entry(caixa, width=37)
        email.pack(fill="x", pady=(2, 7))
        ttk.Label(caixa, text="Senha").pack(anchor="w")
        senha = ttk.Entry(caixa, show="*", width=37)
        senha.pack(fill="x", pady=(2, 12))

        def entrar():
            _, sistema = carregar(self.banco)
            try:
                conta = autenticar(sistema, email.get().strip(), senha.get())
            except PermissionError:
                senha.delete(0, tk.END)
                senha.focus_set()
                raise
            self.conta_id = conta.id
            inicial = {Administrador: "Repasses", Supervisor: "Hoje", Atleta: "Quadras"}
            self.atualizar(inicial[type(conta)])

        botoes = ttk.Frame(caixa)
        botoes.pack(fill="x")
        self.botao(botoes, "Entrar", entrar, ativo=True)
        self.botao(botoes, "Cadastrar atleta", lambda: self.form_conta(Atleta))
        email.bind("<Return>", lambda evento: senha.focus_set())
        senha.bind("<Return>", lambda evento: self.tentar(entrar, self.janela))
        if self.simular:
            ttk.Label(caixa, text="Contas da demonstração").pack(anchor="w", pady=(16, 5))
            atalhos = ttk.Frame(caixa)
            atalhos.pack(fill="x")

            def entrar_com(conta):
                email.delete(0, "end")
                email.insert(0, conta)
                senha.delete(0, "end")
                senha.insert(0, "quadra")
                entrar()

            for nome, conta in (("Ana", "ana@demo"), ("Léo", "leo@demo"),
                               ("Bia", "bia@demo"), ("Admin", "admin@demo")):
                self.botao(atalhos, nome, lambda c=conta: entrar_com(c))
        email.focus_set()

    def sair(self):
        self.conta_id = None
        self.atualizar("Quadras")

    def dados_atuais(self):
        versao, sistema = carregar(self.banco)
        if versao != self.versao:
            raise ConflitoDeVersao("A lista mudou em outra sessão. Confira os dados e repita a operação.")
        autor = por_id(sistema.usuarios, self.conta_id) if self.conta_id is not None else None
        return sistema, autor

    def gravar(self, operacao, pagina=None):
        sistema, autor = self.dados_atuais()
        mensagem = operacao(sistema, autor)
        if mensagem is None:
            return False
        salvar(self.banco, self.versao, sistema)
        self.atualizar(pagina)
        self.status.set(mensagem)
        return True

    def formulario(self, titulo, campos, operacao, opcoes=None, *, aviso=None):
        for widget in self.corpo.winfo_children():
            widget.destroy()
        self.status.set("")
        ttk.Label(self.corpo, text=titulo, style="Titulo.TLabel").pack(anchor="w", pady=(0, 10))
        quadro = ttk.Frame(self.corpo)
        quadro.pack(fill="x")
        entradas = {}
        for linha, (rotulo, inicial) in enumerate(campos.items()):
            ttk.Label(quadro, text=rotulo).grid(row=linha, column=0, sticky="w", padx=(0, 12), pady=4)
            if opcoes and rotulo in opcoes:
                campo = ttk.Combobox(quadro, values=opcoes[rotulo], state="readonly", width=26)
                campo.set(inicial)
            else:
                campo = ttk.Entry(quadro, width=29, show="*" if "senha" in rotulo.casefold() else "")
                campo.insert(0, inicial)
            campo.grid(row=linha, column=1, sticky="ew", pady=4)
            entradas[rotulo] = campo
        quadro.columnconfigure(1, weight=1)

        def confirmar():
            dados = {chave: campo.get() for chave, campo in entradas.items()}
            for chave, valor in dados.items():
                if not valor.strip():
                    raise ValueError(f"Preencha o campo {chave}.")
            self.gravar(lambda s, autor: operacao(s, autor, dados))

        if aviso:
            ttk.Label(quadro, text=aviso, wraplength=330).grid(row=len(campos), columnspan=2,
                                                               sticky="w", pady=(8, 0))
        botoes = ttk.Frame(quadro)
        botoes.grid(row=len(campos) + 1, columnspan=2, sticky="e", pady=(14, 0))
        self.botao(botoes, "Salvar", confirmar, ativo=True)
        self.botao(botoes, "Voltar", self.atualizar)
        for campo in entradas.values():
            campo.bind("<Return>", lambda evento: self.tentar(confirmar, self.janela))
        next(iter(entradas.values())).focus_set()

    def form_conta(self, perfil):
        def cadastrar(sistema, autor, dados):
            if dados["Senha"] != dados["Confirmar senha"]:
                raise ValueError("A confirmação de senha está diferente.")
            nome, email = dados["Nome"], dados["E-mail"]
            if perfil is Supervisor:
                conta = sistema.cadastrar_supervisor(autor, nome, email)
            elif perfil is Administrador:
                conta = sistema.cadastrar_administrador_inicial(nome, email)
            else:
                conta = sistema.cadastrar_atleta(nome, email)
            definir_senha(conta, dados["Senha"])
            return f"Conta de {conta.nome} cadastrada."

        self.formulario(f"Cadastrar {perfil.__name__.lower()}",
                        {"Nome": "", "E-mail": "", "Senha": "", "Confirmar senha": ""}, cadastrar)

    def lista(self, linhas):
        self.itens = dict(linhas)
        self.registros = criar_lista(self.corpo)
        for descricao in self.itens.values():
            self.registros.insert("end", descricao)
        if self.itens:
            self.registros.selection_set(0)
        else:
            self.status.set("Nenhum registro nesta lista.")
        acoes = ttk.Frame(self.corpo)
        acoes.pack(fill="x", pady=(10, 0))
        return acoes

    def selecionado(self, entidade):
        selecao = self.registros.curselection()
        if not selecao:
            raise ValueError(f"Selecione {entidade} na lista.")
        return tuple(self.itens)[selecao[0]]

    def usuarios(self):
        ttk.Label(self.corpo, text="Usuários", style="Titulo.TLabel").pack(anchor="w", pady=(0, 7))
        pessoas = self.sistema.consultar_usuarios(self.usuario)
        acoes = self.lista((u.id, f"  {u.nome}  ·  {type(u).__name__}  ·  {u.email}"
                            + ("  ·  Banida" if u.banido else "")) for u in pessoas)
        filtros = ttk.Frame(self.corpo)
        filtros.pack(fill="x", before=self.registros.master, pady=(0, 8))
        busca = tk.StringVar()
        ttk.Label(filtros, text="Buscar").pack(side="left", padx=(0, 5))
        ttk.Entry(filtros, textvariable=busca).pack(side="left", fill="x", expand=True)
        perfil = ttk.Combobox(filtros, state="readonly", width=14,
                              values=("Todos", "Administrador", "Supervisor", "Atleta"))
        perfil.set("Todos")
        perfil.pack(side="left", padx=(6, 0))
        todos = self.itens.copy()

        def filtrar(*_):
            termo = busca.get().strip().casefold()
            self.itens = {u.id: todos[u.id] for u in pessoas
                          if (perfil.get() in ("Todos", type(u).__name__))
                          and (termo in u.nome.casefold() or termo in u.email.casefold())}
            self.registros.delete(0, "end")
            for linha in self.itens.values():
                self.registros.insert("end", linha)
            if self.itens:
                self.registros.selection_set(0)
            self.status.set("" if self.itens else "Nenhum usuário encontrado.")

        busca.trace_add("write", filtrar)
        perfil.bind("<<ComboboxSelected>>", filtrar)
        self.botao(acoes, "Cadastrar supervisor", lambda: self.form_conta(Supervisor), ativo=True)
        self.botao(acoes, "Ver cadastro", self.ver_usuario)
        self.botao(acoes, "Banir conta", self.banir_conta)

    def ver_usuario(self):
        codigo = self.selecionado("uma conta")
        sistema, autor = self.dados_atuais()
        pessoa = por_id(sistema.usuarios, codigo)
        dados = sistema.consultar_dados(autor, pessoa)
        situacao = "Banida" if dados["banido"] else "Ativa"
        texto = f"{dados['email']}\n{type(pessoa).__name__} · {situacao}"
        if dados["motivo_banimento"]:
            texto += f"\nMotivo: {dados['motivo_banimento']}"
        messagebox.showinfo(pessoa.nome, texto, parent=self.janela)

    def banir_conta(self):
        codigo = self.selecionado("uma conta")
        pessoa = por_id(self.sistema.usuarios, codigo)
        if isinstance(pessoa, Administrador) or pessoa.banido:
            raise ValueError("Selecione um atleta ou supervisor com conta ativa.")

        def banir(sistema, autor, dados):
            texto = f"Banir a conta de {pessoa.nome} ({pessoa.email})?"
            if not messagebox.askyesno("Confirmar banimento", texto, parent=self.janela):
                return None
            sistema.banir_usuario(autor, por_id(sistema.usuarios, codigo), dados["Justificativa"])
            return f"Conta de {pessoa.nome} banida."

        self.formulario(f"Banir conta · {pessoa.nome}", {"Justificativa": ""}, banir)

    def quadras(self):
        titulo = "Minhas quadras" if isinstance(self.usuario, Supervisor) else "Quadras"
        ttk.Label(self.corpo, text=titulo, style="Titulo.TLabel").pack(anchor="w", pady=(0, 7))
        quadras = self.sistema.consultar_quadras(self.usuario)
        acoes = self.lista((q.id, q.nome) for q in quadras)
        self.botao(acoes, "Ver agenda", self.agenda)
        if isinstance(self.usuario, Atleta):
            reservar = lambda: self.form_reserva(self.selecionado("uma quadra"))
            self.botao(acoes, "Reservar", reservar, ativo=True)
            self.registros.bind("<Return>", lambda evento: self.tentar(reservar, self.janela))
            self.registros.bind("<ButtonRelease-1>", lambda evento: self.tentar(reservar, self.janela))
        if isinstance(self.usuario, Supervisor):
            self.botao(acoes, "Cadastrar quadra", self.form_quadra, ativo=True)
            self.botao(acoes, "Editar", lambda: self.form_quadra(self.selecionado("uma quadra")))
            self.botao(acoes, "Excluir", self.excluir_quadra)
            self.botao(acoes, "Disponibilizar", self.disponibilizar)
        if isinstance(self.usuario, (Administrador, Supervisor)):
            self.botao(acoes, "Interditar", self.interditar)

    def form_quadra(self, codigo=None):
        quadra = por_id(self.sistema.quadras, codigo) if codigo is not None else None
        campos = {"Nome": quadra.nome if quadra else "", "Modalidade": quadra.modalidade if quadra else "",
                  "Capacidade": str(quadra.capacidade) if quadra else "",
                  "Preço por hora (R$)": str(quadra.valor_hora).replace(".", ",") if quadra else ""}
        if quadra is None:
            campos.update({"Funcionamento": "Todos os dias", "Abertura": "08:00", "Fechamento": "22:00"})

        def cadastrar_ou_editar(sistema, autor, dados):
            nome, modalidade = dados["Nome"].strip(), dados["Modalidade"].strip()
            try:
                capacidade = int(dados["Capacidade"])
                preco = Decimal(dados["Preço por hora (R$)"].strip().replace(",", "."))
            except (ValueError, InvalidOperation):
                raise ValueError("Informe a capacidade em números inteiros e o preço em reais.") from None
            if codigo is None:
                abre, fecha = ler_hora(dados["Abertura"]), ler_hora(dados["Fechamento"])
                faixas = [FaixaFuncionamento(dia, abre, fecha) for dia in DIAS[dados["Funcionamento"]]]
                nova = sistema.cadastrar_quadra(autor, nome, modalidade, capacidade, preco)
                sistema.definir_disponibilidade(autor, nova, faixas)
                return f"Quadra {nova.nome} cadastrada."
            atual = por_id(sistema.quadras, codigo)
            sistema.atualizar_quadra(autor, atual, nome, modalidade, capacidade)
            sistema.definir_preco(autor, atual, preco)
            return f"Quadra {atual.nome} atualizada."

        self.formulario("Cadastrar quadra" if quadra is None else "Editar quadra", campos,
                        cadastrar_ou_editar, {"Funcionamento": tuple(DIAS)})

    def excluir_quadra(self):
        codigo = self.selecionado("uma quadra")
        nome = por_id(self.sistema.quadras, codigo).nome
        if not messagebox.askyesno("Excluir quadra", f"Excluir {nome}? Quadras com reservas são desativadas.",
                                   parent=self.janela):
            return

        def excluir(sistema, autor):
            quadra = por_id(sistema.quadras, codigo)
            sistema.excluir_quadra(autor, quadra)
            return f"Quadra {nome} desativada." if quadra in sistema.quadras else f"Quadra {nome} excluída."

        self.gravar(excluir)

    def disponibilizar(self):
        codigo = self.selecionado("uma quadra")
        nome = por_id(self.sistema.quadras, codigo).nome
        if not messagebox.askyesno("Disponibilizar quadra", f"Reabrir {nome} e retirar as interdições?",
                                   parent=self.janela):
            return

        def reabrir(sistema, autor):
            sistema.disponibilizar_quadra(autor, por_id(sistema.quadras, codigo))
            return f"Quadra {nome} disponível."

        self.gravar(reabrir)

    def interditar(self):
        codigo = self.selecionado("uma quadra")
        hoje = date.today().strftime("%d/%m/%Y")
        campos = {"Data inicial": hoje, "Início (HH:MM)": "", "Data final": hoje, "Fim (HH:MM)": "", "Motivo": ""}

        def bloquear(sistema, autor, dados):
            inicio = datetime.combine(ler_data(dados["Data inicial"]), ler_hora(dados["Início (HH:MM)"]))
            fim = datetime.combine(ler_data(dados["Data final"]), ler_hora(dados["Fim (HH:MM)"]))
            quadra = por_id(sistema.quadras, codigo)
            atingidas, estornos = sistema.impacto_interdicao(autor, quadra, inicio, fim)
            texto = f"{len(atingidas)} reserva(s) afetada(s) · {reais(estornos)} em estornos."
            for reserva in atingidas[:5]:
                texto += f"\n{reserva.inicio:%d/%m às %H:%M} · {reserva.responsavel.nome}"
            if len(atingidas) > 5:
                texto += f"\nE mais {len(atingidas) - 5} reserva(s)."
            if not messagebox.askyesno("Confirmar interdição", texto, parent=self.janela):
                return None
            sistema.interditar_quadra(autor, quadra, inicio, fim, dados["Motivo"].strip())
            return f"Interdição registrada em {quadra.nome}."

        self.formulario(f"Interditar {por_id(self.sistema.quadras, codigo).nome}", campos, bloquear,
                        aviso="As reservas atingidas serão canceladas. Os créditos pagos voltarão às carteiras.")

    def agenda(self):
        codigo = self.selecionado("uma quadra")
        for widget in self.corpo.winfo_children():
            widget.destroy()
        nome = por_id(self.sistema.quadras, codigo).nome
        ttk.Label(self.corpo, text=f"Agenda · {nome}", style="Titulo.TLabel").pack(anchor="w", pady=(0, 8))
        filtros = ttk.Frame(self.corpo)
        filtros.pack(fill="x", pady=(0, 10))
        datas = []
        for nome in ("De (DD/MM/AAAA)", "Até"):
            ttk.Label(filtros, text=nome).pack(side="left")
            entrada = ttk.Entry(filtros, width=12)
            entrada.pack(side="left", padx=(4, 8))
            datas.append(entrada)
        lista = criar_lista(self.corpo)
        dias = []

        def consultar():
            sistema, autor = self.dados_atuais()
            quadra = por_id(sistema.consultar_quadras(autor), codigo)
            inicio, fim = [ler_data(e.get()) if e.get().strip() else None for e in datas]
            dias[:] = list(sistema.consultar_agenda(quadra, inicio, fim))
            lista.delete(0, "end")
            for dia, faixas in dias:
                livres = "  ·  ".join(f"{a:%H:%M}–{b:%H:%M}" for a, b in faixas)
                lista.insert("end", f"  {dia:%d/%m}   {livres or 'Sem horários livres'}")

        def reservar():
            selecao = lista.curselection()
            if not selecao:
                raise ValueError("Selecione um dia na agenda.")
            dia = dias[selecao[0]][0]
            self.form_reserva(codigo, dia)

        self.botao(filtros, "Consultar", consultar)
        botoes = ttk.Frame(self.corpo)
        botoes.pack(fill="x", pady=(10, 0))
        if isinstance(self.usuario, Atleta):
            self.botao(botoes, "Reservar neste dia", reservar)
        self.botao(botoes, "Voltar", lambda: self.atualizar("Quadras"))
        consultar()

    def form_reserva(self, codigo, dia=None, anterior=None):
        quadra = por_id(self.sistema.quadras, codigo)
        for widget in self.corpo.winfo_children():
            widget.destroy()
        titulo = "Reagendar" if anterior else "Reservar"
        ttk.Label(self.corpo, text=f"{titulo} · {quadra.nome}", style="Titulo.TLabel").pack(anchor="w")
        selecao = ttk.Frame(self.corpo)
        selecao.pack(fill="x", pady=8)
        campos = ttk.Frame(selecao, padding=(14, 0, 0, 0))
        campos.pack(side="right", fill="x", expand=True)
        horario = tk.StringVar()
        disponibilidade = tk.StringVar()
        duracao = tk.StringVar(value="1")
        pagamento = tk.StringVar(value="Integral")
        ttk.Label(campos, text="Duração (horas inteiras)").pack(anchor="w")
        ttk.Entry(campos, textvariable=duracao, width=12).pack(anchor="w", pady=(2, 8))
        if anterior:
            segundos = Decimal(str((anterior.fim - anterior.inicio).total_seconds()))
            duracao.set(str((segundos / 3600).to_integral_value(rounding=ROUND_CEILING)))
        ttk.Label(campos, text="Hora de início").pack(anchor="w")
        horas = ttk.Combobox(campos, textvariable=horario, width=12, state="readonly")
        horas.pack(anchor="w", pady=(2, 8))
        if not anterior:
            ttk.Label(campos, text="Pagamento").pack(anchor="w")
            ttk.Combobox(campos, textvariable=pagamento, width=12, state="readonly",
                         values=("Integral", "Rateado")).pack(anchor="w", pady=(2, 8))
        ttk.Label(campos, textvariable=disponibilidade, wraplength=220).pack(anchor="w")

        def atualizar_horarios(data):
            _, faixas = next(self.sistema.consultar_agenda(quadra, data, ignorar=anterior))
            try:
                duracao_horas = horas_da_duracao()
            except (ValueError, InvalidOperation):
                duracao_horas = 24
            opcoes = []
            for abre, fecha in faixas:
                primeira_hora = abre.hour + int(abre.minute != 0)
                ultima_hora = fecha.hour - duracao_horas
                opcoes.extend(f"{hora:02d}:00" for hora in range(primeira_hora, ultima_hora + 1))
            horas.configure(values=opcoes)
            atual = horario.get()
            if atual not in opcoes:
                horario.set(opcoes[0] if opcoes else "")
            disponibilidade.set("" if opcoes else "Nenhum horário comporta essa duração.")

        calendario = Calendario(selecao, dia or date.today() + timedelta(days=1), atualizar_horarios)
        calendario.pack(side="left")

        resumo = tk.StringVar()
        ttk.Label(self.corpo, textvariable=resumo, wraplength=520).pack(anchor="w", pady=(0, 5))

        def horas_da_duracao():
            horas = Decimal(duracao.get().strip().replace(",", "."))
            if not horas.is_finite() or not 1 <= horas < 24 or horas != horas.to_integral_value():
                raise ValueError("Informe uma duração em horas inteiras (1, 2, 3…).")
            return int(horas)

        def periodo_escolhido():
            inicio = datetime.combine(calendario.dia, ler_hora(horario.get()))
            if inicio.minute != 0:
                raise ValueError("Escolha um horário cheio, com :00 no final.")
            return inicio, inicio + timedelta(hours=horas_da_duracao())

        def prever(*_):
            try:
                inicio, fim = periodo_escolhido()
            except (ValueError, InvalidOperation):
                resumo.set("")
                return
            if self.sistema.consultar_disponibilidade(quadra, inicio, fim, ignorar=anterior):
                valor = f"{inicio:%d/%m} · {inicio:%H:%M}–{fim:%H:%M} · {reais(quadra.calcular_valor(inicio, fim))}"
                if not anterior and pagamento.get() == "Rateado":
                    valor += " · Rateio após conclusão"
                resumo.set(valor)
            else:
                resumo.set("O horário escolhido não está livre pela duração informada.")

        horario.trace_add("write", prever)

        def mudar_duracao(*_):
            atualizar_horarios(calendario.dia)
            prever()

        duracao.trace_add("write", mudar_duracao)
        pagamento.trace_add("write", prever)
        atualizar_horarios(calendario.dia)
        if anterior and f"{anterior.inicio:%H:%M}" in horas.cget("values"):
            horario.set(f"{anterior.inicio:%H:%M}")
        prever()

        def reservar(sistema, autor):
            inicio, fim = periodo_escolhido()
            if anterior:
                sistema.reagendar_reserva(autor, por_id(sistema.reservas, anterior.id), inicio, fim)
                self.reserva_em_foco = anterior.id
                return "Reserva reagendada."
            reserva = sistema.criar_reserva(autor, por_id(sistema.quadras, codigo), inicio, fim,
                                            pagamento.get().lower())
            self.reserva_em_foco = reserva.id
            return f"Reserva {reserva.id} confirmada. Total de {reais(reserva.valor_total)}."

        botoes = ttk.Frame(self.corpo)
        botoes.pack(fill="x")
        nome = "Confirmar reagendamento" if anterior else "Confirmar reserva"
        self.botao(botoes, nome, lambda: self.gravar(reservar, "Reservas"), ativo=True)
        self.botao(botoes, "Voltar", self.atualizar)

    def reservas(self, diaria=False, filtro="Todas"):
        for widget in self.corpo.winfo_children():
            widget.destroy()
        titulo = "Hoje nas minhas quadras" if diaria else "Reservas"
        ttk.Label(self.corpo, text=titulo, style="Titulo.TLabel").pack(anchor="w", pady=(0, 7))
        reservas = self.sistema.consultar_reservas(self.usuario)
        agora = datetime.now()
        filtros = ttk.Frame(self.corpo)
        filtros.pack(fill="x", pady=(0, 7))
        opcoes = ("Todas", "A concluir") if diaria else ("Todas", "Próximas", "A pagar", "Histórico")
        for nome in opcoes:
            self.botao(filtros, nome, lambda n=nome: self.reservas(diaria, n),
                       estilo="Aba.TButton" if nome == filtro else None)

        if diaria:
            agora_data = agora.date()
            bloqueios = [(q, b) for q in self.sistema.consultar_quadras(self.usuario)
                         for b in q.agenda.bloqueios
                         if b.inicio.date() <= agora_data <= b.fim_efetivo.date()
                         and b.fim_efetivo > datetime.now(b.inicio.tzinfo)]
            if bloqueios:
                nomes = ", ".join(dict.fromkeys(q.nome for q, _ in bloqueios))
                ttk.Label(self.corpo, text=f"Interdições de hoje · {nomes}", wraplength=525).pack(anchor="w", pady=(0, 7))
            reservas = [r for r in reservas if r.inicio.date() == agora_data
                        or r.status == StatusReserva.ATIVA and r.fim <= datetime.now(r.fim.tzinfo)]
        if filtro == "Próximas":
            reservas = [r for r in reservas if r.status == StatusReserva.ATIVA
                        and r.inicio > datetime.now(r.inicio.tzinfo)]
        elif filtro == "Histórico":
            reservas = [r for r in reservas if r.status != StatusReserva.ATIVA]
        elif filtro == "A concluir":
            reservas = [r for r in reservas if r.status == StatusReserva.ATIVA
                        and r.fim <= datetime.now(r.fim.tzinfo)]
        elif filtro == "A pagar":
            pagos = {p.reserva for p in self.sistema.pagamentos if p.pagador == self.usuario
                     and p.status == StatusPagamento.PAGO}
            reservas = [r for r in reservas if r not in pagos and (
                (r.metodo_pagamento == "rateado" and r.status == StatusReserva.CONCLUIDA
                 and self.usuario in r.partida.participantes)
                or (r.status == StatusReserva.ATIVA and r.metodo_pagamento != "rateado"
                    and r.responsavel == self.usuario))]
        reservas.sort(key=lambda r: r.inicio.timestamp(), reverse=not diaria and filtro != "Próximas")
        acoes = self.lista((r.id, f"  {r.quadra.nome}  ·  {r.inicio:%d/%m às %H:%M}–{r.fim:%H:%M}"
                            f"  ·  {r.status.value}  ·  {reais(r.valor_total)}") for r in reservas)
        cartao = ttk.Frame(self.corpo, padding=(9, 6), style="Painel.TFrame")
        cartao.pack(fill="x", before=acoes, pady=(6, 0))
        detalhe = ttk.Label(cartao, wraplength=520, justify="left", style="Painel.TLabel")
        detalhe.pack(anchor="w")
        if self.reserva_em_foco in self.itens:
            indice = tuple(self.itens).index(self.reserva_em_foco)
            self.registros.selection_clear(0, "end")
            self.registros.selection_set(indice)
            self.registros.see(indice)
            self.reserva_em_foco = None
        botoes = {}
        if isinstance(self.usuario, (Supervisor, Atleta)):
            botoes["cancelar"] = self.botao(acoes, "Cancelar reserva", self.cancelar_reserva)
        if isinstance(self.usuario, Supervisor):
            botoes["concluir"] = self.botao(acoes, "Concluir", self.concluir_reserva, ativo=True)
            botoes["material"] = self.botao(acoes, "Entregar material", self.entregar_material)
        if isinstance(self.usuario, Atleta):
            botoes["pagar"] = self.botao(acoes, "Pagar", self.pagar_reserva, ativo=True)
            botoes["rateio"] = self.botao(acoes, "Ver parcelas", self.ver_parcelas)
            botoes["reagendar"] = self.botao(acoes, "Reagendar", self.reagendar_reserva)

        def mostrar_detalhes(evento=None):
            selecao = self.registros.curselection()
            habilitados = set()
            if selecao:
                r = reservas[selecao[0]]
                agora = datetime.now(r.fim.tzinfo)
                ativa = r.status == StatusReserva.ATIVA
                concluida = r.status == StatusReserva.CONCLUIDA
                if ativa and r.inicio - agora >= timedelta(hours=2) and self.usuario in (r.responsavel, r.quadra.supervisor):
                    habilitados.add("cancelar")
                if ativa and r.inicio > agora and self.usuario == r.responsavel:
                    habilitados.add("reagendar")
                if ativa and r.fim <= agora:
                    habilitados.add("concluir")
                participantes = ", ".join(a.nome for a in r.partida.participantes)
                texto = f"{r.quadra.nome} · {r.inicio:%d/%m, %H:%M}–{r.fim:%H:%M} · {reais(r.valor_total)}"
                texto += f"\nParticipantes: {participantes}"
                pedidos = [p for p in r.solicitacoes if p.status == StatusSolicitacao.SOLICITADA]
                emprestados = [p for p in r.solicitacoes if p.status == StatusSolicitacao.FORNECIDA]
                if ativa and pedidos:
                    habilitados.add("material")
                    texto += f" · {len(pedidos)} pedido(s) para entregar"
                if emprestados:
                    texto += f" · {len(emprestados)} pedido(s) entregue(s)"
                if r.status == StatusReserva.CANCELADA:
                    estornados = [p for p in self.sistema.pagamentos if p.reserva == r
                                  and p.pagador == self.usuario and p.status == StatusPagamento.ESTORNADO]
                    texto += " · Cancelada"
                    if estornados:
                        texto += f" · {reais(sum(p.valor for p in estornados))} estornados"
                elif r.metodo_pagamento == "rateado":
                    texto += " · Rateio liberado após a conclusão" if not concluida else " · Rateio disponível"
                    if concluida:
                        habilitados.add("rateio")
                        if self.usuario in r.partida.participantes:
                            habilitados.add("pagar")
                elif ativa and self.usuario == r.responsavel:
                    habilitados.add("pagar")
                if any(p.reserva == r and p.pagador == self.usuario and p.status == StatusPagamento.PAGO
                       for p in self.sistema.pagamentos):
                    habilitados.discard("pagar")
                    texto += " · Você já pagou"
                detalhe.configure(text=texto)
            for nome, botao in botoes.items():
                botao.state(["!disabled" if nome in habilitados else "disabled"])

        self.registros.bind("<<ListboxSelect>>", mostrar_detalhes)
        mostrar_detalhes()

    def entregar_material(self):
        from main import SelecaoCancelada
        codigo = self.selecionado("uma reserva")
        reserva = por_id(self.sistema.reservas, codigo)
        pedidos = [p for p in reserva.solicitacoes if p.status == StatusSolicitacao.SOLICITADA]
        try:
            pedido = DialogoDeAcao(self.janela, "Entregar material").escolher(
                pedidos, lambda p: f"{p.quantidade} × {p.equipamento.nome}")
        except SelecaoCancelada:
            return

        def fornecer(sistema, autor):
            atual = por_id(sistema.reservas, codigo)
            sistema.fornecer_equipamento(autor, atual, por_id(atual.solicitacoes, pedido.id))
            return "Entrega registrada."
        self.gravar(fornecer)

    def reagendar_reserva(self):
        reserva = por_id(self.sistema.reservas, self.selecionado("uma reserva"))
        if reserva.responsavel != self.usuario:
            raise PermissionError("Somente o responsável pode reagendar.")
        self.form_reserva(reserva.quadra.id, reserva.inicio.date(), reserva)

    def concluir_reserva(self):
        codigo = self.selecionado("uma reserva")
        if messagebox.askyesno("Concluir reserva", "Confirmar o fim da reserva?", parent=self.janela):
            def concluir(sistema, autor):
                sistema.concluir_reserva(autor, por_id(sistema.reservas, codigo))
                return "Reserva concluída."
            self.gravar(concluir)

    def pagar_reserva(self):
        codigo = self.selecionado("uma reserva")
        reserva = por_id(self.sistema.reservas, codigo)
        integral = reserva.metodo_pagamento != "rateado"
        valor = (reserva.valor_total if integral
                 else self.sistema.calcular_rateio(reserva)[self.usuario.id])
        if messagebox.askyesno("Pagar reserva", f"Debitar {reais(valor)} da carteira?", parent=self.janela):
            def pagar(sistema, autor):
                pagamento = sistema.pagar_reserva(autor, por_id(sistema.reservas, codigo), integral=integral)
                return f"Pagamento de {reais(pagamento.valor)} confirmado."
            self.gravar(pagar)

    def ver_parcelas(self):
        reserva = por_id(self.sistema.reservas, self.selecionado("uma reserva"))
        parcelas = self.sistema.calcular_rateio(reserva)
        messagebox.showinfo("Parcelas", "\n".join(f"{a.nome} · {reais(parcelas[a.id])}"
                                                for a in reserva.partida.participantes), parent=self.janela)

    def repasses(self, historico=False):
        for widget in self.corpo.winfo_children():
            widget.destroy()
        ttk.Label(self.corpo, text="Repasses", style="Titulo.TLabel").pack(anchor="w", pady=(0, 7))
        filtros = ttk.Frame(self.corpo)
        filtros.pack(fill="x", pady=(0, 7))
        self.botao(filtros, "A repassar", self.repasses, estilo="Aba.TButton" if not historico else None)
        self.botao(filtros, "Histórico", lambda: self.repasses(True), estilo="Aba.TButton" if historico else None)
        if historico:
            self.lista((r.id, f"  {r.efetuado_em:%d/%m/%Y} · {r.supervisor.nome} · "
                              f"{len(r.reservas)} reserva(s) · {reais(r.valor)}")
                       for r in reversed(self.sistema.repasses))
            return

        prontas = self.sistema.consultar_reservas_para_repasse(self.usuario)
        grupos = {}
        for reserva in prontas:
            grupos.setdefault(reserva.quadra.supervisor, []).append(reserva)
        if not grupos:
            ttk.Label(self.corpo, text="Nenhuma reserva aguarda repasse.").pack(anchor="w")
            return

        ttk.Label(filtros, text="Supervisor").pack(side="left", padx=(8, 4))
        responsavel = ttk.Combobox(filtros, state="readonly", width=22,
                                   values=[f"{u.nome} · {u.email}" for u in grupos])
        responsavel.pack(side="left", fill="x", expand=True)
        responsavel.current(0)
        total = tk.StringVar()
        rodape = ttk.Label(self.corpo, textvariable=total)
        rodape.pack(side="bottom", anchor="w")
        acoes = self.lista([])
        self.registros.configure(selectmode="extended")
        atuais = []

        def selecionadas():
            return [atuais[i] for i in self.registros.curselection()]

        def atualizar_total(evento=None):
            lote = selecionadas()
            total.set(f"{len(lote)} selecionada(s) · {reais(sum(r.valor_total for r in lote))}")
            botao.state(["!disabled" if lote else "disabled"])

        def carregar_lote(evento=None):
            atuais[:] = grupos[tuple(grupos)[responsavel.current()]]
            self.itens = {r.id: f"  {r.quadra.nome} · {r.inicio:%d/%m às %H:%M} · {reais(r.valor_total)}"
                          for r in atuais}
            self.registros.delete(0, "end")
            for descricao in self.itens.values():
                self.registros.insert("end", descricao)
            self.registros.selection_set(0)
            self.status.set("")
            atualizar_total()

        def repassar():
            lote = selecionadas()
            supervisor = lote[0].quadra.supervisor
            valor = sum(r.valor_total for r in lote)
            if messagebox.askyesno("Confirmar repasse", f"Repassar {reais(valor)} a {supervisor.nome}?",
                                   parent=self.janela):
                codigos = [r.id for r in lote]

                def efetuar(sistema, autor):
                    reservas = [por_id(sistema.reservas, codigo) for codigo in codigos]
                    repasse = sistema.efetuar_repasse(autor, reservas[0].quadra.supervisor, reservas)
                    return f"Repasse de {reais(repasse.valor)} efetuado."
                self.gravar(efetuar)

        botao = self.botao(acoes, "Efetuar repasse", repassar, ativo=True)
        self.botao(acoes, "Selecionar todas", lambda: (self.registros.selection_set(0, "end"), atualizar_total()))
        self.registros.bind("<<ListboxSelect>>", atualizar_total)
        responsavel.bind("<<ComboboxSelected>>", carregar_lote)
        carregar_lote()

    def cancelar_reserva(self):
        codigo = self.selecionado("uma reserva")
        if not messagebox.askyesno("Cancelar reserva", f"Cancelar a reserva {codigo}?", parent=self.janela):
            return

        def cancelar(sistema, autor):
            sistema.cancelar_reserva(autor, por_id(sistema.reservas, codigo))
            return f"Reserva {codigo} cancelada."

        self.gravar(cancelar)


def abrir_janela(banco, simular=False):
    janela = tk.Tk()
    InterfaceReservas(janela, banco, simular)
    janela.mainloop()
