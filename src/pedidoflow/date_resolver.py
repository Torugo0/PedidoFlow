"""Conversao deterministica de expressoes de data em PT-BR."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta

from .schemas import ResolucaoData


class DateResolutionError(ValueError):
    """Indica que uma data nao pode ser interpretada com seguranca."""


class DateResolver:
    """Resolve datas sem depender da LLM nem do relogio do frontend."""

    _DIAS_SEMANA = {
        "segunda": 0,
        "segunda-feira": 0,
        "terca": 1,
        "terca-feira": 1,
        "quarta": 2,
        "quarta-feira": 2,
        "quinta": 3,
        "quinta-feira": 3,
        "sexta": 4,
        "sexta-feira": 4,
        "sabado": 5,
        "domingo": 6,
    }
    _NOMES_DIAS = (
        "segunda-feira",
        "terca-feira",
        "quarta-feira",
        "quinta-feira",
        "sexta-feira",
        "sabado",
        "domingo",
    )
    _NUMEROS = {
        "um": 1,
        "uma": 1,
        "dois": 2,
        "duas": 2,
        "tres": 3,
        "quatro": 4,
        "cinco": 5,
        "seis": 6,
        "sete": 7,
        "oito": 8,
        "nove": 9,
        "dez": 10,
        "onze": 11,
        "doze": 12,
        "treze": 13,
        "quatorze": 14,
        "catorze": 14,
        "quinze": 15,
    }
    _MESES = {
        "janeiro": 1,
        "fevereiro": 2,
        "marco": 3,
        "abril": 4,
        "maio": 5,
        "junho": 6,
        "julho": 7,
        "agosto": 8,
        "setembro": 9,
        "outubro": 10,
        "novembro": 11,
        "dezembro": 12,
    }

    def resolve(
        self,
        texto: str | date | datetime,
        data_referencia: date | datetime | str | None = None,
    ) -> ResolucaoData:
        referencia = self.normalizar_referencia(data_referencia)
        if isinstance(texto, datetime):
            return self._validar_e_montar(
                texto.date().isoformat(), texto.date(), referencia, relativa=False
            )
        if isinstance(texto, date):
            return self._validar_e_montar(
                texto.isoformat(), texto, referencia, relativa=False
            )
        if not isinstance(texto, str) or not texto.strip():
            raise DateResolutionError("Informe uma data ou prazo de entrega.")

        original = texto.strip()
        normalizado = self._normalizar(original)

        if re.search(
            r"\b(?:[aà]|de|pela)\s+(?:manha|tarde|noite)\b|"
            r"\b(?:as\s+)?\d{1,2}\s+(?:da|de)\s+(?:manha|tarde|noite)\b|"
            r"\b(?:as\s+)?\d{1,2}(?::\d{2}|h\d{0,2})\b",
            normalizado,
        ):
            raise DateResolutionError(
                "Horarios nao fazem parte desta POC. Informe somente a data de entrega."
            )

        resolvida = self._resolver_iso(normalizado)
        if resolvida:
            return self._validar_e_montar(original, resolvida, referencia, relativa=False)

        resolvida = self._resolver_data_brasileira(normalizado, referencia)
        if resolvida:
            return self._validar_e_montar(original, resolvida, referencia, relativa=False)

        resolvida = self._resolver_data_por_extenso(normalizado, referencia)
        if resolvida:
            return self._validar_e_montar(original, resolvida, referencia, relativa=False)

        relativos = {
            "hoje": 0,
            "amanha": 1,
            "depois de amanha": 2,
        }
        relativo_encontrado = next(
            (
                nome
                for nome in ("depois de amanha", "amanha", "hoje")
                if re.search(rf"\b{nome}\b", normalizado)
            ),
            None,
        )
        if relativo_encontrado:
            resolvida = referencia + timedelta(days=relativos[relativo_encontrado])
            return self._validar_e_montar(original, resolvida, referencia, relativa=True)

        dias = re.fullmatch(
            r"(?:daqui a|em)\s+(\d+|" + "|".join(self._NUMEROS) + r")\s+dias?",
            normalizado,
        )
        if dias:
            quantidade_texto = dias.group(1)
            quantidade = (
                int(quantidade_texto)
                if quantidade_texto.isdigit()
                else self._NUMEROS[quantidade_texto]
            )
            resolvida = referencia + timedelta(days=quantidade)
            return self._validar_e_montar(original, resolvida, referencia, relativa=True)

        dia_semana = self._encontrar_dia_semana(normalizado)
        if dia_semana is not None:
            diferenca = (dia_semana - referencia.weekday()) % 7
            # Uma mencao ao dia atual significa a proxima ocorrencia. Isso evita
            # agendar silenciosamente para uma data cujo horario pode ter passado.
            if diferenca == 0:
                diferenca = 7
            resolvida = referencia + timedelta(days=diferenca)
            return self._validar_e_montar(original, resolvida, referencia, relativa=True)

        raise DateResolutionError(
            "Nao reconheci o prazo. Use, por exemplo, 'sexta', 'amanha', "
            "'25/10/2026' ou '2026-10-25'."
        )

    @staticmethod
    def normalizar_referencia(valor: date | datetime | str | None) -> date:
        if valor is None:
            return date.today()
        if isinstance(valor, datetime):
            return valor.date()
        if isinstance(valor, date):
            return valor
        if isinstance(valor, str):
            try:
                return date.fromisoformat(valor.strip())
            except ValueError as exc:
                raise DateResolutionError(
                    "A data de referencia deve estar no formato AAAA-MM-DD."
                ) from exc
        raise DateResolutionError("Data de referencia invalida.")

    def _resolver_iso(self, texto: str) -> date | None:
        correspondencia = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", texto)
        if not correspondencia:
            return None
        try:
            return date(*(int(parte) for parte in correspondencia.groups()))
        except ValueError as exc:
            raise DateResolutionError("A data informada nao existe no calendario.") from exc

    def _resolver_data_brasileira(self, texto: str, referencia: date) -> date | None:
        correspondencia = re.search(
            r"\b(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?\b", texto
        )
        if not correspondencia:
            return None
        dia, mes, ano_texto = correspondencia.groups()
        ano = referencia.year if ano_texto is None else int(ano_texto)
        if ano_texto is not None and len(ano_texto) == 2:
            ano += 2000
        try:
            resolvida = date(ano, int(mes), int(dia))
            if ano_texto is None and resolvida < referencia:
                resolvida = date(ano + 1, int(mes), int(dia))
            return resolvida
        except ValueError as exc:
            raise DateResolutionError("A data informada nao existe no calendario.") from exc

    def _resolver_data_por_extenso(self, texto: str, referencia: date) -> date | None:
        correspondencia = re.search(
            r"\b(?:dia\s+)?(\d{1,2})\s+de\s+("
            + "|".join(self._MESES)
            + r")(?:\s+de\s+(\d{4}))?\b",
            texto,
        )
        if not correspondencia:
            return None
        dia_texto, mes_texto, ano_texto = correspondencia.groups()
        ano = int(ano_texto) if ano_texto else referencia.year
        try:
            resolvida = date(ano, self._MESES[mes_texto], int(dia_texto))
            if ano_texto is None and resolvida < referencia:
                resolvida = date(ano + 1, self._MESES[mes_texto], int(dia_texto))
            return resolvida
        except ValueError as exc:
            raise DateResolutionError("A data informada nao existe no calendario.") from exc

    def _encontrar_dia_semana(self, texto: str) -> int | None:
        limpo = re.sub(r"\b(proxima|nesta|esta|que vem|feira)\b", " ", texto)
        limpo = re.sub(r"\s+", " ", limpo).strip(" -")
        for nome, indice in self._DIAS_SEMANA.items():
            if limpo == nome or re.search(rf"\b{re.escape(nome)}\b", limpo):
                return indice
        return None

    def _validar_e_montar(
        self,
        original: str,
        resolvida: date,
        referencia: date,
        *,
        relativa: bool,
    ) -> ResolucaoData:
        if resolvida < referencia:
            raise DateResolutionError("A data de entrega nao pode estar no passado.")
        return self._resultado(original, resolvida, relativa)

    def _resultado(self, original: str, resolvida: date, relativa: bool) -> ResolucaoData:
        interpretacao = self.formatar_ptbr(resolvida)
        pergunta = None
        if relativa:
            pergunta = f"Você quis dizer {interpretacao}?"
        return ResolucaoData(
            texto_original=original,
            data=resolvida,
            data_iso=resolvida.isoformat(),
            interpretacao=interpretacao,
            relativa=relativa,
            requer_confirmacao=relativa,
            pergunta_confirmacao=pergunta,
        )

    def formatar_ptbr(self, valor: date) -> str:
        dia_semana = self._NOMES_DIAS[valor.weekday()]
        return f"{dia_semana}, {valor.strftime('%d/%m/%Y')}"

    @staticmethod
    def _normalizar(texto: str) -> str:
        sem_acentos = "".join(
            caractere
            for caractere in unicodedata.normalize("NFKD", texto.lower())
            if not unicodedata.combining(caractere)
        )
        return re.sub(r"\s+", " ", sem_acentos).strip().rstrip(".?!")
