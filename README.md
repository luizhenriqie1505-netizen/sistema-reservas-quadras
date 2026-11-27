
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
- Programação Orientada a Objetos (POO)
- Enum
- ABC e métodos abstratos
- Encapsulamento e propriedades
- Polimorfismo
- Testes automatizados com unittest

## Organização dos arquivos

- `main.py` abre os menus de cadastro, login e operações dos três perfis.
- `armazenamento.py` guarda a sessão em SQLite e verifica as senhas.
- `modelos.py`: classes e regras de negócio.
- `servicos.py`: gerenciamento das operações do sistema.
- `enums.py`: enumerações e estados.
- `testes.py`: testes automatizados.

## Como executar

Na pasta do projeto, execute no terminal integrado do VS Code:

```powershell
py main.py
```

**Opção 1 — sistema com dados salvos.** No primeiro acesso, cadastre o administrador e entre com e-mail e senha. O administrador cadastra supervisores. O atleta cria sua conta na tela de entrada. O supervisor cadastra a quadra e informa os horários de funcionamento. No Windows, os dados ficam em `%LOCALAPPDATA%\SistemaReservasQuadras\reservas.sqlite3`.

**Opção 2 — simulação para apresentação.** Inicia um cenário em memória com uma quadra aberta todos os dias das 8h às 22h e três bolas. Você pode entrar nas contas preparadas ou criar outras. Para abrir a simulação diretamente, execute `py main.py --simular`. A cada nova simulação o cenário recomeça.

| Perfil | E-mail de demonstração | Senha de demonstração |
| --- | --- | --- |
| Administrador | admin@demo | quadra |
| Supervisora Bia | bia@demo | quadra |
| Atleta Ana | ana@demo | quadra |
| Atleta Léo | leo@demo | quadra |

### Roteiro para a apresentação

1. Entre como **Léo**, escolha **Entrar em partida ou aceitar convite** e selecione a reserva **2**. A partida é privada e Ana já o convidou. Consulte o rateio: os R$ 100 da reserva agora correspondem a R$ 50 por atleta. Pague a parcela de Léo.
2. Use **0 — Sair da conta** e entre como **Ana**. Pague a outra parcela da reserva **2** e solicite uma bola. Cada pagamento fica associado ao respectivo atleta.
3. Entre como **Bia**. Em **Fornecer equipamento**, selecione a reserva **2** e o pedido. Em **Avaliar atleta**, selecione a reserva **1**, que já foi concluída, e atribua uma nota a Ana.
4. Entre como **administrador**. Em **Pagar supervisor por lote**, selecione Bia e a reserva **1**. Tentar repetir o repasse exibe a recusa do sistema.
5. Para demonstrar o estorno, cancele a reserva **2** como Ana ou Bia e confira as duas carteiras. O cancelamento normal exige pelo menos duas horas de antecedência. Uma interdição cancela e estorna as reservas ativas atingidas mesmo dentro desse prazo.

## Como executar os testes

```powershell
py -m unittest -v testes
```

A suíte exercita os serviços diretamente e também executa o programa pelo terminal, com entradas para cadastro, login, reserva, pagamento, equipamentos, avaliação e repasse.

## Desenvolvido para fins acadêmicos.
