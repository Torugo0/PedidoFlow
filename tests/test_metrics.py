from training.metrics import is_schema_valid


def test_schema_valido_aceita_chamada_completa_e_parcial_coerente():
    assert is_schema_valid(
        {
            "acao": "criar_pedido",
            "argumentos": {
                "cliente": "Mercado Central",
                "itens": [
                    {"produto": "café", "quantidade": 2, "unidade": "caixa"}
                ],
                "endereco_entrega": "Rua A, 10",
                "prazo_texto": "sexta",
            },
            "campos_faltantes": [],
        }
    )
    assert is_schema_valid(
        {
            "acao": "consultar_pedido",
            "argumentos": {},
            "campos_faltantes": ["numero_pedido"],
        }
    )


def test_schema_valido_rejeita_tipos_e_valores_que_o_servico_nao_executa():
    assert not is_schema_valid(
        {
            "acao": "criar_pedido",
            "argumentos": {
                "cliente": 123,
                "itens": [
                    {"produto": "", "quantidade": -7, "unidade": ""}
                ],
                "endereco_entrega": False,
                "prazo_texto": [],
            },
            "campos_faltantes": [],
        }
    )
    assert not is_schema_valid(
        {
            "acao": "cancelar_pedido",
            "argumentos": {"numero_pedido": -1, "motivo": 9},
            "campos_faltantes": [],
        }
    )


def test_schema_valido_rejeita_campos_faltantes_incoerentes():
    assert not is_schema_valid(
        {
            "acao": "consultar_pedido",
            "argumentos": {"numero_pedido": 10},
            "campos_faltantes": ["numero_pedido"],
        }
    )
    assert not is_schema_valid(
        {
            "acao": "alterar_entrega",
            "argumentos": {"numero_pedido": 10, "novo_endereco": "Rua A, 10"},
            "campos_faltantes": ["novo_endereco"],
        }
    )
