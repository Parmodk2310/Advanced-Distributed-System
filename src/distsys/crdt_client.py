"""Topology-transparent one-shot client for Phase-4 causal CRDT operations."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from distsys.causal import CausalToken
from distsys.crdt import CrdtType
from distsys.protocol.framing import DEFAULT_MAX_FRAME_SIZE, encode_frame, read_message
from distsys.protocol.message import Message, MessageType
from distsys.replication.codec import (
    CrdtMutationData,
    CrdtReadData,
    CrdtResponseData,
    decode_crdt_response,
    encode_mutation_request,
    encode_read_request,
)


class CrdtCorrelationMismatch(ConnectionError):
    pass


class RemoteCrdtError(RuntimeError):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class CrdtResult:
    key: str
    crdt_type: CrdtType
    value: Any
    causal_token: CausalToken
    served_by: str
    repair_performed: bool


class CrdtClient:
    """One-shot CRDT client that monotonically accumulates a session token."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8000,
        client_id: str = "crdt-client",
        timeout_seconds: float = 5.0,
        max_frame_size: int = DEFAULT_MAX_FRAME_SIZE,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self.timeout_seconds = timeout_seconds
        self.max_frame_size = max_frame_size
        self.causal_token = CausalToken.empty()

    def _token(self, explicit: CausalToken | None) -> CausalToken:
        if explicit is None:
            return self.causal_token
        return self.causal_token.merge(explicit)

    async def _exchange(
        self,
        msg_type: MessageType,
        payload: bytes,
    ) -> CrdtResponseData:
        request = Message.new_request(
            sender_id=self.client_id,
            msg_type=msg_type,
            payload=payload,
        )
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port),
            timeout=self.timeout_seconds,
        )
        try:
            writer.write(encode_frame(request, max_frame_size=self.max_frame_size))
            await asyncio.wait_for(writer.drain(), timeout=self.timeout_seconds)
            response = await asyncio.wait_for(
                read_message(reader, max_frame_size=self.max_frame_size),
                timeout=self.timeout_seconds,
            )
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass
        if response.correlation_id != request.correlation_id:
            raise CrdtCorrelationMismatch(
                f"expected {request.correlation_id}, got {response.correlation_id}"
            )
        if response.msg_type is not MessageType.CRDT_RESPONSE:
            raise ConnectionError(f"expected CRDT_RESPONSE, got {response.msg_type.name}")
        decoded = decode_crdt_response(response.payload)
        if not decoded.success:
            raise RemoteCrdtError(decoded.error_code, decoded.error_message)
        self.causal_token = self.causal_token.merge(decoded.causal_token)
        return decoded

    def _result(self, key: str, response: CrdtResponseData) -> CrdtResult:
        if response.crdt_type is None:
            raise ConnectionError("successful CRDT response did not include a CRDT type")
        return CrdtResult(
            key=key,
            crdt_type=response.crdt_type,
            value=response.value,
            causal_token=self.causal_token,
            served_by=response.served_by,
            repair_performed=response.repair_performed,
        )

    async def _mutate(
        self,
        *,
        key: str,
        crdt_type: CrdtType,
        operation: str,
        value: Any = None,
        amount: int = 0,
        causal_token: CausalToken | None = None,
    ) -> CrdtResult:
        request = CrdtMutationData(
            key=key,
            crdt_type=crdt_type,
            operation=operation,
            value=value,
            amount=amount,
            causal_token=self._token(causal_token),
        )
        response = await self._exchange(
            MessageType.CRDT_MUTATE_REQUEST,
            encode_mutation_request(request),
        )
        return self._result(key, response)

    async def increment(
        self,
        key: str,
        *,
        amount: int = 1,
        causal_token: CausalToken | None = None,
        crdt_type: CrdtType = CrdtType.GCOUNTER,
    ) -> CrdtResult:
        if crdt_type not in (CrdtType.GCOUNTER, CrdtType.PNCOUNTER):
            raise ValueError("increment supports GCounter or PNCounter")
        return await self._mutate(
            key=key,
            crdt_type=crdt_type,
            operation="increment",
            amount=amount,
            causal_token=causal_token,
        )

    async def decrement(
        self,
        key: str,
        *,
        amount: int = 1,
        causal_token: CausalToken | None = None,
    ) -> CrdtResult:
        return await self._mutate(
            key=key,
            crdt_type=CrdtType.PNCOUNTER,
            operation="decrement",
            amount=amount,
            causal_token=causal_token,
        )

    async def add(
        self,
        key: str,
        element: str,
        *,
        causal_token: CausalToken | None = None,
    ) -> CrdtResult:
        return await self._mutate(
            key=key,
            crdt_type=CrdtType.ORSET,
            operation="add",
            value=element,
            causal_token=causal_token,
        )

    async def remove(
        self,
        key: str,
        element: str,
        *,
        causal_token: CausalToken | None = None,
    ) -> CrdtResult:
        return await self._mutate(
            key=key,
            crdt_type=CrdtType.ORSET,
            operation="remove",
            value=element,
            causal_token=causal_token,
        )

    async def write_register(
        self,
        key: str,
        value: Any,
        *,
        causal_token: CausalToken | None = None,
    ) -> CrdtResult:
        return await self._mutate(
            key=key,
            crdt_type=CrdtType.MVREGISTER,
            operation="write",
            value=value,
            causal_token=causal_token,
        )

    async def read(
        self,
        key: str,
        *,
        causal_token: CausalToken | None = None,
    ) -> CrdtResult:
        response = await self._exchange(
            MessageType.CRDT_READ_REQUEST,
            encode_read_request(CrdtReadData(key=key, causal_token=self._token(causal_token))),
        )
        return self._result(key, response)
