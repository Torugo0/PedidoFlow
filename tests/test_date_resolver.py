from datetime import date

import pytest

from pedidoflow import DateResolutionError, DateResolver


REFERENCIA = date(2026, 10, 14)  # quarta-feira


def test_sexta_e_resolvida_para_data_exata_e_pede_confirmacao():
    resolucao = DateResolver().resolve("sexta", REFERENCIA)

    assert resolucao.data == date(2026, 10, 16)
    assert resolucao.data_iso == "2026-10-16"
    assert resolucao.requer_confirmacao is True
    assert "sexta-feira, 16/10/2026" in resolucao.pergunta_confirmacao


def test_dia_da_semana_igual_ao_atual_significa_proxima_ocorrencia():
    resolucao = DateResolver().resolve("sexta", date(2026, 10, 16))

    assert resolucao.data == date(2026, 10, 23)
    assert resolucao.requer_confirmacao is True


@pytest.mark.parametrize(
    ("texto", "esperada"),
    [
        ("hoje", date(2026, 10, 14)),
        ("amanhã", date(2026, 10, 15)),
        ("depois de amanhã", date(2026, 10, 16)),
        ("próxima terça-feira", date(2026, 10, 20)),
    ],
)
def test_expressoes_relativas(texto, esperada):
    resolucao = DateResolver().resolve(texto, REFERENCIA)

    assert resolucao.data == esperada
    assert resolucao.requer_confirmacao is True


def test_data_explicita_valida_nao_e_tratada_como_ambigua():
    resolucao = DateResolver().resolve("20/10/2026", REFERENCIA)

    assert resolucao.data_iso == "2026-10-20"
    assert resolucao.requer_confirmacao is False
    assert resolucao.pergunta_confirmacao is None


def test_data_no_passado_e_rejeitada():
    with pytest.raises(DateResolutionError, match="passado"):
        DateResolver().resolve("13/10/2026", REFERENCIA)


def test_data_inexistente_e_rejeitada():
    with pytest.raises(DateResolutionError, match="nao existe"):
        DateResolver().resolve("31/02/2027", REFERENCIA)


@pytest.mark.parametrize(
    "texto",
    [
        "sexta de manhã",
        "quarta-feira às 15h",
        "sexta às 3 da tarde",
        "amanhã à tarde",
        "25/10/2026 14:30",
    ],
)
def test_rejeita_horario_para_nao_descartar_informacao_silenciosamente(texto):
    with pytest.raises(DateResolutionError, match="Horarios"):
        DateResolver().resolve(texto, REFERENCIA)


def test_data_com_mes_por_extenso():
    resolucao = DateResolver().resolve("dia 22 de outubro", REFERENCIA)

    assert resolucao.data == date(2026, 10, 22)
    assert resolucao.requer_confirmacao is False


def test_intervalo_com_numero_por_extenso():
    resolucao = DateResolver().resolve("daqui a três dias", REFERENCIA)

    assert resolucao.data == date(2026, 10, 17)
    assert resolucao.requer_confirmacao is True
