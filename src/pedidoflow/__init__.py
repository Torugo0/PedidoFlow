"""Nucleo do PedidoFlow.

O pacote separa interpretacao, validacao, regras de negocio e persistencia.  A
camada de interface precisa conhecer apenas :class:`PedidoService` e os
contratos expostos neste modulo.
"""

from .database import (
    EstoqueInsuficienteError,
    OperacaoInvalidaError,
    PedidoNaoEncontradoError,
    ProdutoNaoEncontradoError,
    RepositoryError,
    SQLiteRepository,
)
from .date_resolver import DateResolutionError, DateResolver
from .schemas import (
    Acao,
    ItemSolicitado,
    Pedido,
    PedidoItem,
    PedidoStatus,
    PreviewAcao,
    ProdutoEstoque,
    ResolucaoData,
    ResultadoExecucao,
    ToolCall,
)
from .service import PedidoService

__all__ = [
    "Acao",
    "DateResolutionError",
    "DateResolver",
    "EstoqueInsuficienteError",
    "ItemSolicitado",
    "OperacaoInvalidaError",
    "Pedido",
    "PedidoItem",
    "PedidoNaoEncontradoError",
    "PedidoService",
    "PedidoStatus",
    "PreviewAcao",
    "ProdutoEstoque",
    "ProdutoNaoEncontradoError",
    "ResolucaoData",
    "RepositoryError",
    "ResultadoExecucao",
    "SQLiteRepository",
    "ToolCall",
]
