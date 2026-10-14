"""Interpreta solicitações em português como chamadas de ferramenta.

O caminho principal usa o adapter QLoRA treinado pelo projeto. Quando o adapter
ainda não foi gerado (por exemplo, na primeira demonstração), um interpretador
determinístico pequeno mantém a aplicação utilizável. A interface sempre expõe
qual caminho produziu a última interpretação.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from .generation import json_stopping_criteria, strict_json_loads
from .model_loader import load_local_model
from .prompts import SYSTEM_PROMPT
from .schemas import ToolCall


ACOES = {
    "criar_pedido",
    "consultar_pedido",
    "cancelar_pedido",
    "alterar_entrega",
    "nao_suportada",
}

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
    "dezesseis": 16,
    "dezessete": 17,
    "dezoito": 18,
    "dezenove": 19,
    "vinte": 20,
}

_QTD_PATTERN = r"\d+|um|uma|dois|duas|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez|onze|doze|treze|quatorze|catorze|quinze|dezesseis|dezessete|dezoito|dezenove|vinte"
_UNIDADE_PATTERN = r"caixas?|cx|pacotes?|pct|fardos?|unidades?|un|garrafas?|sacos?|quilos?|quilo|kg|litros?|litro|l"

_UNIDADES = {
    "caixa": "caixa",
    "caixas": "caixa",
    "cx": "caixa",
    "pacote": "pacote",
    "pacotes": "pacote",
    "pct": "pacote",
    "fardo": "fardo",
    "fardos": "fardo",
    "unidade": "unidade",
    "unidades": "unidade",
    "un": "unidade",
    "garrafa": "garrafa",
    "garrafas": "garrafa",
    "saco": "saco",
    "sacos": "saco",
    "quilo": "kg",
    "quilos": "kg",
    "kg": "kg",
    "litro": "litro",
    "litros": "litro",
    "l": "litro",
}

_DIAS_PATTERN = (
    r"(?:pr[oó]xim[ao]\s+)?(?:segunda(?:-feira)?|ter[cç]a(?:-feira)?|"
    r"quarta(?:-feira)?|quinta(?:-feira)?|sexta(?:-feira)?|s[aá]bado|domingo)"
)

_HORARIO_SUFFIX = re.compile(
    r"^\s+(?:(?:[aà]s?\s+)?\d{1,2}(?::\d{2}|h\d{0,2})?"
    r"(?:\s+(?:da|de)\s+(?:manh[aã]|tarde|noite))?"
    r"|(?:[aà]|de|pela)\s+(?:manh[aã]|tarde|noite))\b",
    flags=re.IGNORECASE,
)

def _sem_acentos(texto: str) -> str:
    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFD", texto.casefold())
        if unicodedata.category(caractere) != "Mn"
    )


def _tool_call(dados: dict[str, Any]) -> ToolCall:
    """Valida a saída tanto em Pydantic 1 quanto em Pydantic 2."""

    if hasattr(ToolCall, "model_validate"):
        return ToolCall.model_validate(dados)
    return ToolCall.parse_obj(dados)


def _reconcile_missing_fields(call: ToolCall) -> ToolCall:
    """Calcula ausencias pelo payload; nao confia nessa lista gerada pela LLM."""

    action = getattr(call.acao, "value", call.acao)
    arguments = call.argumentos
    missing: list[str] = []
    if action == "criar_pedido":
        for field in ("cliente", "itens", "endereco_entrega", "prazo_texto"):
            if not arguments.get(field):
                missing.append(field)
    elif action == "consultar_pedido":
        if not arguments.get("numero_pedido"):
            missing.append("numero_pedido")
    elif action == "cancelar_pedido":
        if not arguments.get("numero_pedido"):
            missing.append("numero_pedido")
        if not arguments.get("motivo"):
            missing.append("motivo")
    elif action == "alterar_entrega":
        if not arguments.get("numero_pedido"):
            missing.append("numero_pedido")
        if not arguments.get("novo_endereco") and not arguments.get(
            "novo_prazo_texto"
        ):
            missing.append("novo_endereco_ou_novo_prazo_texto")
    return call.model_copy(update={"campos_faltantes": missing})


def _json_da_resposta(texto: str) -> dict[str, Any]:
    texto = texto.strip()
    texto = re.sub(r"^```(?:json)?\s*", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\s*```$", "", texto)
    inicio = texto.find("{")
    fim = texto.rfind("}")
    if inicio < 0 or fim <= inicio:
        raise ValueError("A saída do modelo não contém um objeto JSON.")
    dados = strict_json_loads(texto[inicio : fim + 1])
    if not isinstance(dados, dict):
        raise ValueError("A saída do modelo não é um objeto JSON.")
    return dados


def _preservar_sufixo_horario(
    texto: str, correspondencia: re.Match[str], grupo: str | int = 0
) -> str:
    inicio, fim = correspondencia.span(grupo)
    sufixo = _HORARIO_SUFFIX.match(texto[fim:])
    if sufixo:
        fim += sufixo.end()
    return texto[inicio:fim].strip()


class OrderInterpreter:
    """Seleciona uma ferramenta e extrai seus argumentos.

    O modelo é carregado de forma preguiçosa somente se existir um diretório de
    adapter. Assim, importar a aplicação ou rodar os testes não baixa pesos.
    """

    def __init__(
        self,
        adapter_path: str | Path = "models/adapter_demo",
        base_model: str = "Qwen/Qwen3-1.7B",
        force_fallback: bool | None = None,
    ) -> None:
        self.adapter_path = Path(adapter_path)
        self.base_model = base_model
        self.force_fallback = (
            os.getenv("PEDIDOFLOW_FORCE_FALLBACK", "0") == "1"
            if force_fallback is None
            else force_fallback
        )
        self._model: Any | None = None
        self._tokenizer: Any | None = None
        self._load_attempted = False
        self._load_error: str | None = None
        self.last_backend = "fallback_deterministico"

    @property
    def backend_status(self) -> str:
        if self.last_backend == "adapter_qwen":
            return "LLM local: adapter Qwen treinado (GPU)"
        if self._load_error:
            return f"Fallback determinístico local (adapter indisponível: {self._load_error})"
        if self.force_fallback:
            return "Fallback determinístico local (forçado por configuração)"
        if not self.adapter_path.exists():
            return "Fallback determinístico local (treine o adapter para ativar a LLM)"
        return "Fallback determinístico local"

    def interpret(self, texto: str) -> ToolCall:
        texto = (texto or "").strip()
        if not texto:
            self.last_backend = "fallback_deterministico"
            return _tool_call(
                {
                    "acao": "nao_suportada",
                    "argumentos": {},
                    "campos_faltantes": ["solicitacao"],
                }
            )

        if self._ensure_model():
            try:
                resultado = self._interpret_with_model(texto)
                self.last_backend = "adapter_qwen"
                return _reconcile_missing_fields(resultado)
            except (
                ValueError,
                TypeError,
                KeyError,
                RuntimeError,
                json.JSONDecodeError,
            ):
                # Uma saída fora do contrato nunca segue para a camada de negócio.
                self.last_backend = "fallback_deterministico"

        self.last_backend = "fallback_deterministico"
        return _reconcile_missing_fields(self._interpret_deterministic(texto))

    def _ensure_model(self) -> bool:
        if self.force_fallback or not self.adapter_path.exists():
            return False
        if self._model is not None and self._tokenizer is not None:
            return True
        if self._load_attempted:
            return False

        self._load_attempted = True
        try:
            self._tokenizer, self._model, _ = load_local_model(
                self.base_model, self.adapter_path
            )
            return True
        except (ImportError, OSError, RuntimeError, ValueError) as erro:
            self._model = None
            self._tokenizer = None
            self._load_error = str(erro).splitlines()[0][:120]
            return False

    def _interpret_with_model(self, texto: str) -> ToolCall:
        import torch

        mensagens = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": texto},
        ]
        try:
            prompt = self._tokenizer.apply_chat_template(
                mensagens,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            prompt = self._tokenizer.apply_chat_template(
                mensagens, tokenize=False, add_generation_prompt=True
            )

        entradas = self._tokenizer(prompt, return_tensors="pt")
        dispositivo = next(self._model.parameters()).device
        entradas = {nome: valor.to(dispositivo) for nome, valor in entradas.items()}
        with torch.inference_mode():
            tokens = self._model.generate(
                **entradas,
                max_new_tokens=320,
                do_sample=False,
                stopping_criteria=json_stopping_criteria(
                    self._tokenizer, entradas["input_ids"].shape[1]
                ),
                pad_token_id=self._tokenizer.eos_token_id,
            )
        novos_tokens = tokens[0, entradas["input_ids"].shape[1] :]
        dados = _json_da_resposta(
            self._tokenizer.decode(novos_tokens, skip_special_tokens=True)
        )
        if dados.get("acao") not in ACOES:
            raise ValueError("Ação fora da lista permitida.")
        dados.setdefault("argumentos", {})
        dados.setdefault("campos_faltantes", [])
        return _tool_call(dados)

    def _interpret_deterministic(self, texto: str) -> ToolCall:
        normalizado = _sem_acentos(texto)
        if re.search(r"\b(cancel|cancele|cancelar|cancela)\w*\b", normalizado):
            return self._cancelar(texto)
        if re.search(r"\b(alter|mud|troc|atualiz)\w*\b", normalizado) and re.search(
            r"\b(entrega|endereco|prazo|data)\b", normalizado
        ):
            return self._alterar(texto)
        if re.search(
            r"\b(consult|status|situacao|rastre|acompanhar)\w*\b|\bonde\s+(?:esta|ta)\b",
            normalizado,
        ):
            return self._consultar(texto)
        if re.search(
            r"\b(cadastr|cri|registr|quero|preciso|mand|envi|pedido)\w*\b",
            normalizado,
        ) and self._extrair_itens(texto):
            return self._criar(texto)
        return _tool_call(
            {"acao": "nao_suportada", "argumentos": {}, "campos_faltantes": []}
        )

    @staticmethod
    def _numero_pedido(texto: str) -> int | None:
        correspondencia = re.search(
            r"\bpedido\s*(?:n(?:[.º°o]|[uú]mero)?\s*)?[#:]?\s*(\d+)\b",
            texto,
            flags=re.IGNORECASE,
        )
        if not correspondencia:
            correspondencia = re.search(r"#(\d+)\b", texto)
        return int(correspondencia.group(1)) if correspondencia else None

    def _consultar(self, texto: str) -> ToolCall:
        numero = self._numero_pedido(texto)
        argumentos = {"numero_pedido": numero} if numero is not None else {}
        faltantes = [] if numero is not None else ["numero_pedido"]
        return _tool_call(
            {
                "acao": "consultar_pedido",
                "argumentos": argumentos,
                "campos_faltantes": faltantes,
            }
        )

    def _cancelar(self, texto: str) -> ToolCall:
        numero = self._numero_pedido(texto)
        motivo_match = re.search(
            r"\b(?:porque|pois|motivo\s*:|por\s+motivo\s+de)\s+(.+)$",
            texto,
            flags=re.IGNORECASE,
        )
        motivo = motivo_match.group(1).strip(" .") if motivo_match else None
        argumentos: dict[str, Any] = {}
        faltantes: list[str] = []
        if numero is None:
            faltantes.append("numero_pedido")
        else:
            argumentos["numero_pedido"] = numero
        if not motivo:
            faltantes.append("motivo")
        else:
            argumentos["motivo"] = motivo
        return _tool_call(
            {
                "acao": "cancelar_pedido",
                "argumentos": argumentos,
                "campos_faltantes": faltantes,
            }
        )

    def _alterar(self, texto: str) -> ToolCall:
        numero = self._numero_pedido(texto)
        prazo = self._extrair_prazo(texto)
        endereco_match = re.search(
            r"\bendere[cç]o(?:\s+de\s+entrega)?"
            r"(?:\s+do\s+pedido\s+(?:n(?:[.º°o]|[uú]mero)?\s*)?[#:]?\s*\d+)?"
            r"\s+(?:para|pra|:)\s+(.+?)"
            rf"(?=\s+(?:(?:at[eé]|para)\s+(?:{_DIAS_PATTERN}|hoje|amanh[aã]|\d{{1,2}}[/.-]\d{{1,2}})|e\s+a\s+entrega\s+para)|;|$)",
            texto,
            flags=re.IGNORECASE,
        )
        endereco = endereco_match.group(1).strip(" ,.") if endereco_match else None

        argumentos: dict[str, Any] = {}
        if numero is not None:
            argumentos["numero_pedido"] = numero
        if endereco:
            argumentos["novo_endereco"] = endereco
        if prazo:
            argumentos["novo_prazo_texto"] = prazo

        faltantes = [] if numero is not None else ["numero_pedido"]
        if not endereco and not prazo:
            faltantes.append("novo_endereco_ou_novo_prazo_texto")
        return _tool_call(
            {
                "acao": "alterar_entrega",
                "argumentos": argumentos,
                "campos_faltantes": faltantes,
            }
        )

    def _criar(self, texto: str) -> ToolCall:
        itens = self._extrair_itens(texto)
        cliente = self._extrair_cliente(texto)
        endereco = self._extrair_endereco(texto)
        prazo = self._extrair_prazo(texto)

        argumentos: dict[str, Any] = {}
        faltantes: list[str] = []
        for nome, valor in (
            ("cliente", cliente),
            ("itens", itens),
            ("endereco_entrega", endereco),
            ("prazo_texto", prazo),
        ):
            if valor:
                argumentos[nome] = valor
            else:
                faltantes.append(nome)
        return _tool_call(
            {
                "acao": "criar_pedido",
                "argumentos": argumentos,
                "campos_faltantes": faltantes,
            }
        )

    @staticmethod
    def _extrair_itens(texto: str) -> list[dict[str, Any]]:
        padrao = re.compile(
            rf"\b(?P<qtd>{_QTD_PATTERN})\s+"
            rf"(?P<unidade>{_UNIDADE_PATTERN})\s+(?:de\s+)?"
            rf"(?P<produto>.+?)"
            rf"(?=(?:\s+e\s+|\s*,\s*)(?=(?:{_QTD_PATTERN})\s+(?:{_UNIDADE_PATTERN})\b)"
            rf"|\s*(?:,|;)?\s+(?:entregar|entrega|com\s+entrega|at[eé]|endere[cç]o)\b"
            rf"|[.;]|$)",
            flags=re.IGNORECASE,
        )
        itens: list[dict[str, Any]] = []
        for correspondencia in padrao.finditer(texto):
            qtd_texto = _sem_acentos(correspondencia.group("qtd"))
            quantidade = int(qtd_texto) if qtd_texto.isdigit() else _NUMEROS[qtd_texto]
            unidade_original = _sem_acentos(correspondencia.group("unidade"))
            produto = correspondencia.group("produto").strip(" ,.-")
            if produto:
                itens.append(
                    {
                        "produto": produto.casefold(),
                        "quantidade": quantidade,
                        "unidade": _UNIDADES[unidade_original],
                    }
                )
        return itens

    @staticmethod
    def _extrair_cliente(texto: str) -> str | None:
        explicito = re.search(
            rf"\bcliente\s*(?:é|:)?\s*(.+?)(?=\s+(?:{_QTD_PATTERN})\s+(?:{_UNIDADE_PATTERN})\b|[,;.]|$)",
            texto,
            flags=re.IGNORECASE,
        )
        if explicito:
            return explicito.group(1).strip(" ,.")

        depois_da_acao = re.search(
            rf"\b(?:cadastre|crie|registre)(?:\s+um\s+pedido)?\s+(?:para|pro|pra)\s+"
            rf"(?:o|a)?\s*(.+?)(?=\s+(?:com\s+)?(?:{_QTD_PATTERN})\s+"
            rf"(?:{_UNIDADE_PATTERN})\b)",
            texto,
            flags=re.IGNORECASE,
        )
        return depois_da_acao.group(1).strip(" ,.") if depois_da_acao else None

    @staticmethod
    def _extrair_endereco(texto: str) -> str | None:
        correspondencia = re.search(
            r"\b(?:entregar|entrega|endere[cç]o(?:\s+de\s+entrega)?)"
            r"\s*(?:é|:)?\s*(?:em|na|no|para|pra)?\s*"
            rf"(.+?)(?=\s+(?:at[eé]\s+)?(?:{_DIAS_PATTERN}|hoje|amanh[aã]|depois\s+de\s+amanh[aã])\b|;|$)",
            texto,
            flags=re.IGNORECASE,
        )
        if not correspondencia:
            return None
        endereco = correspondencia.group(1).strip(" ,.")
        return endereco or None

    @staticmethod
    def _extrair_prazo(texto: str) -> str | None:
        padroes_diretos = (
            rf"\b{_DIAS_PATTERN}\b",
            r"\b(?:depois\s+de\s+amanh[aã]|amanh[aã]|hoje)\b",
        )
        for padrao in padroes_diretos:
            correspondencia = re.search(padrao, texto, flags=re.IGNORECASE)
            if correspondencia:
                return _preservar_sufixo_horario(texto, correspondencia)
        data_com_contexto = re.search(
            r"\b(?:at[eé]|para|pra|em|prazo(?:\s+para)?|data(?:\s+para)?)\s+"
            r"(?P<prazo>\d{4}-\d{2}-\d{2}|(?:dia\s+)?\d{1,2}[/.-]\d{1,2}"
            r"(?:[/.-]\d{2,4})?)\b",
            texto,
            flags=re.IGNORECASE,
        )
        if data_com_contexto:
            return _preservar_sufixo_horario(texto, data_com_contexto, "prazo")
        return None


__all__ = ["OrderInterpreter"]
