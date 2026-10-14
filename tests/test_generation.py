from pedidoflow.generation import is_complete_json_object


def test_detecta_objeto_json_completo_sem_aceitar_texto_extra():
    assert is_complete_json_object('{"acao":"consultar_pedido"}') is True
    assert is_complete_json_object('{"acao":"consultar_pedido"') is False
    assert is_complete_json_object('```json\n{"acao":"consultar_pedido"}\n```') is False
    assert is_complete_json_object('[{"acao":"consultar_pedido"}]') is False
    assert is_complete_json_object('{"numero":NaN}') is False
