"""Interface comercial local do PedidoFlow.

Execute com ``python app.py``. A pessoa descreve a operação em linguagem
natural, revisa uma prévia legível e confirma sem preencher campos técnicos.
"""

from __future__ import annotations

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

    selecao = PROJECT_ROOT / "results" / "model-selection.json"
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

    publicado = PROJECT_ROOT / "models" / "adapter_demo"
    if publicado.exists():
        return publicado

    # Nao escolhe A/B/C pelo nome: o vencedor deve ser registrado pelas
    # metricas com training/select_best.py ou informado pela variavel de ambiente.
    return publicado


def _dump_model(modelo: Any) -> dict[str, Any]:
    if hasattr(modelo, "model_dump"):
        return modelo.model_dump(mode="json")
    return modelo.dict()


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


_CAMPOS_AMIGAVEIS = {
    "cliente": "nome do cliente",
    "itens": "produtos e quantidades",
    "endereco_entrega": "endereço de entrega",
    "prazo_texto": "data de entrega",
    "numero_pedido": "número do pedido",
    "motivo": "motivo do cancelamento",
    "novo_endereco ou novo_prazo_texto": "novo endereço ou nova data de entrega",
    "novo_endereco_ou_novo_prazo_texto": "novo endereço ou nova data de entrega",
}


def _moeda(valor: Any) -> str:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        numero = 0.0
    return f"R$ {numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _erros_amigaveis(erros: list[str]) -> list[str]:
    mensagens: list[str] = []
    for erro in erros:
        if erro.casefold().startswith("campos obrigatorios ausentes:"):
            campos_texto = erro.split(":", 1)[1].strip(" .")
            campos = [campo.strip() for campo in campos_texto.split(",")]
            nomes = [_CAMPOS_AMIGAVEIS.get(campo, campo.replace("_", " ")) for campo in campos]
            mensagens.append("Não consegui identificar: " + ", ".join(nomes) + ".")
        else:
            mensagens.append(erro)
    return mensagens


def _confirmacao_markdown(preview: Any) -> str:
    """Apresenta a prévia como uma revisão comercial, sem expor JSON."""

    if not preview.pode_executar:
        mensagens = _erros_amigaveis(preview.erros)
        itens = "\n".join(f"- {mensagem}" for mensagem in mensagens)
        instrucao = (
            "Ajuste a frase acima com essas informações e clique em "
            "**Entender solicitação** novamente."
        )
        return f"### Preciso de mais informações\n\n{itens}\n\n{instrucao}"

    argumentos = preview.argumentos
    acao = _valor_enum(preview.acao)
    partes: list[str] = []

    if acao == "criar_pedido":
        partes.append("### Confira o pedido")
        partes.append(f"**Cliente:** {argumentos.get('cliente', '—')}")
        linhas_itens = []
        for item in argumentos.get("itens", []):
            linhas_itens.append(
                f"- **{item.get('quantidade')} {item.get('unidade')}** de "
                f"{item.get('produto')}"
            )
        partes.append("**Produtos:**\n" + ("\n".join(linhas_itens) or "- —"))
        partes.append(f"**Endereço:** {argumentos.get('endereco_entrega', '—')}")
        partes.append(
            f"**Entrega:** {argumentos.get('data_entrega_formatada', '—')}"
        )
        partes.append(f"**Total estimado:** {_moeda(argumentos.get('total'))}")
    elif acao == "cancelar_pedido":
        partes.extend(
            [
                "### Confira o cancelamento",
                f"**Pedido:** #{argumentos.get('numero_pedido', '—')}",
                f"**Motivo:** {argumentos.get('motivo', '—')}",
            ]
        )
    elif acao == "alterar_entrega":
        partes.append("### Confira a alteração")
        partes.append(f"**Pedido:** #{argumentos.get('numero_pedido', '—')}")
        if argumentos.get("novo_endereco"):
            partes.append(f"**Novo endereço:** {argumentos['novo_endereco']}")
        if argumentos.get("nova_data_entrega_formatada"):
            partes.append(
                f"**Nova entrega:** {argumentos['nova_data_entrega_formatada']}"
            )
    else:
        partes.extend(["### Pedido encontrado", preview.resumo])

    if preview.pergunta_confirmacao:
        partes.append(f"> 📅 **{preview.pergunta_confirmacao}**")
    if preview.avisos:
        partes.append("> ⚠️ " + " ".join(preview.avisos))
    return "\n\n".join(partes)


def _rotulo_botao(preview: PreviewAcao) -> str:
    acao = _valor_enum(preview.acao)
    if acao == "criar_pedido":
        return "Confirmar data e criar pedido"
    if acao == "cancelar_pedido":
        return "Confirmar cancelamento"
    if acao == "alterar_entrega":
        return "Salvar alteração"
    return "Ver pedido"


def _estado_da_preview(tool_call: ToolCall, preview: PreviewAcao) -> dict[str, Any]:
    """Vincula o token à chamada e à data exata mostradas ao usuário."""

    return {
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
    titulo = "Operação concluída" if resultado.sucesso else "Operação não concluída"
    linhas = [f"### {icone} {titulo}", resultado.mensagem]
    if resultado.protocolo:
        linhas.append(f"**Protocolo:** `{resultado.protocolo}`")
    if resultado.erros:
        linhas.append("**Erros:** " + " ".join(resultado.erros))
    pedido = resultado.dados.get("pedido") if resultado.dados else None
    if isinstance(pedido, dict):
        detalhes = []
        if pedido.get("numero_pedido") is not None:
            detalhes.append(f"**Pedido:** #{pedido['numero_pedido']}")
        if pedido.get("cliente"):
            detalhes.append(f"**Cliente:** {pedido['cliente']}")
        if pedido.get("status"):
            status = str(pedido["status"]).replace("_", " ").capitalize()
            detalhes.append(f"**Status:** {status}")
        if pedido.get("data_entrega"):
            data = str(pedido["data_entrega"])
            try:
                data = datetime.fromisoformat(data).strftime("%d/%m/%Y")
            except ValueError:
                pass
            detalhes.append(f"**Entrega:** {data}")
        if pedido.get("total") is not None:
            detalhes.append(f"**Total:** {_moeda(pedido['total'])}")
        if detalhes:
            linhas.append("  \n".join(detalhes))
    return "\n\n".join(linhas)


APP_CSS = """
footer { display: none !important; }
.gradio-container { max-width: 1080px !important; margin: 0 auto !important; }
#hero {
    background: linear-gradient(135deg, #1d4ed8 0%, #0f766e 100%);
    border-radius: 18px;
    padding: 24px 28px;
    margin-bottom: 18px;
    box-shadow: 0 12px 30px rgba(15, 118, 110, 0.16);
}
#hero h1, #hero p { color: white !important; margin-bottom: 6px; }
#pedido-card, #revisao-card {
    border: 1px solid var(--border-color-primary);
    border-radius: 16px;
    padding: 18px;
    background: var(--block-background-fill);
}
#revisao-card { min-height: 170px; }
#acao-principal { min-height: 48px; font-weight: 700; }
#status-tecnico { opacity: 0.78; font-size: 0.9rem; }
"""
APP_THEME = gr.themes.Soft(
    primary_hue="blue", secondary_hue="emerald", neutral_hue="slate"
)


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
                "### Escreva a solicitação\n\nConte o que deseja fazer em uma frase.",
                gr.update(visible=False),
                {},
                "",
                interpreter.backend_status,
            )
        try:
            tool_call = interpreter.interpret(texto)
            preview = service.analisar(tool_call, data_referencia=_hoje())
            estado = _estado_da_preview(tool_call, preview)
            estado["texto_original"] = texto.strip()
            return (
                _confirmacao_markdown(preview),
                gr.update(
                    value=_rotulo_botao(preview),
                    visible=preview.pode_executar,
                ),
                estado,
                "",
                interpreter.backend_status,
            )
        except Exception as erro:  # erro de validação exibido na própria POC
            return (
                f"❌ Não foi possível entender a solicitação: {erro}",
                gr.update(visible=False),
                {},
                "",
                interpreter.backend_status,
            )

    def executar(texto: str, estado: dict[str, Any] | None):
        try:
            if not estado or not estado.get("token"):
                return (
                    "### Analise a solicitação primeiro",
                    gr.update(visible=False),
                    {},
                    "Digite a operação e clique em **Entender solicitação**.",
                    _tabela_pedidos(service),
                    _tabela_catalogo(service),
                )
            if estado.get("texto_original") != (texto or "").strip():
                return (
                    "### A solicitação foi alterada\n\nClique em **Entender solicitação** novamente para revisar os novos dados.",
                    gr.update(visible=False),
                    {},
                    "",
                    _tabela_pedidos(service),
                    _tabela_catalogo(service),
                )

            # Usa exatamente a data exibida na revisão; não recalcula expressões
            # relativas entre a análise e a confirmação.
            preview = _preview_do_estado(estado)
            if not preview.pode_executar:
                return (
                    _confirmacao_markdown(preview),
                    gr.update(visible=False),
                    estado,
                    "A operação não pode ser confirmada enquanto houver informações pendentes.",
                    _tabela_pedidos(service),
                    _tabela_catalogo(service),
                )

            resultado = service.confirmar(estado["token"])
            return (
                _confirmacao_markdown(preview),
                gr.update(visible=False),
                {},
                _resultado_markdown(resultado),
                _tabela_pedidos(service),
                _tabela_catalogo(service),
            )
        except Exception as erro:
            return (
                "### Não foi possível concluir",
                gr.update(visible=False),
                {},
                f"❌ {erro} Analise a solicitação novamente.",
                _tabela_pedidos(service),
                _tabela_catalogo(service),
            )

    def atualizar_tabelas():
        return _tabela_pedidos(service), _tabela_catalogo(service)

    def limpar():
        return (
            "",
            "### Pronto para começar\n\nDescreva um pedido, uma consulta, um cancelamento ou uma alteração.",
            gr.update(visible=False),
            {},
            "",
        )

    with gr.Blocks(title="PedidoFlow") as demo:
        estado_preview = gr.State({})
        gr.Markdown(
            "# PedidoFlow\n"
            "**Pedidos sem formulário.** Escreva como você falaria com alguém da equipe; "
            "o sistema organiza os dados e pede sua confirmação antes de salvar.",
            elem_id="hero",
        )

        with gr.Row(equal_height=False):
            with gr.Column(scale=6, elem_id="pedido-card"):
                solicitacao = gr.Textbox(
                    label="O que você precisa?",
                    placeholder=(
                        "Ex.: Crie um pedido para o Mercado Central com 2 caixas de café, "
                        "entrega na Av. Brasil, 500 até sexta"
                    ),
                    lines=4,
                    autofocus=True,
                )
                with gr.Row():
                    analisar_btn = gr.Button(
                        "Entender solicitação",
                        variant="primary",
                        elem_id="acao-principal",
                    )
                    limpar_btn = gr.Button("Limpar")
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
                    label="Exemplos rápidos",
                )

            with gr.Column(scale=5, elem_id="revisao-card"):
                confirmacao_texto = gr.Markdown(
                    "### Pronto para começar\n\n"
                    "Descreva um pedido, uma consulta, um cancelamento ou uma alteração."
                )
                executar_btn = gr.Button(
                    "Confirmar operação",
                    variant="primary",
                    visible=False,
                    elem_id="acao-principal",
                )
                resultado = gr.Markdown()

        with gr.Row():
            gr.Markdown("## Operação do comércio")
            atualizar_btn = gr.Button("Atualizar", size="sm")
        with gr.Tab("Pedidos recentes"):
            pedidos = gr.Dataframe(
                headers=["Nº", "Cliente", "Status", "Entrega", "Total"],
                value=_tabela_pedidos(service),
                interactive=False,
            )
        with gr.Tab("Estoque"):
            catalogo = gr.Dataframe(
                headers=["Produto", "Unidade", "Preço", "Estoque"],
                value=_tabela_catalogo(service),
                interactive=False,
            )
        with gr.Accordion("Informações técnicas", open=False):
            backend = gr.Markdown(interpreter.backend_status, elem_id="status-tecnico")
            gr.Markdown(
                "A IA local interpreta a frase. Datas, estoque e gravação no SQLite "
                "são validados pelo sistema antes da confirmação."
            )

        saidas_analise = [
            confirmacao_texto,
            executar_btn,
            estado_preview,
            resultado,
            backend,
        ]
        analisar_btn.click(analisar, inputs=[solicitacao], outputs=saidas_analise)
        solicitacao.submit(analisar, inputs=[solicitacao], outputs=saidas_analise)
        executar_btn.click(
            executar,
            inputs=[solicitacao, estado_preview],
            outputs=[
                confirmacao_texto,
                executar_btn,
                estado_preview,
                resultado,
                pedidos,
                catalogo,
            ],
        )
        limpar_btn.click(
            limpar,
            outputs=[
                solicitacao,
                confirmacao_texto,
                executar_btn,
                estado_preview,
                resultado,
            ],
        )
        atualizar_btn.click(atualizar_tabelas, outputs=[pedidos, catalogo])

    return demo


if __name__ == "__main__":
    create_app().launch(
        server_name="127.0.0.1",
        server_port=7860,
        inbrowser=True,
        theme=APP_THEME,
        css=APP_CSS,
        footer_links=[],
    )
