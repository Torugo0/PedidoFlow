from types import SimpleNamespace

import app


def _pedido_para_sexta():
    return app.ToolCall.model_validate(
        {
            "acao": "criar_pedido",
            "argumentos": {
                "cliente": "Mercado Central",
                "itens": [
                    {"produto": "café", "quantidade": 2, "unidade": "caixa"}
                ],
                "endereco_entrega": "Avenida Brasil, 500",
                "prazo_texto": "sexta",
            },
            "campos_faltantes": [],
        }
    )


def test_frontend_gradio_pode_ser_montado_sem_carregar_modelo():
    demo = app.create_app(
        service=app.PedidoService(app.SQLiteRepository(":memory:")),
        interpreter=app.OrderInterpreter(force_fallback=True),
    )

    assert demo.__class__.__name__ == "Blocks"
    assert app._hoje().isoformat() >= "2026-10-14"


def test_estado_da_tela_preserva_a_data_exata_que_foi_confirmada():
    service = app.PedidoService(app.SQLiteRepository(":memory:"))
    tool_call = _pedido_para_sexta()
    preview = service.analisar(tool_call, data_referencia="2026-10-14")

    estado = app._estado_da_preview(tool_call, preview)
    restaurada = app._preview_do_estado(estado)

    assert restaurada.argumentos["data_entrega"] == "2026-10-16"
    assert restaurada.pergunta_confirmacao.startswith(
        "Você quis dizer sexta-feira, 16/10/2026?"
    )
    assert restaurada.token == preview.token


def test_titulo_de_confirmacao_distingue_data_de_outra_operacao():
    service = app.PedidoService(app.SQLiteRepository(":memory:"))
    preview_data = service.analisar(_pedido_para_sexta(), "2026-10-14")

    revisao = app._confirmacao_markdown(preview_data)

    assert "### Confira o pedido" in revisao
    assert "Mercado Central" in revisao
    assert "Avenida Brasil, 500" in revisao
    assert "sexta-feira, 16/10/2026" in revisao
    assert "prazo_texto" not in revisao
    assert app._rotulo_botao(preview_data) == "Confirmar data e criar pedido"


def test_banco_em_arquivo_e_criado_automaticamente(tmp_path):
    caminho = tmp_path / "dados" / "pedidoflow.db"
    repositorio = app.SQLiteRepository(caminho)
    try:
        service = app.PedidoService(repositorio)
        assert caminho.exists()
        assert len(service.listar_catalogo()) == 10
    finally:
        repositorio._connection.close()


def test_resultado_de_consulta_mostra_status_sem_json():
    resultado = SimpleNamespace(
        sucesso=True,
        mensagem="Pedido 1 localizado.",
        protocolo=None,
        erros=[],
        dados={
            "pedido": {
                "numero_pedido": 1,
                "cliente": "Mercado Central",
                "status": "criado",
                "data_entrega": "2026-10-16",
                "total": 42.5,
            }
        },
    )

    mensagem = app._resultado_markdown(resultado)

    assert "**Status:** Criado" in mensagem
    assert "```json" not in mensagem


def test_resultado_sem_sucesso_nao_diz_que_operacao_foi_concluida():
    resultado = SimpleNamespace(
        sucesso=False,
        mensagem="Pedido não encontrado.",
        protocolo=None,
        erros=[],
        dados={},
    )

    assert "Operação não concluída" in app._resultado_markdown(resultado)
