"""Interface local do PedidoFlow.

Execute com ``python app.py``. A tela usa um fluxo de duas etapas: primeiro a
solicitação é analisada e exibida como uma prévia editável; somente depois de
uma confirmação explícita a operação pode alterar o banco.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import gradio as gr


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pedidoflow import PedidoService, PreviewAcao, SQLiteRepository, ToolCall  # noqa: E402
from pedidoflow.artifacts import sha256_directory, sha256_file  # noqa: E402
from pedidoflow.generation import strict_json_loads  # noqa: E402
from pedidoflow.interpreter import OrderInterpreter  # noqa: E402


TIMEZONE = ZoneInfo("America/Sao_Paulo")


def _hoje():
    return datetime.now(TIMEZONE).date()


def _adapter_padrao() -> Path:
    configurado = os.getenv("PEDIDOFLOW_ADAPTER") or os.getenv(
        "PEDIDOFLOW_ADAPTER_PATH"
    )
    if configurado:
        return Path(configurado)

    selecao = PROJECT_ROOT / "reports" / "model-selection.json"
    if selecao.exists():
        try:
            dados = json.loads(selecao.read_text(encoding="utf-8"))
            if dados.get("status") != "final":
                raise ValueError("A selecao registrada ainda nao e final.")
            escolhido = Path(str(dados["adapter_path"]))
            if not escolhido.is_absolute():
                escolhido = PROJECT_ROOT / escolhido
            esperado = str(dados.get("adapter_sha256", ""))
            validation_file = PROJECT_ROOT / "data" / "validation.jsonl"
            validation_esperada = str(
                dados.get("validation_dataset_sha256", "")
            )
            validation_confere = (
                validation_file.exists()
                and bool(validation_esperada)
                and sha256_file(validation_file) == validation_esperada
            )
            if (
                escolhido.exists()
                and esperado
                and validation_confere
                and sha256_directory(escolhido) == esperado
            ):
                return escolhido
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            pass

    publicado = PROJECT_ROOT / "models" / "pedidoflow-qwen3-1.7b"
    if publicado.exists():
        return publicado

    # Nao escolhe A/B/C pelo nome: o vencedor deve ser registrado pelas
    # metricas com training/select_best.py ou informado pela variavel de ambiente.
    return publicado


def _dump_model(modelo: Any) -> dict[str, Any]:
    if hasattr(modelo, "model_dump"):
        return modelo.model_dump(mode="json")
    return modelo.dict()


def _tool_call_do_editor(conteudo: str) -> ToolCall:
    try:
        dados = strict_json_loads(conteudo)
    except (json.JSONDecodeError, ValueError) as erro:
        detalhe = getattr(erro, "msg", str(erro))
        raise ValueError(f"A prévia não é um JSON válido: {detalhe}.") from erro
    if hasattr(ToolCall, "model_validate"):
        return ToolCall.model_validate(dados)
    return ToolCall.parse_obj(dados)


def _json_tool_call(tool_call: ToolCall) -> str:
    return json.dumps(_dump_model(tool_call), ensure_ascii=False, indent=2)


def _fingerprint(tool_call: ToolCall) -> str:
    canonico = json.dumps(
        _dump_model(tool_call), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def _valor_enum(valor: Any) -> Any:
    return getattr(valor, "value", valor)


def _tabela_catalogo(service: PedidoService) -> list[list[Any]]:
    return [
        [
            produto.nome,
            produto.unidade,
            f"R$ {produto.preco_unitario:,.2f}".replace(",", "X")
            .replace(".", ",")
            .replace("X", "."),
            produto.estoque,
        ]
        for produto in service.listar_catalogo()
    ]


def _tabela_pedidos(service: PedidoService) -> list[list[Any]]:
    return [
        [
            pedido.numero_pedido,
            pedido.cliente,
            _valor_enum(pedido.status),
            pedido.data_entrega.strftime("%d/%m/%Y"),
            f"R$ {pedido.total:,.2f}".replace(",", "X")
            .replace(".", ",")
            .replace("X", "."),
        ]
        for pedido in service.listar_pedidos()
    ]


def _confirmacao_markdown(preview: Any) -> str:
    partes = [f"### Prévia da ação\n\n{preview.resumo}"]
    if preview.pergunta_confirmacao:
        titulo = (
            "Confirme a data"
            if "você quis dizer" in preview.pergunta_confirmacao.casefold()
            else "Confirme a operação"
        )
        partes.append(f"### {titulo}\n\n⚠️ **{preview.pergunta_confirmacao}**")
    elif preview.requer_confirmacao:
        partes.append("### Confirmação\n\nConfira os dados antes de executar a ação.")
    if preview.avisos:
        partes.append("**Avisos:** " + " ".join(preview.avisos))
    if preview.erros:
        partes.append("**Pendências:** " + " ".join(preview.erros))
    return "\n\n".join(partes)


def _estado_da_preview(tool_call: ToolCall, preview: PreviewAcao) -> dict[str, Any]:
    """Vincula o token à chamada e à data exata mostradas ao usuário."""

    return {
        "fingerprint": _fingerprint(tool_call),
        "token": preview.token,
        "requer_confirmacao": preview.requer_confirmacao,
        "preview": _dump_model(preview),
    }


def _preview_do_estado(estado: dict[str, Any]) -> PreviewAcao:
    dados = estado.get("preview")
    if not isinstance(dados, dict):
        raise ValueError("A prévia expirou na tela. Analise a solicitação novamente.")
    return PreviewAcao.model_validate(dados)


def _resultado_markdown(resultado: Any) -> str:
    icone = "✅" if resultado.sucesso else "❌"
    linhas = [f"### {icone} Resultado", resultado.mensagem]
    if resultado.protocolo:
        linhas.append(f"**Protocolo:** `{resultado.protocolo}`")
    if resultado.erros:
        linhas.append("**Erros:** " + " ".join(resultado.erros))
    if resultado.dados:
        linhas.append(
            "```json\n"
            + json.dumps(resultado.dados, ensure_ascii=False, indent=2, default=str)
            + "\n```"
        )
    return "\n\n".join(linhas)


def create_app(
    service: PedidoService | None = None,
    interpreter: OrderInterpreter | None = None,
) -> gr.Blocks:
    """Monta a interface, permitindo injetar dependências nos testes."""

    if service is None:
        caminho_banco = os.getenv(
            "PEDIDOFLOW_DB", str(PROJECT_ROOT / "data" / "pedidoflow.db")
        )
        service = PedidoService(SQLiteRepository(caminho_banco))
    if interpreter is None:
        interpreter = OrderInterpreter(adapter_path=_adapter_padrao())

    def analisar(texto: str):
        if not (texto or "").strip():
            return (
                "",
                "⚠️ Digite uma solicitação antes de analisar.",
                gr.update(value=False, visible=False),
                {},
                "",
                interpreter.backend_status,
            )
        try:
            tool_call = interpreter.interpret(texto)
            preview = service.analisar(tool_call, data_referencia=_hoje())
            estado = _estado_da_preview(tool_call, preview)
            return (
                _json_tool_call(tool_call),
                _confirmacao_markdown(preview),
                gr.update(
                    value=False,
                    visible=preview.requer_confirmacao and preview.pode_executar,
                    label=(
                        preview.pergunta_confirmacao
                        or "Revisei a prévia e confirmo esta operação"
                    ),
                ),
                estado,
                "",
                interpreter.backend_status,
            )
        except Exception as erro:  # erro de validação exibido na própria POC
            return (
                "",
                f"❌ Não foi possível preparar a ação: {erro}",
                gr.update(value=False, visible=False),
                {},
                "",
                interpreter.backend_status,
            )

    def executar(editor: str, confirmou: bool, estado: dict[str, Any] | None):
        try:
            tool_call = _tool_call_do_editor(editor)

            # Se a prévia editável mudou, um novo token é criado e a confirmação
            # anterior é descartada. Isso evita confirmar uma data e executar outra.
            if not estado or estado.get("fingerprint") != _fingerprint(tool_call):
                preview = service.analisar(tool_call, data_referencia=_hoje())
                novo_estado = _estado_da_preview(tool_call, preview)
                mensagem = (
                    "✏️ **A prévia foi alterada e validada novamente.** "
                    "Confira os dados e confirme outra vez antes de executar.\n\n"
                    + _confirmacao_markdown(preview)
                )
                return (
                    mensagem,
                    gr.update(
                        value=False,
                        visible=preview.requer_confirmacao and preview.pode_executar,
                        label=(
                            preview.pergunta_confirmacao
                            or "Revisei a prévia e confirmo esta operação"
                        ),
                    ),
                    novo_estado,
                    "",
                    _tabela_pedidos(service),
                    _tabela_catalogo(service),
                )

            # Usa exatamente a prévia exibida na análise. Não recalcula uma
            # expressão relativa na virada do dia antes de confirmar o token.
            preview = _preview_do_estado(estado)
            if not preview.pode_executar:
                return (
                    _confirmacao_markdown(preview),
                    gr.update(value=False, visible=False),
                    estado,
                    "❌ Complete ou corrija os campos indicados antes de executar.",
                    _tabela_pedidos(service),
                    _tabela_catalogo(service),
                )
            if preview.requer_confirmacao and not confirmou:
                return (
                    _confirmacao_markdown(preview),
                    gr.update(value=False, visible=True),
                    estado,
                    "⚠️ Marque a confirmação da prévia (e da data resolvida) antes de executar.",
                    _tabela_pedidos(service),
                    _tabela_catalogo(service),
                )

            resultado = service.confirmar(estado["token"])
            return (
                _confirmacao_markdown(preview),
                gr.update(value=False, visible=False),
                {},
                _resultado_markdown(resultado),
                _tabela_pedidos(service),
                _tabela_catalogo(service),
            )
        except Exception as erro:
            return (
                "❌ Revise a prévia.",
                gr.update(value=False),
                estado or {},
                f"❌ A operação não foi executada: {erro}",
                _tabela_pedidos(service),
                _tabela_catalogo(service),
            )

    def atualizar_tabelas():
        return _tabela_pedidos(service), _tabela_catalogo(service)

    with gr.Blocks(title="PedidoFlow Local") as demo:
        estado_preview = gr.State({})
        gr.Markdown(
            "# PedidoFlow Local\n"
            "Transforme uma solicitação em uma operação segura de pedidos. "
            "A LLM interpreta; regras determinísticas validam datas, estoque e execução."
        )
        backend = gr.Markdown(interpreter.backend_status)

        with gr.Row(equal_height=False):
            with gr.Column(scale=6):
                solicitacao = gr.Textbox(
                    label="Solicitação em português",
                    placeholder=(
                        "Ex.: Cadastre para o Mercado Central 2 caixas de café, "
                        "entrega na Av. Brasil, 500 até sexta."
                    ),
                    lines=5,
                )
                analisar_btn = gr.Button("Analisar solicitação", variant="primary")
                gr.Examples(
                    examples=[
                        [
                            "Cadastre para o Mercado Central duas caixas de café e "
                            "cinco pacotes de açúcar. Entregar na Av. Brasil, 500 até sexta."
                        ],
                        ["Qual é o status do pedido 1?"],
                        ["Cancele o pedido 1 porque foi cadastrado em duplicidade."],
                        [
                            "Altere o endereço do pedido 1 para Rua das Flores, 120 "
                            "e a entrega para próxima terça."
                        ],
                    ],
                    inputs=[solicitacao],
                    label="Exemplos para testar",
                )

            with gr.Column(scale=5):
                preview_json = gr.Code(
                    label="Chamada de função (prévia editável)",
                    language="json",
                    lines=15,
                    interactive=True,
                )
                confirmacao_texto = gr.Markdown("Aguardando uma solicitação.")
                confirmar = gr.Checkbox(
                    label="Revisei a prévia e confirmo esta operação",
                    value=False,
                    visible=False,
                )
                executar_btn = gr.Button("Executar operação", variant="primary")
                resultado = gr.Markdown()

        with gr.Row():
            gr.Markdown("## Estado do sistema")
            atualizar_btn = gr.Button("Atualizar tabelas", size="sm")
        with gr.Tab("Pedidos"):
            pedidos = gr.Dataframe(
                headers=["Nº", "Cliente", "Status", "Entrega", "Total"],
                value=_tabela_pedidos(service),
                interactive=False,
            )
        with gr.Tab("Catálogo e estoque"):
            catalogo = gr.Dataframe(
                headers=["Produto", "Unidade", "Preço", "Estoque"],
                value=_tabela_catalogo(service),
                interactive=False,
            )

        analisar_btn.click(
            analisar,
            inputs=[solicitacao],
            outputs=[
                preview_json,
                confirmacao_texto,
                confirmar,
                estado_preview,
                resultado,
                backend,
            ],
        )
        executar_btn.click(
            executar,
            inputs=[preview_json, confirmar, estado_preview],
            outputs=[
                confirmacao_texto,
                confirmar,
                estado_preview,
                resultado,
                pedidos,
                catalogo,
            ],
        )
        atualizar_btn.click(atualizar_tabelas, outputs=[pedidos, catalogo])

    return demo


if __name__ == "__main__":
    create_app().launch(inbrowser=True)
