
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

- `main.py`: execução e demonstração do sistema.
- `modelos.py`: classes e regras de negócio.
- `servicos.py`: gerenciamento das operações do sistema.
- `enums.py`: enumerações e estados.
- `testes.py`: testes automatizados.

## Como executar

Execute o sistema pelo terminal:

```bash
py main.py
```

## Como executar os testes

```bash
py -m unittest testes.py
```

## Resultado dos testes

O projeto possui 11 testes automatizados, verificando permissões, reservas, conflitos de horários, carteira e créditos.

## Desenvolvido para fins acadêmicos.
