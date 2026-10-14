"""Persistencia SQLite e regras transacionais de pedidos/estoque."""

from __future__ import annotations

import re
import sqlite3
import threading
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .schemas import Pedido, PedidoItem, PedidoStatus, ProdutoEstoque


class RepositoryError(RuntimeError):
    pass


class ProdutoNaoEncontradoError(RepositoryError):
    pass


class EstoqueInsuficienteError(RepositoryError):
    pass


class PedidoNaoEncontradoError(RepositoryError):
    pass


class OperacaoInvalidaError(RepositoryError):
    pass


class SQLiteRepository:
    """Repositorio autocontido, adequado para a demonstracao local da POC."""

    _CATALOGO_INICIAL = (
        ("Café", "cafe", "caixa", 4250, 50),
        ("Açúcar", "acucar", "pacote", 850, 120),
        ("Arroz", "arroz", "fardo", 11890, 100),
        ("Leite", "leite", "caixa", 5590, 80),
        ("Farinha", "farinha", "pacote", 780, 75),
        ("Chá", "cha", "caixa", 1875, 45),
        ("Óleo", "oleo", "caixa", 9870, 60),
        ("Água mineral", "agua mineral", "fardo", 2640, 90),
        ("Papel toalha", "papel toalha", "pacote", 1290, 70),
        ("Detergente", "detergente", "caixa", 4580, 65),
    )
    _UNIDADES = {
        "caixa": "caixa",
        "caixas": "caixa",
        "cx": "caixa",
        "pacote": "pacote",
        "pacotes": "pacote",
        "pct": "pacote",
        "fardo": "fardo",
        "fardos": "fardo",
    }

    def __init__(self, database_path: str | Path = "data/pedidoflow.db") -> None:
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).expanduser().resolve().parent.mkdir(
                parents=True, exist_ok=True
            )
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self.database_path,
            check_same_thread=False,
            timeout=10,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 10000")
        if self.database_path != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
        self._criar_schema()
        self._popular_catalogo()

    def _criar_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS produtos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    chave TEXT NOT NULL UNIQUE,
                    unidade TEXT NOT NULL,
                    preco_centavos INTEGER NOT NULL CHECK (preco_centavos >= 0),
                    estoque INTEGER NOT NULL CHECK (estoque >= 0)
                );

                CREATE TABLE IF NOT EXISTS pedidos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cliente TEXT NOT NULL,
                    endereco_entrega TEXT NOT NULL,
                    data_entrega TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('criado', 'cancelado')),
                    total_centavos INTEGER NOT NULL CHECK (total_centavos >= 0),
                    motivo_cancelamento TEXT,
                    criado_em TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pedido_itens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pedido_id INTEGER NOT NULL REFERENCES pedidos(id),
                    produto_id INTEGER NOT NULL REFERENCES produtos(id),
                    produto_nome TEXT NOT NULL,
                    quantidade INTEGER NOT NULL CHECK (quantidade > 0),
                    unidade TEXT NOT NULL,
                    preco_unitario_centavos INTEGER NOT NULL CHECK (
                        preco_unitario_centavos >= 0
                    )
                );

                CREATE INDEX IF NOT EXISTS idx_pedido_itens_pedido
                ON pedido_itens(pedido_id);
                """
            )

    def _popular_catalogo(self) -> None:
        with self._lock, self._connection:
            self._connection.executemany(
                """
                INSERT OR IGNORE INTO produtos
                    (nome, chave, unidade, preco_centavos, estoque)
                VALUES (?, ?, ?, ?, ?)
                """,
                self._CATALOGO_INICIAL,
            )

    def listar_produtos(self) -> list[ProdutoEstoque]:
        with self._lock:
            linhas = self._connection.execute(
                """
                SELECT id, nome, unidade, preco_centavos, estoque
                FROM produtos ORDER BY nome
                """
            ).fetchall()
        return [self._produto_da_linha(linha) for linha in linhas]

    def obter_produto(self, nome: str) -> ProdutoEstoque:
        chave = self._normalizar_chave(nome)
        with self._lock:
            linha = self._connection.execute(
                """
                SELECT id, nome, unidade, preco_centavos, estoque
                FROM produtos WHERE chave = ?
                """,
                (chave,),
            ).fetchone()
        if linha is None:
            raise ProdutoNaoEncontradoError(f"Produto '{nome}' nao encontrado no catalogo.")
        return self._produto_da_linha(linha)

    def orcar_itens(self, itens: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Valida produtos/estoque e calcula valores, sem alterar o banco."""

        agrupados: dict[str, int] = {}
        nomes_originais: dict[str, str] = {}
        unidades_solicitadas: dict[str, set[str]] = {}
        for item in itens:
            if not isinstance(item, Mapping):
                raise OperacaoInvalidaError(
                    "Cada item deve ser um objeto com produto, quantidade e unidade."
                )
            nome = str(item.get("produto", "")).strip()
            quantidade = item.get("quantidade")
            unidade = self._normalizar_unidade(item.get("unidade"))
            if not nome:
                raise OperacaoInvalidaError("Todo item precisa informar o produto.")
            if unidade is None:
                raise OperacaoInvalidaError(
                    f"Informe uma unidade valida para '{nome}' (caixa, pacote ou fardo)."
                )
            if isinstance(quantidade, bool) or not isinstance(quantidade, int) or quantidade <= 0:
                raise OperacaoInvalidaError(
                    f"A quantidade de '{nome}' deve ser um numero inteiro maior que zero."
                )
            chave = self._normalizar_chave(nome)
            agrupados[chave] = agrupados.get(chave, 0) + quantidade
            nomes_originais[chave] = nome
            unidades_solicitadas.setdefault(chave, set()).add(unidade)

        if not agrupados:
            raise OperacaoInvalidaError("Inclua ao menos um item no pedido.")

        itens_validados: list[dict[str, Any]] = []
        total_centavos = 0
        with self._lock:
            for chave, quantidade in agrupados.items():
                linha = self._connection.execute(
                    "SELECT * FROM produtos WHERE chave = ?", (chave,)
                ).fetchone()
                if linha is None:
                    raise ProdutoNaoEncontradoError(
                        f"Produto '{nomes_originais[chave]}' nao encontrado no catalogo."
                    )
                unidade_catalogo = self._normalizar_unidade(linha["unidade"])
                if unidades_solicitadas[chave] != {unidade_catalogo}:
                    informadas = ", ".join(sorted(unidades_solicitadas[chave]))
                    raise OperacaoInvalidaError(
                        f"Unidade incompativel para {linha['nome']}: o catalogo usa "
                        f"'{linha['unidade']}', mas foi informado '{informadas}'."
                    )
                if linha["estoque"] < quantidade:
                    raise EstoqueInsuficienteError(
                        f"Estoque insuficiente para {linha['nome']}: solicitado "
                        f"{quantidade}, disponivel {linha['estoque']}."
                    )
                subtotal = linha["preco_centavos"] * quantidade
                total_centavos += subtotal
                itens_validados.append(
                    {
                        "produto_id": linha["id"],
                        "produto": linha["nome"],
                        "quantidade": quantidade,
                        "unidade": linha["unidade"],
                        "preco_unitario_centavos": linha["preco_centavos"],
                        "preco_unitario": linha["preco_centavos"] / 100,
                        "subtotal_centavos": subtotal,
                        "subtotal": subtotal / 100,
                    }
                )
        return {
            "itens": itens_validados,
            "total_centavos": total_centavos,
            "total": total_centavos / 100,
        }

    def criar_pedido(
        self,
        *,
        cliente: str,
        itens: Sequence[Mapping[str, Any]],
        endereco_entrega: str,
        data_entrega: date | str,
    ) -> Pedido:
        entrega_iso = self._data_iso(data_entrega)
        agora = self._agora_iso()
        with self._lock, self._connection:
            orcamento = self.orcar_itens(itens)
            cursor = self._connection.execute(
                """
                INSERT INTO pedidos (
                    cliente, endereco_entrega, data_entrega, status,
                    total_centavos, criado_em, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cliente.strip(),
                    endereco_entrega.strip(),
                    entrega_iso,
                    PedidoStatus.CRIADO.value,
                    orcamento["total_centavos"],
                    agora,
                    agora,
                ),
            )
            pedido_id = int(cursor.lastrowid)
            for item in orcamento["itens"]:
                atualizado = self._connection.execute(
                    """
                    UPDATE produtos SET estoque = estoque - ?
                    WHERE id = ? AND estoque >= ?
                    """,
                    (item["quantidade"], item["produto_id"], item["quantidade"]),
                )
                if atualizado.rowcount != 1:
                    raise EstoqueInsuficienteError(
                        f"O estoque de {item['produto']} mudou antes da confirmacao."
                    )
                self._connection.execute(
                    """
                    INSERT INTO pedido_itens (
                        pedido_id, produto_id, produto_nome, quantidade,
                        unidade, preco_unitario_centavos
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pedido_id,
                        item["produto_id"],
                        item["produto"],
                        item["quantidade"],
                        item["unidade"],
                        item["preco_unitario_centavos"],
                    ),
                )
        return self.consultar_pedido(pedido_id)

    def consultar_pedido(self, numero_pedido: int) -> Pedido:
        with self._lock:
            return self._carregar_pedido(numero_pedido)

    def listar_pedidos(self, limite: int = 100) -> list[Pedido]:
        limite_seguro = max(1, min(int(limite), 500))
        with self._lock:
            ids = self._connection.execute(
                "SELECT id FROM pedidos ORDER BY id DESC LIMIT ?", (limite_seguro,)
            ).fetchall()
            return [self._carregar_pedido(linha["id"]) for linha in ids]

    def cancelar_pedido(self, numero_pedido: int, motivo: str) -> Pedido:
        if not motivo.strip():
            raise OperacaoInvalidaError("Informe o motivo do cancelamento.")
        with self._lock, self._connection:
            pedido = self._carregar_pedido(numero_pedido)
            if pedido.status == PedidoStatus.CANCELADO:
                raise OperacaoInvalidaError(f"O pedido {numero_pedido} ja esta cancelado.")
            itens = self._connection.execute(
                "SELECT produto_id, quantidade FROM pedido_itens WHERE pedido_id = ?",
                (numero_pedido,),
            ).fetchall()
            for item in itens:
                self._connection.execute(
                    "UPDATE produtos SET estoque = estoque + ? WHERE id = ?",
                    (item["quantidade"], item["produto_id"]),
                )
            self._connection.execute(
                """
                UPDATE pedidos
                SET status = ?, motivo_cancelamento = ?, atualizado_em = ?
                WHERE id = ?
                """,
                (
                    PedidoStatus.CANCELADO.value,
                    motivo.strip(),
                    self._agora_iso(),
                    numero_pedido,
                ),
            )
        return self.consultar_pedido(numero_pedido)

    def alterar_entrega(
        self,
        numero_pedido: int,
        *,
        novo_endereco: str | None = None,
        nova_data_entrega: date | str | None = None,
    ) -> Pedido:
        if not novo_endereco and nova_data_entrega is None:
            raise OperacaoInvalidaError(
                "Informe um novo endereco, um novo prazo ou ambos."
            )
        with self._lock, self._connection:
            pedido = self._carregar_pedido(numero_pedido)
            if pedido.status != PedidoStatus.CRIADO:
                raise OperacaoInvalidaError(
                    f"Nao e possivel alterar um pedido com status '{pedido.status.value}'."
                )
            endereco = novo_endereco.strip() if novo_endereco else pedido.endereco_entrega
            entrega = (
                self._data_iso(nova_data_entrega)
                if nova_data_entrega is not None
                else pedido.data_entrega.isoformat()
            )
            self._connection.execute(
                """
                UPDATE pedidos
                SET endereco_entrega = ?, data_entrega = ?, atualizado_em = ?
                WHERE id = ?
                """,
                (endereco, entrega, self._agora_iso(), numero_pedido),
            )
        return self.consultar_pedido(numero_pedido)

    def fechar(self) -> None:
        with self._lock:
            self._connection.close()

    def _carregar_pedido(self, numero_pedido: int) -> Pedido:
        try:
            numero = int(numero_pedido)
        except (TypeError, ValueError) as exc:
            raise PedidoNaoEncontradoError("Numero de pedido invalido.") from exc
        linha = self._connection.execute(
            "SELECT * FROM pedidos WHERE id = ?", (numero,)
        ).fetchone()
        if linha is None:
            raise PedidoNaoEncontradoError(f"Pedido {numero} nao encontrado.")
        linhas_itens = self._connection.execute(
            """
            SELECT produto_id, produto_nome, quantidade, unidade,
                   preco_unitario_centavos
            FROM pedido_itens WHERE pedido_id = ? ORDER BY id
            """,
            (numero,),
        ).fetchall()
        itens = [
            PedidoItem(
                produto_id=item["produto_id"],
                produto=item["produto_nome"],
                quantidade=item["quantidade"],
                unidade=item["unidade"],
                preco_unitario=item["preco_unitario_centavos"] / 100,
                subtotal=(item["preco_unitario_centavos"] * item["quantidade"]) / 100,
            )
            for item in linhas_itens
        ]
        return Pedido(
            numero_pedido=linha["id"],
            cliente=linha["cliente"],
            itens=itens,
            endereco_entrega=linha["endereco_entrega"],
            data_entrega=date.fromisoformat(linha["data_entrega"]),
            status=PedidoStatus(linha["status"]),
            total=linha["total_centavos"] / 100,
            motivo_cancelamento=linha["motivo_cancelamento"],
            criado_em=datetime.fromisoformat(linha["criado_em"]),
            atualizado_em=datetime.fromisoformat(linha["atualizado_em"]),
        )

    @staticmethod
    def _produto_da_linha(linha: sqlite3.Row) -> ProdutoEstoque:
        return ProdutoEstoque(
            id=linha["id"],
            nome=linha["nome"],
            unidade=linha["unidade"],
            preco_unitario=linha["preco_centavos"] / 100,
            estoque=linha["estoque"],
        )

    @staticmethod
    def _normalizar_chave(nome: str) -> str:
        sem_acentos = "".join(
            caractere
            for caractere in unicodedata.normalize("NFKD", nome.lower().strip())
            if not unicodedata.combining(caractere)
        )
        return re.sub(r"[^a-z0-9]+", " ", sem_acentos).strip()

    @classmethod
    def _normalizar_unidade(cls, unidade: Any) -> str | None:
        if not isinstance(unidade, str) or not unidade.strip():
            return None
        chave = cls._normalizar_chave(unidade)
        return cls._UNIDADES.get(chave)

    @staticmethod
    def _data_iso(valor: date | str) -> str:
        if isinstance(valor, date):
            return valor.isoformat()
        try:
            return date.fromisoformat(str(valor)).isoformat()
        except ValueError as exc:
            raise OperacaoInvalidaError(
                "A data de entrega deve estar no formato AAAA-MM-DD."
            ) from exc

    @staticmethod
    def _agora_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
