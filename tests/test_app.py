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

    assert "### Confirme a data" in app._confirmacao_markdown(preview_data)
