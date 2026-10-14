"""Contratos de entrada e saida do nucleo do PedidoFlow."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Acao(str, Enum):
    """Acoes que o modelo local pode selecionar."""

    CRIAR_PEDIDO = "criar_pedido"
    CONSULTAR_PEDIDO = "consultar_pedido"
    CANCELAR_PEDIDO = "cancelar_pedido"
    ALTERAR_ENTREGA = "alterar_entrega"
    NAO_SUPORTADA = "nao_suportada"


class PedidoStatus(str, Enum):
    CRIADO = "criado"
    CANCELADO = "cancelado"


class SchemaBase(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
        use_enum_values=False,
        validate_assignment=True,
    )


class ItemSolicitado(SchemaBase):
    produto: str = Field(min_length=1)
    quantidade: int = Field(gt=0)
    unidade: str | None = None


class ToolCall(SchemaBase):
    """Saida estruturada esperada do interpretador/LLM."""

    acao: Acao
    argumentos: dict[str, Any] = Field(default_factory=dict)
    campos_faltantes: list[str] = Field(default_factory=list)

    @field_validator("campos_faltantes")
    @classmethod
    def remover_campos_repetidos(cls, campos: list[str]) -> list[str]:
        return list(dict.fromkeys(campo.strip() for campo in campos if campo.strip()))


class ResolucaoData(SchemaBase):
    """Resultado auditavel da conversao de uma data em linguagem natural."""

    texto_original: str
    data: date
    data_iso: str
    interpretacao: str
    relativa: bool
    requer_confirmacao: bool
    pergunta_confirmacao: str | None = None

    @property
    def resolved_date(self) -> date:
        """Alias em ingles para facilitar integracoes externas."""

        return self.data


class ProdutoEstoque(SchemaBase):
    id: int
    nome: str
    unidade: str
    preco_unitario: float = Field(ge=0)
    estoque: int = Field(ge=0)


class PedidoItem(SchemaBase):
    produto_id: int
    produto: str
    quantidade: int = Field(gt=0)
    unidade: str
    preco_unitario: float = Field(ge=0)
    subtotal: float = Field(ge=0)


class Pedido(SchemaBase):
    numero_pedido: int
    cliente: str
    itens: list[PedidoItem]
    endereco_entrega: str
    data_entrega: date
    status: PedidoStatus
    total: float = Field(ge=0)
    criado_em: datetime
    atualizado_em: datetime
    motivo_cancelamento: str | None = None


class PreviewAcao(SchemaBase):
    """Previa segura; o token referencia os argumentos validados no servidor."""

    token: str
    acao: Acao
    argumentos: dict[str, Any] = Field(default_factory=dict)
    resumo: str
    requer_confirmacao: bool
    pergunta_confirmacao: str | None = None
    pode_executar: bool
    erros: list[str] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    data_referencia: date
    criado_em: datetime
    expira_em: datetime

    @property
    def mensagem_confirmacao(self) -> str | None:
        return self.pergunta_confirmacao


class ResultadoExecucao(SchemaBase):
    sucesso: bool
    acao: Acao
    mensagem: str
    protocolo: str | None = None
    dados: dict[str, Any] = Field(default_factory=dict)
    erros: list[str] = Field(default_factory=list)

