"""Orquestracao das chamadas de ferramenta e confirmacao das acoes."""

from __future__ import annotations

import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from pydantic import ValidationError

from .database import RepositoryError, SQLiteRepository
from .date_resolver import DateResolutionError, DateResolver
from .schemas import (
    Acao,
    PreviewAcao,
    ProdutoEstoque,
    ResultadoExecucao,
    ToolCall,
)


class PedidoService:
    """Fronteira segura entre a interpretacao da LLM e o banco de dados.

    ``analisar`` nunca altera dados. A previa gerada e guardada internamente e
    somente o token correspondente pode ser confirmado. Assim, alteracoes no
    JSON exibido pelo navegador nao mudam a operacao validada no servidor.
    """

    def __init__(
        self,
        repository: SQLiteRepository | str | Path | None = None,
        *,
        database_path: str | Path = "data/pedidoflow.db",
        preview_ttl_minutos: int = 10,
        date_resolver: DateResolver | None = None,
    ) -> None:
        if isinstance(repository, (str, Path)):
            self.repository = SQLiteRepository(repository)
        else:
            self.repository = repository or SQLiteRepository(database_path)
        self.date_resolver = date_resolver or DateResolver()
        self.preview_ttl = timedelta(minutes=max(1, preview_ttl_minutos))
        self._pendentes: dict[str, PreviewAcao] = {}
        self._lock = threading.RLock()

    def analisar(
        self,
        tool_call: ToolCall | Mapping[str, Any],
        data_referencia: date | datetime | str | None = None,
    ) -> PreviewAcao:
        """Valida uma chamada e retorna uma previa sem efeitos colaterais."""

        try:
            referencia = self.date_resolver.normalizar_referencia(data_referencia)
        except DateResolutionError:
            referencia = date.today()
            return self._nova_preview(
                acao=Acao.NAO_SUPORTADA,
                argumentos={},
                resumo="Nao foi possivel validar a data de referencia.",
                requer_confirmacao=False,
                pode_executar=False,
                erros=["A data de referencia deve estar no formato AAAA-MM-DD."],
                data_referencia=referencia,
            )

        try:
            chamada = (
                tool_call
                if isinstance(tool_call, ToolCall)
                else ToolCall.model_validate(dict(tool_call))
            )
        except (ValidationError, TypeError, ValueError) as exc:
            return self._nova_preview(
                acao=Acao.NAO_SUPORTADA,
                argumentos={},
                resumo="A interpretacao nao gerou uma chamada valida.",
                requer_confirmacao=False,
                pode_executar=False,
                erros=[f"Chamada de ferramenta invalida: {self._resumir_erro(exc)}"],
                data_referencia=referencia,
            )

        if chamada.acao == Acao.CRIAR_PEDIDO:
            return self._analisar_criacao(chamada, referencia)
        if chamada.acao == Acao.CONSULTAR_PEDIDO:
            return self._analisar_consulta(chamada, referencia)
        if chamada.acao == Acao.CANCELAR_PEDIDO:
            return self._analisar_cancelamento(chamada, referencia)
        if chamada.acao == Acao.ALTERAR_ENTREGA:
            return self._analisar_alteracao(chamada, referencia)
        return self._nova_preview(
            acao=Acao.NAO_SUPORTADA,
            argumentos={},
            resumo="A solicitacao esta fora das operacoes suportadas pelo PedidoFlow.",
            requer_confirmacao=False,
            pode_executar=False,
            erros=["Solicitacao nao suportada."],
            data_referencia=referencia,
        )

    def confirmar(
        self, preview_ou_token: PreviewAcao | Mapping[str, Any] | str
    ) -> ResultadoExecucao:
        """Executa uma previa uma unica vez, desde que ainda esteja valida."""

        token = self._extrair_token(preview_ou_token)
        if not token:
            return self._falha(
                Acao.NAO_SUPORTADA,
                "Nao foi possivel confirmar a operacao.",
                "Token de confirmacao ausente.",
            )
        with self._lock:
            preview = self._pendentes.pop(token, None)
        if preview is None:
            return self._falha(
                Acao.NAO_SUPORTADA,
                "A previa nao existe ou ja foi utilizada.",
                "Analise novamente a solicitacao antes de confirmar.",
            )
        if datetime.now(timezone.utc) > preview.expira_em:
            return self._falha(
                preview.acao,
                "A previa expirou.",
                "Analise novamente a solicitacao para atualizar os dados.",
            )
        if not preview.pode_executar:
            return self._falha(
                preview.acao,
                "A operacao possui erros e nao pode ser executada.",
                *preview.erros,
            )

        try:
            if preview.acao == Acao.CRIAR_PEDIDO:
                return self._executar_criacao(preview)
            if preview.acao == Acao.CONSULTAR_PEDIDO:
                return self._executar_consulta(preview)
            if preview.acao == Acao.CANCELAR_PEDIDO:
                return self._executar_cancelamento(preview)
            if preview.acao == Acao.ALTERAR_ENTREGA:
                return self._executar_alteracao(preview)
        except RepositoryError as exc:
            return self._falha(
                preview.acao,
                "A operacao nao foi concluida.",
                str(exc),
            )
        return self._falha(
            preview.acao,
            "A operacao nao e executavel.",
            "Acao nao suportada.",
        )

    def executar(
        self, preview_ou_token: PreviewAcao | Mapping[str, Any] | str
    ) -> ResultadoExecucao:
        """Alias explicito para integracoes que usam o termo executar."""

        return self.confirmar(preview_ou_token)

    def listar_catalogo(self) -> list[ProdutoEstoque]:
        return self.repository.listar_produtos()

    def listar_estoque(self) -> list[ProdutoEstoque]:
        return self.listar_catalogo()

    def listar_pedidos(self, limite: int = 100):
        return self.repository.listar_pedidos(limite)

    def _analisar_criacao(self, chamada: ToolCall, referencia: date) -> PreviewAcao:
        argumentos = chamada.argumentos
        cliente = self._texto(argumentos.get("cliente"))
        endereco = self._texto(
            argumentos.get("endereco_entrega", argumentos.get("endereco"))
        )
        prazo = argumentos.get(
            "prazo_texto", argumentos.get("prazo", argumentos.get("data_entrega"))
        )
        itens = argumentos.get("itens")
        faltantes: set[str] = set()
        if not cliente:
            faltantes.add("cliente")
        if not isinstance(itens, list) or not itens:
            faltantes.add("itens")
        if not endereco:
            faltantes.add("endereco_entrega")
        if prazo in (None, ""):
            faltantes.add("prazo_texto")
        if faltantes:
            return self._preview_com_faltantes(Acao.CRIAR_PEDIDO, faltantes, referencia)

        try:
            resolucao = self.date_resolver.resolve(prazo, referencia)
            orcamento = self.repository.orcar_itens(itens)
        except (DateResolutionError, RepositoryError) as exc:
            return self._preview_com_erro(Acao.CRIAR_PEDIDO, str(exc), referencia)

        itens_normalizados = [
            {
                "produto": item["produto"],
                "quantidade": item["quantidade"],
                "unidade": item["unidade"],
            }
            for item in orcamento["itens"]
        ]
        normalizados = {
            "cliente": cliente,
            "itens": itens_normalizados,
            "endereco_entrega": endereco,
            "prazo_texto": str(prazo),
            "data_entrega": resolucao.data_iso,
            "data_entrega_formatada": resolucao.interpretacao,
            "total": orcamento["total"],
        }
        pergunta = (
            f"{resolucao.pergunta_confirmacao} Confirma a criacao do pedido?"
            if resolucao.requer_confirmacao
            else f"Confirma a criacao do pedido para {resolucao.interpretacao}?"
        )
        return self._nova_preview(
            acao=Acao.CRIAR_PEDIDO,
            argumentos=normalizados,
            resumo=(
                f"Criar pedido para {cliente}, com {len(itens_normalizados)} produto(s), "
                f"total de {self._moeda(orcamento['total'])}, entrega em "
                f"{resolucao.interpretacao}."
            ),
            requer_confirmacao=True,
            pergunta_confirmacao=pergunta,
            pode_executar=True,
            data_referencia=referencia,
        )

    def _analisar_consulta(self, chamada: ToolCall, referencia: date) -> PreviewAcao:
        numero = self._numero_pedido(chamada.argumentos.get("numero_pedido"))
        faltantes: set[str] = set()
        if numero is None:
            faltantes.add("numero_pedido")
        if faltantes:
            return self._preview_com_faltantes(Acao.CONSULTAR_PEDIDO, faltantes, referencia)
        try:
            pedido = self.repository.consultar_pedido(numero)
        except RepositoryError as exc:
            return self._preview_com_erro(Acao.CONSULTAR_PEDIDO, str(exc), referencia)
        return self._nova_preview(
            acao=Acao.CONSULTAR_PEDIDO,
            argumentos={"numero_pedido": numero},
            resumo=f"Consultar o pedido {numero} de {pedido.cliente}.",
            requer_confirmacao=False,
            pode_executar=True,
            data_referencia=referencia,
        )

    def _analisar_cancelamento(self, chamada: ToolCall, referencia: date) -> PreviewAcao:
        numero = self._numero_pedido(chamada.argumentos.get("numero_pedido"))
        motivo = self._texto(chamada.argumentos.get("motivo"))
        faltantes: set[str] = set()
        if numero is None:
            faltantes.add("numero_pedido")
        if not motivo:
            faltantes.add("motivo")
        if faltantes:
            return self._preview_com_faltantes(Acao.CANCELAR_PEDIDO, faltantes, referencia)
        try:
            pedido = self.repository.consultar_pedido(numero)
            if pedido.status.value == "cancelado":
                return self._preview_com_erro(
                    Acao.CANCELAR_PEDIDO,
                    f"O pedido {numero} ja esta cancelado.",
                    referencia,
                )
        except RepositoryError as exc:
            return self._preview_com_erro(Acao.CANCELAR_PEDIDO, str(exc), referencia)
        return self._nova_preview(
            acao=Acao.CANCELAR_PEDIDO,
            argumentos={"numero_pedido": numero, "motivo": motivo},
            resumo=f"Cancelar o pedido {numero}. Motivo: {motivo}.",
            requer_confirmacao=True,
            pergunta_confirmacao=f"Confirma o cancelamento do pedido {numero}?",
            pode_executar=True,
            avisos=["O estoque dos itens sera devolvido ao catalogo."],
            data_referencia=referencia,
        )

    def _analisar_alteracao(self, chamada: ToolCall, referencia: date) -> PreviewAcao:
        argumentos = chamada.argumentos
        numero = self._numero_pedido(argumentos.get("numero_pedido"))
        endereco = self._texto(
            argumentos.get("novo_endereco", argumentos.get("endereco_entrega"))
        )
        prazo = argumentos.get(
            "novo_prazo_texto",
            argumentos.get(
                "novo_prazo",
                argumentos.get(
                    "nova_data_entrega",
                    argumentos.get("prazo_texto", argumentos.get("prazo")),
                ),
            ),
        )
        faltantes: set[str] = set()
        if numero is None:
            faltantes.add("numero_pedido")
        if not endereco and prazo in (None, ""):
            faltantes.add("novo_endereco ou novo_prazo_texto")
        if faltantes:
            return self._preview_com_faltantes(Acao.ALTERAR_ENTREGA, faltantes, referencia)
        try:
            pedido = self.repository.consultar_pedido(numero)
            if pedido.status.value != "criado":
                return self._preview_com_erro(
                    Acao.ALTERAR_ENTREGA,
                    f"O pedido {numero} nao pode mais ser alterado.",
                    referencia,
                )
            resolucao = self.date_resolver.resolve(prazo, referencia) if prazo else None
        except (DateResolutionError, RepositoryError) as exc:
            return self._preview_com_erro(Acao.ALTERAR_ENTREGA, str(exc), referencia)

        normalizados: dict[str, Any] = {"numero_pedido": numero}
        mudancas: list[str] = []
        if endereco:
            normalizados["novo_endereco"] = endereco
            mudancas.append(f"endereco para {endereco}")
        if resolucao:
            normalizados.update(
                {
                    "novo_prazo_texto": str(prazo),
                    "nova_data_entrega": resolucao.data_iso,
                    "nova_data_entrega_formatada": resolucao.interpretacao,
                }
            )
            mudancas.append(f"entrega para {resolucao.interpretacao}")
        pergunta = f"Confirma a alteracao do pedido {numero}?"
        if resolucao and resolucao.requer_confirmacao:
            pergunta = f"{resolucao.pergunta_confirmacao} {pergunta}"
        return self._nova_preview(
            acao=Acao.ALTERAR_ENTREGA,
            argumentos=normalizados,
            resumo=f"Alterar pedido {numero}: {'; '.join(mudancas)}.",
            requer_confirmacao=True,
            pergunta_confirmacao=pergunta,
            pode_executar=True,
            data_referencia=referencia,
        )

    def _executar_criacao(self, preview: PreviewAcao) -> ResultadoExecucao:
        args = preview.argumentos
        pedido = self.repository.criar_pedido(
            cliente=args["cliente"],
            itens=args["itens"],
            endereco_entrega=args["endereco_entrega"],
            data_entrega=args["data_entrega"],
        )
        protocolo = self._protocolo("PED", pedido.numero_pedido)
        return ResultadoExecucao(
            sucesso=True,
            acao=preview.acao,
            mensagem=(
                f"Pedido {pedido.numero_pedido} criado com sucesso. "
                f"Total: {self._moeda(pedido.total)}."
            ),
            protocolo=protocolo,
            dados={"pedido": pedido.model_dump(mode="json")},
        )

    def _executar_consulta(self, preview: PreviewAcao) -> ResultadoExecucao:
        pedido = self.repository.consultar_pedido(preview.argumentos["numero_pedido"])
        return ResultadoExecucao(
            sucesso=True,
            acao=preview.acao,
            mensagem=f"Pedido {pedido.numero_pedido} localizado.",
            dados={"pedido": pedido.model_dump(mode="json")},
        )

    def _executar_cancelamento(self, preview: PreviewAcao) -> ResultadoExecucao:
        args = preview.argumentos
        pedido = self.repository.cancelar_pedido(args["numero_pedido"], args["motivo"])
        return ResultadoExecucao(
            sucesso=True,
            acao=preview.acao,
            mensagem=f"Pedido {pedido.numero_pedido} cancelado com sucesso.",
            protocolo=self._protocolo("CAN", pedido.numero_pedido),
            dados={"pedido": pedido.model_dump(mode="json")},
        )

    def _executar_alteracao(self, preview: PreviewAcao) -> ResultadoExecucao:
        args = preview.argumentos
        pedido = self.repository.alterar_entrega(
            args["numero_pedido"],
            novo_endereco=args.get("novo_endereco"),
            nova_data_entrega=args.get("nova_data_entrega"),
        )
        return ResultadoExecucao(
            sucesso=True,
            acao=preview.acao,
            mensagem=f"Entrega do pedido {pedido.numero_pedido} alterada com sucesso.",
            protocolo=self._protocolo("ALT", pedido.numero_pedido),
            dados={"pedido": pedido.model_dump(mode="json")},
        )

    def _nova_preview(
        self,
        *,
        acao: Acao,
        argumentos: dict[str, Any],
        resumo: str,
        requer_confirmacao: bool,
        pode_executar: bool,
        data_referencia: date,
        pergunta_confirmacao: str | None = None,
        erros: list[str] | None = None,
        avisos: list[str] | None = None,
    ) -> PreviewAcao:
        agora = datetime.now(timezone.utc)
        preview = PreviewAcao(
            token=uuid.uuid4().hex,
            acao=acao,
            argumentos=argumentos,
            resumo=resumo,
            requer_confirmacao=requer_confirmacao,
            pergunta_confirmacao=pergunta_confirmacao,
            pode_executar=pode_executar,
            erros=erros or [],
            avisos=avisos or [],
            data_referencia=data_referencia,
            criado_em=agora,
            expira_em=agora + self.preview_ttl,
        )
        if pode_executar:
            with self._lock:
                self._limpar_expirados(agora)
                self._pendentes[preview.token] = preview.model_copy(deep=True)
        return preview

    def _preview_com_faltantes(
        self, acao: Acao, faltantes: set[str], referencia: date
    ) -> PreviewAcao:
        campos = sorted(faltantes)
        return self._nova_preview(
            acao=acao,
            argumentos={},
            resumo="Faltam dados para preparar a operacao.",
            requer_confirmacao=False,
            pode_executar=False,
            erros=[f"Campos obrigatorios ausentes: {', '.join(campos)}."],
            data_referencia=referencia,
        )

    def _preview_com_erro(self, acao: Acao, erro: str, referencia: date) -> PreviewAcao:
        return self._nova_preview(
            acao=acao,
            argumentos={},
            resumo="Nao foi possivel preparar a operacao.",
            requer_confirmacao=False,
            pode_executar=False,
            erros=[erro],
            data_referencia=referencia,
        )

    @staticmethod
    def _texto(valor: Any) -> str | None:
        if not isinstance(valor, str):
            return None
        limpo = valor.strip()
        return limpo or None

    @staticmethod
    def _numero_pedido(valor: Any) -> int | None:
        if isinstance(valor, bool):
            return None
        if isinstance(valor, int):
            return valor if valor > 0 else None
        if isinstance(valor, str):
            limpo = valor.strip()
            if not limpo.isdigit():
                return None
            numero = int(limpo)
            return numero if numero > 0 else None
        # Nao converte floats: 1.9 nunca pode virar silenciosamente o pedido 1.
        return None

    @staticmethod
    def _extrair_token(valor: PreviewAcao | Mapping[str, Any] | str) -> str | None:
        if isinstance(valor, PreviewAcao):
            return valor.token
        if isinstance(valor, str):
            return valor.strip() or None
        if isinstance(valor, Mapping):
            token = valor.get("token")
            return str(token).strip() if token else None
        return None

    def _limpar_expirados(self, agora: datetime) -> None:
        expirados = [
            token for token, preview in self._pendentes.items() if agora > preview.expira_em
        ]
        for token in expirados:
            self._pendentes.pop(token, None)

    @staticmethod
    def _falha(acao: Acao, mensagem: str, *erros: str) -> ResultadoExecucao:
        return ResultadoExecucao(
            sucesso=False,
            acao=acao,
            mensagem=mensagem,
            erros=[erro for erro in erros if erro],
        )

    @staticmethod
    def _protocolo(prefixo: str, numero_pedido: int) -> str:
        return f"{prefixo}-{date.today().year}-{numero_pedido:06d}"

    @staticmethod
    def _moeda(valor: float) -> str:
        formatado = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {formatado}"

    @staticmethod
    def _resumir_erro(erro: Exception) -> str:
        texto = str(erro).replace("\n", " ")
        return " ".join(texto.split())[:300]
