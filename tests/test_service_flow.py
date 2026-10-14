from datetime import date

import pytest

from pedidoflow import Acao, PedidoService, SQLiteRepository, ToolCall


REFERENCIA = date(2026, 10, 14)


def criar_service() -> PedidoService:
    return PedidoService(SQLiteRepository(":memory:"))


def chamada_criacao() -> ToolCall:
    return ToolCall(
        acao=Acao.CRIAR_PEDIDO,
        argumentos={
            "cliente": "Mercado Central",
            "itens": [
                {"produto": "café", "quantidade": 2, "unidade": "caixa"}
            ],
            "endereco_entrega": "Av. Brasil, 500",
            "prazo_texto": "sexta",
        },
    )


def test_analise_resolve_data_mas_nao_altera_banco_antes_da_confirmacao():
    service = criar_service()
    estoque_antes = next(
        produto.estoque
        for produto in service.listar_catalogo()
        if produto.nome.casefold().startswith("caf")
    )

    preview = service.analisar(chamada_criacao(), REFERENCIA)

    assert preview.pode_executar is True
    assert preview.requer_confirmacao is True
    assert preview.argumentos["data_entrega"] == "2026-10-16"
    assert "sexta-feira, 16/10/2026" in preview.pergunta_confirmacao
    assert service.listar_pedidos() == []
    estoque_depois = next(
        produto.estoque
        for produto in service.listar_catalogo()
        if produto.nome.casefold().startswith("caf")
    )
    assert estoque_depois == estoque_antes


def test_confirmacao_cria_pedido_e_atualiza_estoque_uma_unica_vez():
    service = criar_service()
    preview = service.analisar(chamada_criacao(), REFERENCIA)

    resultado = service.confirmar(preview)

    assert resultado.sucesso is True
    assert resultado.protocolo.startswith("PED-")
    assert len(service.listar_pedidos()) == 1
    assert service.listar_pedidos()[0].data_entrega == date(2026, 10, 16)
    estoque = next(
        produto.estoque
        for produto in service.listar_catalogo()
        if produto.nome.casefold().startswith("caf")
    )
    assert estoque == 48

    repeticao = service.confirmar(preview)
    assert repeticao.sucesso is False
    assert len(service.listar_pedidos()) == 1


def test_campos_faltantes_impedem_execucao():
    service = criar_service()
    incompleta = ToolCall(
        acao=Acao.CRIAR_PEDIDO,
        argumentos={"itens": [{"produto": "café", "quantidade": 1}]},
        campos_faltantes=["cliente", "endereco_entrega", "prazo_texto"],
    )

    preview = service.analisar(incompleta, REFERENCIA)

    assert preview.pode_executar is False
    assert preview.requer_confirmacao is False
    assert "cliente" in " ".join(preview.erros).casefold()
    resultado = service.confirmar(preview)
    assert resultado.sucesso is False


def test_consulta_nao_exige_confirmacao_de_efeito_colateral():
    service = criar_service()
    criacao = service.analisar(chamada_criacao(), REFERENCIA)
    service.confirmar(criacao)
    consulta = service.analisar(
        ToolCall(
            acao=Acao.CONSULTAR_PEDIDO,
            argumentos={"numero_pedido": 1},
        ),
        REFERENCIA,
    )

    assert consulta.pode_executar is True
    assert consulta.requer_confirmacao is False
    resultado = service.confirmar(consulta)
    assert resultado.sucesso is True
    assert resultado.dados["pedido"]["numero_pedido"] == 1


def test_alteracao_e_cancelamento_exigem_confirmacao_e_repoem_estoque():
    service = criar_service()
    service.confirmar(service.analisar(chamada_criacao(), REFERENCIA))

    alteracao = service.analisar(
        ToolCall(
            acao=Acao.ALTERAR_ENTREGA,
            argumentos={
                "numero_pedido": 1,
                "novo_endereco": "Rua das Flores, 120",
                "novo_prazo_texto": "próxima terça",
            },
        ),
        REFERENCIA,
    )
    assert alteracao.pode_executar is True
    assert alteracao.requer_confirmacao is True
    assert alteracao.argumentos["nova_data_entrega"] == "2026-10-20"
    assert service.confirmar(alteracao).sucesso is True

    cancelamento = service.analisar(
        ToolCall(
            acao=Acao.CANCELAR_PEDIDO,
            argumentos={"numero_pedido": 1, "motivo": "pedido duplicado"},
        ),
        REFERENCIA,
    )
    assert cancelamento.requer_confirmacao is True
    assert service.confirmar(cancelamento).sucesso is True
    assert service.listar_pedidos()[0].status.value == "cancelado"

    estoque = next(
        produto.estoque
        for produto in service.listar_catalogo()
        if produto.nome.casefold().startswith("caf")
    )
    assert estoque == 50


def test_argumentos_da_preview_nao_podem_adulterar_execucao_confirmada():
    service = criar_service()
    preview = service.analisar(chamada_criacao(), REFERENCIA)
    preview.argumentos["cliente"] = "Cliente adulterado"

    resultado = service.confirmar(preview.token)

    assert resultado.sucesso is True
    assert service.listar_pedidos()[0].cliente == "Mercado Central"


def test_unidade_incompativel_e_bloqueada_em_vez_de_ser_trocada_silenciosamente():
    service = criar_service()
    chamada = chamada_criacao()
    chamada.argumentos["itens"][0]["unidade"] = "pacote"

    preview = service.analisar(chamada, REFERENCIA)

    assert preview.pode_executar is False
    assert "unidade incompativel" in " ".join(preview.erros).casefold()
    assert service.listar_pedidos() == []


def test_item_malformado_da_llm_vira_erro_estruturado_sem_excecao():
    service = criar_service()
    chamada = chamada_criacao()
    chamada.argumentos["itens"] = ["café"]

    preview = service.analisar(chamada, REFERENCIA)

    assert preview.pode_executar is False
    assert "cada item deve ser um objeto" in " ".join(preview.erros).casefold()


@pytest.mark.parametrize("numero", [1.9, "1.9", True, 0, -1])
def test_numero_de_pedido_nao_e_coagido_para_outro_id(numero):
    service = criar_service()
    service.confirmar(service.analisar(chamada_criacao(), REFERENCIA))

    preview = service.analisar(
        ToolCall(
            acao=Acao.CANCELAR_PEDIDO,
            argumentos={"numero_pedido": numero, "motivo": "duplicidade"},
        ),
        REFERENCIA,
    )

    assert preview.pode_executar is False
    assert service.listar_pedidos()[0].status.value == "criado"
