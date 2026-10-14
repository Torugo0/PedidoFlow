from pedidoflow import Acao, ToolCall
from pedidoflow.interpreter import OrderInterpreter, _reconcile_missing_fields


def criar_interpretador() -> OrderInterpreter:
    return OrderInterpreter(force_fallback=True)


def test_cria_pedido_com_varios_itens_sem_inventar_data_iso():
    interpretador = criar_interpretador()

    chamada = interpretador.interpret(
        "Cadastre para o Mercado Central duas caixas de café e cinco pacotes "
        "de açúcar. Entregar na Av. Brasil, 500 até sexta."
    )

    assert chamada.acao == Acao.CRIAR_PEDIDO
    assert chamada.argumentos["cliente"] == "Mercado Central"
    assert chamada.argumentos["itens"] == [
        {"produto": "café", "quantidade": 2, "unidade": "caixa"},
        {"produto": "açúcar", "quantidade": 5, "unidade": "pacote"},
    ]
    assert chamada.argumentos["endereco_entrega"] == "Av. Brasil, 500"
    assert chamada.argumentos["prazo_texto"].casefold() == "sexta"
    assert chamada.campos_faltantes == []
    assert "Fallback determinístico" in interpretador.backend_status


def test_consulta_extrai_numero_do_pedido():
    chamada = criar_interpretador().interpret("Qual o status do pedido nº 1042?")

    assert chamada.acao == Acao.CONSULTAR_PEDIDO
    assert chamada.argumentos == {"numero_pedido": 1042}
    assert chamada.campos_faltantes == []


def test_cancelamento_exige_motivo_e_numero():
    chamada = criar_interpretador().interpret("Cancele o pedido 1042")

    assert chamada.acao == Acao.CANCELAR_PEDIDO
    assert chamada.argumentos == {"numero_pedido": 1042}
    assert chamada.campos_faltantes == ["motivo"]


def test_cancelamento_extrai_motivo():
    chamada = criar_interpretador().interpret(
        "Cancele o pedido 1042 porque foi cadastrado em duplicidade."
    )

    assert chamada.acao == Acao.CANCELAR_PEDIDO
    assert chamada.argumentos["motivo"] == "foi cadastrado em duplicidade"
    assert chamada.campos_faltantes == []


def test_alteracao_extrai_endereco_e_prazo_natural():
    chamada = criar_interpretador().interpret(
        "Altere o endereço do pedido 10 para Rua das Flores, 120 e a entrega "
        "para próxima terça."
    )

    assert chamada.acao == Acao.ALTERAR_ENTREGA
    assert chamada.argumentos["numero_pedido"] == 10
    assert chamada.argumentos["novo_endereco"] == "Rua das Flores, 120"
    assert chamada.argumentos["novo_prazo_texto"].casefold() == "próxima terça"
    assert chamada.campos_faltantes == []


def test_pedido_incompleto_nao_pode_ocultar_campos_faltantes():
    chamada = criar_interpretador().interpret("Quero duas caixas de café.")

    assert chamada.acao == Acao.CRIAR_PEDIDO
    assert chamada.argumentos["itens"][0]["produto"] == "café"
    assert chamada.campos_faltantes == ["cliente", "endereco_entrega", "prazo_texto"]


def test_texto_fora_do_escopo_nao_dispara_uma_ferramenta():
    chamada = criar_interpretador().interpret(
        "Explique de forma simples o que é inteligência artificial."
    )

    assert chamada.acao == Acao.NAO_SUPORTADA
    assert chamada.argumentos == {}


def test_campos_faltantes_da_llm_sao_reconciliados_com_os_argumentos():
    inconsistente = ToolCall(
        acao=Acao.CRIAR_PEDIDO,
        argumentos={
            "cliente": "Mercado Central",
            "itens": [{"produto": "café", "quantidade": 2, "unidade": "caixa"}],
            "endereco_entrega": "Avenida Brasil, 500",
            "prazo_texto": "sexta",
        },
        campos_faltantes=["cliente"],
    )

    reconciliada = _reconcile_missing_fields(inconsistente)

    assert reconciliada.campos_faltantes == []


def test_cliente_nao_inclui_a_preposicao_com_antes_dos_itens():
    chamada = criar_interpretador().interpret(
        "Crie um pedido para Mercado Central com 2 caixas de café, "
        "entrega na Avenida Brasil, 500 até sexta."
    )

    assert chamada.argumentos["cliente"] == "Mercado Central"


def test_numero_no_nome_da_rua_nao_e_inventado_como_prazo():
    chamada = criar_interpretador().interpret(
        "Crie um pedido para Mercado Central com 2 caixas de café, "
        "entrega na Rua 12/10, 50."
    )

    assert "prazo_texto" not in chamada.argumentos
    assert "prazo_texto" in chamada.campos_faltantes


def test_fallback_preserva_horario_para_o_backend_poder_rejeitar():
    chamada = criar_interpretador().interpret(
        "Crie um pedido para Mercado Central com 2 caixas de café, "
        "entrega na Avenida Brasil, 500 até sexta às 3 da tarde."
    )

    assert chamada.argumentos["prazo_texto"] == "sexta às 3 da tarde"

    relativa = criar_interpretador().interpret(
        "Crie um pedido para Mercado Central com 2 caixas de café, "
        "entrega na Avenida Brasil, 500 amanhã à tarde."
    )
    assert relativa.argumentos["prazo_texto"] == "amanhã à tarde"
