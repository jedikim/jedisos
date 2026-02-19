"""
[JS-G004] jedisos.security.secvault_daemon
SecVault 독립 복호화 데몬 - Unix Domain Socket 기반 IPC

version: 1.0.0
created: 2026-02-19
modified: 2026-02-19
dependencies: argon2-cffi>=23.1.0, cryptography>=46.0.5

라이프사이클:
1. 앱 시작 → SecVault 데몬 프로세스 spawn
2. master.key 없음 → "needs_setup" 상태
3. master.key 있음 → "locked" 상태 (비밀번호 필요)
4. 웹 UI에서 비밀번호 입력 → unlock → "unlocked" 상태
5. 이후 모든 encrypt/decrypt 요청 처리 가능
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from multiprocessing import Process
from pathlib import Path
from typing import Any

import structlog

from jedisos.security.secvault import MasterKeyFile, decrypt_data, encrypt_data

logger = structlog.get_logger()

# UDS 프로토콜:
# 요청: {"op": "encrypt|decrypt|unlock|setup|status|lock", "data": "...", "request_id": "uuid"}
# 응답: {"ok": true|false, "data": "...", "error": "...", "request_id": "uuid"}


class SecVaultDaemon:  # [JS-G004.1]
    """SecVault 독립 복호화 데몬.

    Unix Domain Socket으로 통신하며, 마스터 키를 메모리에 보유합니다.
    별도 프로세스로 실행되어 LLM에 키가 노출되지 않습니다.
    """

    MAX_ATTEMPTS = 5
    LOCKOUT_SECONDS = 300
    MAX_MESSAGE_SIZE = 1024 * 1024  # 1 MiB

    def __init__(self, secvault_dir: Path) -> None:
        self.secvault_dir = secvault_dir
        self.socket_path = secvault_dir / "vault.sock"
        self.master_key_file = MasterKeyFile(secvault_dir / "master.key")
        self._master_key: bytes | None = None
        self._failed_attempts = 0
        self._locked_until = 0.0
        self._running = False

    @property
    def status(self) -> str:  # [JS-G004.1.1]
        """현재 상태를 반환합니다."""
        if not self.master_key_file.exists():
            return "needs_setup"
        if self._master_key is None:
            return "locked"
        return "unlocked"

    def run(self) -> None:  # [JS-G004.2]
        """UDS 서버 루프를 실행합니다. multiprocessing.Process의 target으로 사용."""
        self._running = True
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        asyncio.run(self._serve())

    async def _serve(self) -> None:  # [JS-G004.2.1]
        """비동기 UDS 서버."""
        # 기존 소켓 파일 제거
        if self.socket_path.exists():
            self.socket_path.unlink()

        self.secvault_dir.mkdir(parents=True, exist_ok=True)

        server = await asyncio.start_unix_server(
            self._handle_connection,
            path=str(self.socket_path),
        )
        # 소켓 파일 권한 제한
        self.socket_path.chmod(0o600)

        logger.info("secvault_daemon_started", socket=str(self.socket_path), status=self.status)

        async with server:
            try:
                await server.serve_forever()
            except asyncio.CancelledError:
                pass
            finally:
                self._running = False
                logger.info("secvault_daemon_stopped")

    async def _handle_connection(  # [JS-G004.2.2]
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """단일 UDS 연결을 처리합니다."""
        try:
            data = await reader.read(self.MAX_MESSAGE_SIZE)
            if not data:
                return

            request = json.loads(data.decode("utf-8"))
            response = self._dispatch(request)

            writer.write(json.dumps(response).encode("utf-8"))
            await writer.drain()
        except json.JSONDecodeError:
            error_resp = {"ok": False, "error": "유효하지 않은 JSON", "request_id": ""}
            writer.write(json.dumps(error_resp).encode("utf-8"))
            await writer.drain()
        except Exception as e:
            logger.error("secvault_connection_error", error=str(e))
        finally:
            writer.close()
            await writer.wait_closed()

    def _dispatch(self, request: dict[str, Any]) -> dict[str, Any]:  # [JS-G004.3]
        """요청을 적절한 핸들러로 디스패치합니다."""
        op = request.get("op", "")
        data = request.get("data", "")
        request_id = request.get("request_id", "")

        handlers = {
            "setup": self._handle_setup,
            "unlock": self._handle_unlock,
            "encrypt": self._handle_encrypt,
            "decrypt": self._handle_decrypt,
            "status": self._handle_status,
            "lock": self._handle_lock,
        }

        handler = handlers.get(op)
        if not handler:
            return {"ok": False, "error": f"알 수 없는 작업: {op}", "request_id": request_id}

        try:
            result = handler(data) if op in ("setup", "unlock", "encrypt", "decrypt") else handler()
            result["request_id"] = request_id
            return result
        except Exception as e:
            logger.error("secvault_handler_error", op=op, error=str(e))
            return {"ok": False, "error": str(e), "request_id": request_id}

    def _handle_setup(self, password: str) -> dict[str, Any]:  # [JS-G004.4]
        """최초 비밀번호 설정."""
        if self.master_key_file.exists():
            return {"ok": False, "error": "마스터 키가 이미 존재합니다. lock/unlock을 사용하세요."}

        if len(password) < 4:
            return {"ok": False, "error": "비밀번호는 최소 4자 이상이어야 합니다."}

        self._master_key = self.master_key_file.create(password)
        self._failed_attempts = 0
        logger.info("secvault_setup_complete")
        return {"ok": True, "data": "setup_complete"}

    def _handle_unlock(self, password: str) -> dict[str, Any]:  # [JS-G004.5]
        """비밀번호 검증 + 마스터 키 언락."""
        import time

        if self._master_key is not None:
            return {"ok": True, "data": "already_unlocked"}

        if not self.master_key_file.exists():
            return {"ok": False, "error": "마스터 키가 없습니다. setup을 먼저 실행하세요."}

        # 잠금 상태 확인
        now = time.monotonic()
        if now < self._locked_until:
            remaining = int(self._locked_until - now)
            return {"ok": False, "error": f"계정 잠금 중. {remaining}초 후 재시도하세요."}

        try:
            self._master_key = self.master_key_file.unlock(password)
            self._failed_attempts = 0
            logger.info("secvault_unlocked")
            return {"ok": True, "data": "unlocked"}
        except Exception:
            self._failed_attempts += 1
            logger.warning("secvault_unlock_failed", attempts=self._failed_attempts)

            if self._failed_attempts >= self.MAX_ATTEMPTS:
                self._locked_until = time.monotonic() + self.LOCKOUT_SECONDS
                self._failed_attempts = 0
                return {
                    "ok": False,
                    "error": f"비밀번호 {self.MAX_ATTEMPTS}회 실패. {self.LOCKOUT_SECONDS}초간 잠금됩니다.",
                }

            remaining = self.MAX_ATTEMPTS - self._failed_attempts
            return {"ok": False, "error": f"비밀번호가 틀립니다. 남은 시도: {remaining}회"}

    def _handle_encrypt(self, plaintext: str) -> dict[str, Any]:  # [JS-G004.6]
        """평문을 암호화합니다."""
        if self._master_key is None:
            return {"ok": False, "error": "SecVault가 잠겨 있습니다. 먼저 unlock하세요."}

        marker = encrypt_data(plaintext, self._master_key)
        return {"ok": True, "data": marker}

    def _handle_decrypt(self, marker: str) -> dict[str, Any]:  # [JS-G004.7]
        """SecVault 마커를 복호화합니다."""
        if self._master_key is None:
            return {"ok": False, "error": "SecVault가 잠겨 있습니다. 먼저 unlock하세요."}

        plaintext = decrypt_data(marker, self._master_key)
        return {"ok": True, "data": plaintext}

    def _handle_status(self) -> dict[str, Any]:  # [JS-G004.8]
        """현재 상태를 반환합니다."""
        info = self.master_key_file.get_info()
        return {
            "ok": True,
            "data": {
                "status": self.status,
                "master_key_exists": info.get("exists", False),
                "created_at": info.get("created_at"),
            },
        }

    def _handle_lock(self) -> dict[str, Any]:  # [JS-G004.9]
        """마스터 키를 메모리에서 제거합니다."""
        self._master_key = None
        logger.info("secvault_locked")
        return {"ok": True, "data": "locked"}

    def _handle_signal(self, signum: int, _frame: Any) -> None:
        """시그널 핸들러."""
        logger.info("secvault_signal_received", signal=signum)
        self._running = False
        sys.exit(0)


def start_daemon(secvault_dir: str | Path) -> Process:  # [JS-G004.10]
    """SecVault 데몬을 별도 프로세스로 시작합니다.

    Args:
        secvault_dir: SecVault 데이터 디렉토리 경로

    Returns:
        시작된 Process 객체
    """
    secvault_dir = Path(secvault_dir)
    daemon = SecVaultDaemon(secvault_dir)

    process = Process(
        target=daemon.run,
        name="secvault-daemon",
        daemon=True,
    )
    process.start()
    logger.info("secvault_daemon_process_started", pid=process.pid)
    return process


def stop_daemon(process: Process) -> None:  # [JS-G004.11]
    """SecVault 데몬 프로세스를 종료합니다."""
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            os.kill(process.pid, signal.SIGKILL)
            process.join(timeout=2)
        logger.info("secvault_daemon_process_stopped", pid=process.pid)
