"""SWIM-style gossip protocol for cluster membership."""

import asyncio
import random
import pickle
import time
import logging
from typing import Dict, List, Tuple

from src.protocol.message import Message, MessageType

logger = logging.getLogger("DistSys")


class UDPProtocol(asyncio.DatagramProtocol):
    def __init__(self):
        self.transport = None
    def connection_made(self, transport):
        self.transport = transport
    def datagram_received(self, data, addr):
        pass


class GossipProtocol:
    def __init__(self, node_id: str, port: int, peers: List[Tuple[str, int]] = None):
        self.node_id = node_id
        self.port = port
        self.peers = peers or []
        self.members: Dict[str, Dict] = {}
        self.suspected: Dict[str, float] = {}
        self.failure_timeout = 15.0
        self.gossip_interval = 2.0
        self.suspect_timeout = 5.0
        self._running = False
        
    async def start(self):
        self._running = True
        asyncio.create_task(self._gossip_loop())
        asyncio.create_task(self._failure_detector())
        
    async def _gossip_loop(self):
        while self._running:
            try:
                await self._send_gossip()
                await asyncio.sleep(self.gossip_interval)
            except Exception as e:
                logger.error(f"Gossip error: {e}")
                
    async def _send_gossip(self):
        if not self.peers:
            return
        targets = random.sample(self.peers, min(3, len(self.peers)))
        payload = {
            'members': self.members,
            'suspected': list(self.suspected.keys()),
            'sender': self.node_id,
            'load': 0.0
        }
        msg = Message(MessageType.GOSSIP, self.node_id, pickle.dumps(payload))
        for host, port in targets:
            try:
                await self._send_udp(host, port, msg.serialize())
            except Exception:
                pass
    
    async def _send_udp(self, host: str, port: int, data: bytes):
        loop = asyncio.get_event_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: UDPProtocol(), remote_addr=(host, port)
        )
        try:
            transport.sendto(data)
        finally:
            transport.close()
    
    async def _failure_detector(self):
        while self._running:
            now = time.time()
            for node_id, suspect_time in list(self.suspected.items()):
                if now - suspect_time > self.suspect_timeout:
                    logger.warning(f"Node {node_id} marked FAILED")
                    self.members.pop(node_id, None)
                    self.suspected.pop(node_id, None)
            for node_id, info in list(self.members.items()):
                if node_id == self.node_id:
                    continue
                last_seen = info.get('last_seen', 0)
                if now - last_seen > self.failure_timeout and node_id not in self.suspected:
                    logger.warning(f"Node {node_id} suspected")
                    self.suspected[node_id] = now
            await asyncio.sleep(1.0)
    
    def handle_gossip(self, msg: Message):
        try:
            data = pickle.loads(msg.payload)
            sender = data['sender']
            self.members[sender] = {'last_seen': time.time(), 'load': data.get('load', 0.0)}
            self.suspected.pop(sender, None)
            for node_id, info in data.get('members', {}).items():
                if node_id != self.node_id:
                    if node_id not in self.members or info.get('last_seen', 0) > self.members[node_id].get('last_seen', 0):
                        self.members[node_id] = info
            for node_id in data.get('suspected', []):
                if node_id in self.members and node_id not in self.suspected:
                    self.suspected[node_id] = time.time()
        except Exception as e:
            logger.error(f"Gossip process error: {e}")
    
    def stop(self):
        self._running = False