
# Sistema de Reservas de Quadras

## Sobre o projeto

Sistema desenvolvido em Python para gerenciamento de reservas de quadras esportivas.

O sistema permite cadastrar usuários, administrar quadras, configurar horários de funcionamento, realizar reservas, organizar partidas, controlar créditos e pagamentos.

## Funcionalidades

- Cadastro de administradores, supervisores e atletas.
- Gerenciamento de quadras esportivas.
- Configuração de horários e bloqueios.
- Criação, cancelamento e reagendamento de reservas.
- Organização de partidas públicas e privadas.
- Participação de atletas nas partidas.
- Solicitação e fornecimento de equipamentos.
- Compra e controle de créditos.
- Pagamentos e repasses.
- Registro de denúncias.

## Tecnologias utilizadas

- Python 3
- Tkinter e ttk para a interface gráfica
- SQLite para armazenar os cadastros e as reservas
- Programação Orientada a Objetos (POO)
- Enum
- ABC e métodos abstratos
- Encapsulamento e propriedades
- Polimorfismo
- Testes automatizados com unittest

## Organização dos arquivos

- `main.py` inicia o sistema pelo terminal ou em uma janela.
- `interface.py` organiza os formulários, os botões e as listas da janela.
- `armazenamento.py` guarda a sessão em SQLite e verifica as senhas.
- `modelos.py`: classes e regras de negócio.
- `servicos.py`: gerenciamento das operações do sistema.
- `enums.py`: enumerações e estados.
- `testes.py`: testes automatizados.

## Como executar

### Interface gráfica em Tkinter

No Windows, abra a pasta do projeto no VS Code. No terminal integrado, execute um dos comandos abaixo com Python 3 e Tkinter instalados.

| Modo | Comando | Dados |
| --- | --- | --- |
| Uso normal | `py main.py --gui` | Compartilha o banco SQLite com o modo terminal. Cadastros e reservas ficam disponíveis ao reabrir o programa. No primeiro acesso, cadastre o administrador. |
| Demonstração | `py main.py --simular` | Começa com contas, quadra e reservas de exemplo. Ao fechar a janela, os dados dessa sessão são descartados. |

O administrador lista os usuários e cadastra supervisores. O supervisor cadastra, lista, edita e exclui suas quadras. Uma quadra com histórico de reservas é desativada ao ser excluída. O atleta pode criar sua conta, consultar a agenda, reservar um horário e cancelar uma reserva sua.

**Demonstração pela janela**

1. Abra a demonstração e clique em **Ana** na tela de login.
2. Em **Quadras**, selecione **Central** e clique em **Ver agenda**. Na linha de amanhã, o período das 18h às 19h já está ocupado. Selecione essa linha e clique em **Reservar neste dia**.
3. Selecione amanhã, informe duração de `1` hora e escolha `19:00` entre os horários disponíveis. Escolha **Integral** e clique em **Confirmar reserva**.
4. Em **Reservas**, selecione a nova reserva de Ana, clique em **Cancelar reserva** e confirme. A situação passa a **Cancelada**. Volte a **Quadras**, selecione **Central** e abra **Ver agenda** para conferir a liberação das 19h às 20h.

Os formulários agrupam campos `Entry`, rótulos `Label` e botões `Button` em um `Frame`. Ao reservar, a janela lê os campos e chama `SistemaReservas.criar_reserva`. O serviço verifica a disponibilidade, cria um objeto `Reserva` e calcula o valor. A operação concluída é gravada em SQLite e a janela mostra o resultado. Se o modelo recusar o horário, a janela exibe o erro.

### Terminal

Na pasta do projeto, execute no terminal integrado do VS Code:

```powershell
py main.py
```

**Opção 1 — sistema com dados salvos.** No primeiro acesso, cadastre o administrador e entre com e-mail e senha. O administrador cadastra supervisores. O atleta cria sua conta na tela de entrada. O supervisor cadastra a quadra e informa os horários de funcionamento. No Windows, os dados ficam em `%LOCALAPPDATA%\SistemaReservasQuadras\reservas.sqlite3`.

**Opção 2 — simulação para apresentação.** Abre a tela de login gráfica com um cenário em memória com uma quadra aberta todos os dias das 8h às 22h e três bolas. Você pode entrar nas contas preparadas ou criar outras. Para abrir a simulação diretamente, execute `py main.py --simular`. A cada nova simulação o cenário recomeça.

**Opção 3 — interface gráfica.** Abre a janela com os dados salvos, assim como `py main.py --gui`.

| Perfil | E-mail de demonstração | Senha de demonstração |
| --- | --- | --- |
| Administrador | admin@demo | quadra |
| Supervisora Bia | bia@demo | quadra |
| Atleta Ana | ana@demo | quadra |
| Atleta Léo | leo@demo | quadra |

### Roteiro da demonstração por perfil

1. Entre como **Léo**, abra **Partidas**, selecione a reserva **2** e clique em **Entrar na partida**. A partida é privada e Ana já o convidou.
2. Entre como **Ana** e solicite uma bola para a reserva **2**. Entre como **Bia** e forneça o equipamento. Na agenda da Central, confira que a reserva ocupa amanhã das 18h às 19h.
3. O cálculo e a cobrança do rateio ficam disponíveis depois que o horário termina e Bia seleciona a reserva e clica em **Concluir**, na aba **Reservas**. Com Ana e Léo na reserva **2**, a parcela de cada um é de R$ 50.
4. Para demonstrar um repasse sem esperar pelo horário da reserva **2**, entre como **administrador**. Na aba **Repasses**, selecione a reserva **1**, que já está paga e concluída, e clique em **Efetuar repasse**.

### Consulta de disponibilidade

A opção **6** do supervisor e a opção **1** do atleta mostram os horários livres da quadra de hoje até o sexto dia seguinte. Havendo várias quadras, escolha uma pelo ID. A agenda considera o funcionamento, as reservas ativas e as interdições.

- Digite `amanhã`, `segunda` ou uma data em `DD/MM/AAAA` para ver um único dia.
- Digite `14 dias` para ver duas semanas a partir de hoje, ou informe duas datas no formato `DD/MM/AAAA a DD/MM/AAAA`.
- Como atleta, depois de escolher um dia, você pode digitar outro período, pressionar **Enter** para voltar ou informar a hora de início para fazer uma reserva.

Para reabrir uma quadra, o supervisor usa a opção **8 — Disponibilizar quadra e retirar interdições**. A ação encerra tanto as interdições em vigor quanto as agendadas para essa quadra. Os horários liberados podem ser reservados novamente. As reservas canceladas e os estornos continuam no histórico.

Em **Registrar denúncia**, o supervisor pode selecionar atletas ou outros supervisores. O administrador fica fora dessa lista. A avaliação de atletas foi retirada do menu de supervisão.

## Como executar os testes

```powershell
py -m unittest -v testes
```

A suíte exercita os serviços e os menus do terminal, incluindo cadastro, login, agenda, reabertura de quadras, permissões de denúncia, reservas, pagamentos, equipamentos e repasses. Quando o Tkinter pode abrir uma janela, um teste também aciona os botões de login e reserva e confere tanto a mensagem de recusa para um horário ocupado quanto a confirmação de uma reserva em horário livre.

## Desenvolvido para fins acadêmicos.
