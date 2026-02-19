"""
[JS-G005] jedisos.security.secvault_client
SecVault 비동기 UDS 클라이언트 - 데몬과 통신하는 인터페이스

version: 1.0.0
created: 2026-02-19
modified: 2026-02-19
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import structlog

from jedisos.security.secvault import SECDATA_PATTERN

logger = structlog.get_logger()

# 재시도 설정
_CONNECT_RETRIES = 3
_CONNECT_DELAY = 0.5  # 초
_READ_TIMEOUT = 10.0  # 초
_MAX_RESPONSE_SIZE = 1024 * 1024  # 1 MiB


class SecVaultClient:  # [JS-G005.1]
    """SecVault 데몬과 UDS로 통신하는 비동기 클라이언트.

    사용법:
        client = SecVaultClient("/data/.secvault")
        status = await client.status()
        if status["status"] == "needs_setup":
            await client.setup("my-password")
        elif status["status"] == "locked":
            await client.unlock("my-password")
        encrypted = await client.encrypt("비밀 정보")
        decrypted = await client.decrypt(encrypted)
    """

    def __init__(self, secvault_dir: str | Path) -> None:
        self.socket_path = Path(secvault_dir) / "vault.sock"

    async def _send(self, request: dict[str, Any]) -> dict[str, Any]:  # [JS-G005.2]
        """UDS를 통해 데몬에 요청을 보내고 응답을 받습니다.

        Args:
            request: JSON 직렬화 가능한 요청 딕셔너리

        Returns:
            데몬 응답 딕셔너리

        Raises:
            ConnectionError: 데몬에 연결할 수 없는 경우
            TimeoutError: 응답 타임아웃
        """
        last_error: Exception | None = None

        for attempt in range(1, _CONNECT_RETRIES + 1):
            try:
                reader, writer = await asyncio.open_unix_connection(str(self.socket_path))
                try:
                    writer.write(json.dumps(request).encode("utf-8"))
                    await writer.drain()

                    data = await asyncio.wait_for(
                        reader.read(_MAX_RESPONSE_SIZE),
                        timeout=_READ_TIMEOUT,
                    )
                    if not data:
                        raise ConnectionError("데몬으로부터 빈 응답")

                    return json.loads(data.decode("utf-8"))
                finally:
                    writer.close()
                    await writer.wait_closed()
            except (ConnectionRefusedError, FileNotFoundError, OSError) as e:
                last_error = e
                if attempt < _CONNECT_RETRIES:
                    logger.debug(
                        "secvault_connect_retry",
                        attempt=attempt,
                        error=str(e),
                    )
                    await asyncio.sleep(_CONNECT_DELAY * attempt)

        raise ConnectionError(
            f"SecVault 데몬에 연결할 수 없습니다 ({_CONNECT_RETRIES}회 시도): {last_error}"
        )

    async def encrypt(self, plaintext: str) -> str:  # [JS-G005.3]
        """평문을 암호화합니다.

        Args:
            plaintext: 암호화할 평문

        Returns:
            SecVault 마커 문자열: [[SECDATA:AES256GCM:<nonce>:<ct>:<tag>]]

        Raises:
            ConnectionError: 데몬 연결 실패
            RuntimeError: 암호화 실패
        """
        resp = await self._send({"op": "encrypt", "data": plaintext})
        if not resp.get("ok"):
            raise RuntimeError(f"암호화 실패: {resp.get('error')}")
        return resp["data"]

    async def decrypt(self, marker: str) -> str:  # [JS-G005.4]
        """SecVault 마커를 복호화합니다.

        Args:
            marker: [[SECDATA:AES256GCM:...]] 형식 문자열

        Returns:
            복호화된 평문

        Raises:
            ConnectionError: 데몬 연결 실패
            RuntimeError: 복호화 실패
        """
        resp = await self._send({"op": "decrypt", "data": marker})
        if not resp.get("ok"):
            raise RuntimeError(f"복호화 실패: {resp.get('error')}")
        return resp["data"]

    async def decrypt_all(self, text: str) -> str:  # [JS-G005.5]
        """텍스트 내의 모든 SecVault 마커를 복호화합니다.

        Args:
            text: SecVault 마커가 포함된 텍스트

        Returns:
            모든 마커가 복호화된 텍스트
        """
        markers = SECDATA_PATTERN.findall(text)
        if not markers:
            return text

        result = text
        for nonce_b64, ct_b64, tag_b64 in markers:
            full_marker = f"[[SECDATA:AES256GCM:{nonce_b64}:{ct_b64}:{tag_b64}]]"
            try:
                plaintext = await self.decrypt(full_marker)
                result = result.replace(full_marker, plaintext)
            except RuntimeError:
                logger.warning("secvault_decrypt_marker_failed", marker=full_marker[:30])
        return result

    async def unlock(self, password: str) -> bool:  # [JS-G005.6]
        """비밀번호로 SecVault를 언락합니다.

        Args:
            password: 마스터 비밀번호

        Returns:
            성공 여부
        """
        resp = await self._send({"op": "unlock", "data": password})
        if resp.get("ok"):
            logger.info("secvault_client_unlock_success")
            return True
        logger.warning("secvault_client_unlock_failed", error=resp.get("error"))
        return False

    async def setup(self, password: str) -> bool:  # [JS-G005.7]
        """최초 비밀번호를 설정합니다.

        Args:
            password: 마스터 비밀번호 (최소 4자)

        Returns:
            성공 여부
        """
        resp = await self._send({"op": "setup", "data": password})
        if resp.get("ok"):
            logger.info("secvault_client_setup_success")
            return True
        logger.warning("secvault_client_setup_failed", error=resp.get("error"))
        return False

    async def status(self) -> dict[str, Any]:  # [JS-G005.8]
        """SecVault 상태를 조회합니다.

        Returns:
            {"status": "needs_setup|locked|unlocked", ...}
        """
        resp = await self._send({"op": "status"})
        if resp.get("ok"):
            return resp["data"]
        return {"status": "unknown", "error": resp.get("error")}

    async def lock(self) -> bool:  # [JS-G005.9]
        """SecVault를 잠급니다 (마스터 키를 메모리에서 제거)."""
        resp = await self._send({"op": "lock"})
        return bool(resp.get("ok"))

    async def is_locked(self) -> bool:  # [JS-G005.10]
        """SecVault가 잠겨있는지 확인합니다."""
        st = await self.status()
        return st.get("status") != "unlocked"
