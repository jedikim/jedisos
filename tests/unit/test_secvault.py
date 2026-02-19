"""
[JS-T015] tests.unit.test_secvault
SecVault 암호화/복호화/UDS 프로토콜 단위 테스트

version: 1.0.0
created: 2026-02-19
modified: 2026-02-19
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

import pytest

from jedisos.security.secvault import (
    SECDATA_PATTERN,
    MasterKeyFile,
    decrypt_data,
    derive_key,
    encrypt_data,
    find_secdata_markers,
    has_secdata,
)
from jedisos.security.secvault_daemon import SecVaultDaemon

if TYPE_CHECKING:
    from pathlib import Path


# === secvault.py 코어 암호화 테스트 ===


class TestDeriveKey:  # [JS-T015.1]
    """Argon2id 키 유도 테스트."""

    def test_derive_key_returns_32_bytes(self) -> None:
        key = derive_key("test-password", b"0" * 32)
        assert len(key) == 32

    def test_derive_key_deterministic(self) -> None:
        salt = b"fixed-salt-for-testing!!" + b"\x00" * 8  # 32 bytes
        key1 = derive_key("password", salt)
        key2 = derive_key("password", salt)
        assert key1 == key2

    def test_derive_key_different_passwords(self) -> None:
        salt = b"0" * 32
        key1 = derive_key("password1", salt)
        key2 = derive_key("password2", salt)
        assert key1 != key2

    def test_derive_key_different_salts(self) -> None:
        key1 = derive_key("password", b"a" * 32)
        key2 = derive_key("password", b"b" * 32)
        assert key1 != key2


class TestEncryptDecrypt:  # [JS-T015.2]
    """AES-256-GCM 암호화/복호화 테스트."""

    def test_encrypt_returns_marker_format(self) -> None:
        key = derive_key("test", b"0" * 32)
        marker = encrypt_data("hello", key)
        assert marker.startswith("[[SECDATA:AES256GCM:")
        assert marker.endswith("]]")

    def test_encrypt_decrypt_roundtrip(self) -> None:
        key = derive_key("test", b"0" * 32)
        plaintext = "비밀번호: my-secret-123!"
        marker = encrypt_data(plaintext, key)
        decrypted = decrypt_data(marker, key)
        assert decrypted == plaintext

    def test_encrypt_decrypt_unicode(self) -> None:
        key = derive_key("test", b"0" * 32)
        plaintext = "주민등록번호: 900101-1234567 🔒"
        marker = encrypt_data(plaintext, key)
        decrypted = decrypt_data(marker, key)
        assert decrypted == plaintext

    def test_decrypt_wrong_key_fails(self) -> None:
        from cryptography.exceptions import InvalidTag

        key1 = derive_key("correct", b"0" * 32)
        key2 = derive_key("wrong", b"0" * 32)
        marker = encrypt_data("secret", key1)
        with pytest.raises(InvalidTag):
            decrypt_data(marker, key2)

    def test_decrypt_invalid_marker_fails(self) -> None:
        key = derive_key("test", b"0" * 32)
        with pytest.raises(ValueError, match="유효하지 않은"):
            decrypt_data("not-a-marker", key)

    def test_encrypt_produces_different_ciphertext(self) -> None:
        """같은 평문도 매번 다른 nonce로 암호화."""
        key = derive_key("test", b"0" * 32)
        m1 = encrypt_data("same", key)
        m2 = encrypt_data("same", key)
        assert m1 != m2  # nonce가 다르므로

    def test_marker_matches_regex(self) -> None:
        key = derive_key("test", b"0" * 32)
        marker = encrypt_data("data", key)
        assert SECDATA_PATTERN.fullmatch(marker)


class TestMarkerUtils:  # [JS-T015.3]
    """SecVault 마커 유틸리티 테스트."""

    def test_has_secdata_true(self) -> None:
        key = derive_key("test", b"0" * 32)
        marker = encrypt_data("secret", key)
        text = f"비밀번호는 {marker} 입니다."
        assert has_secdata(text) is True

    def test_has_secdata_false(self) -> None:
        assert has_secdata("일반 텍스트입니다.") is False

    def test_find_secdata_markers(self) -> None:
        key = derive_key("test", b"0" * 32)
        m1 = encrypt_data("a", key)
        m2 = encrypt_data("b", key)
        text = f"첫 번째: {m1} 두 번째: {m2}"
        found = find_secdata_markers(text)
        assert len(found) == 2


# === MasterKeyFile 테스트 ===


class TestMasterKeyFile:  # [JS-T015.4]
    """마스터 키 파일 생성/언락 테스트."""

    def test_create_and_unlock(self, tmp_path: Path) -> None:
        mkf = MasterKeyFile(tmp_path / "master.key")
        assert not mkf.exists()

        master_key = mkf.create("my-password")
        assert mkf.exists()
        assert len(master_key) == 32

        unlocked_key = mkf.unlock("my-password")
        assert unlocked_key == master_key

    def test_unlock_wrong_password(self, tmp_path: Path) -> None:
        from cryptography.exceptions import InvalidTag

        mkf = MasterKeyFile(tmp_path / "master.key")
        mkf.create("correct-password")

        with pytest.raises(InvalidTag):
            mkf.unlock("wrong-password")

    def test_unlock_no_file(self, tmp_path: Path) -> None:
        mkf = MasterKeyFile(tmp_path / "nonexistent.key")
        with pytest.raises(FileNotFoundError):
            mkf.unlock("password")

    def test_get_info_no_file(self, tmp_path: Path) -> None:
        mkf = MasterKeyFile(tmp_path / "master.key")
        info = mkf.get_info()
        assert info["exists"] is False

    def test_get_info_with_file(self, tmp_path: Path) -> None:
        mkf = MasterKeyFile(tmp_path / "master.key")
        mkf.create("password")
        info = mkf.get_info()
        assert info["exists"] is True
        assert info["version"] == 1
        assert info["algorithm"] == "argon2id"
        assert "created_at" in info

    def test_file_permissions(self, tmp_path: Path) -> None:
        mkf = MasterKeyFile(tmp_path / "master.key")
        mkf.create("password")
        # 0o600 = 소유자만 읽기/쓰기
        mode = mkf.path.stat().st_mode & 0o777
        assert mode == 0o600


# === SecVaultDaemon 단위 테스트 (프로세스 없이) ===


class TestSecVaultDaemon:  # [JS-T015.5]
    """데몬 핸들러 직접 호출 테스트."""

    def _make_daemon(self, tmp_path: Path) -> SecVaultDaemon:
        return SecVaultDaemon(tmp_path / ".secvault")

    def test_initial_status_needs_setup(self, tmp_path: Path) -> None:
        d = self._make_daemon(tmp_path)
        assert d.status == "needs_setup"

    def test_setup_flow(self, tmp_path: Path) -> None:
        d = self._make_daemon(tmp_path)
        result = d._handle_setup("my-password")
        assert result["ok"] is True
        assert d.status == "unlocked"

    def test_setup_too_short_password(self, tmp_path: Path) -> None:
        d = self._make_daemon(tmp_path)
        result = d._handle_setup("ab")
        assert result["ok"] is False
        assert "최소 4자" in result["error"]

    def test_setup_duplicate(self, tmp_path: Path) -> None:
        d = self._make_daemon(tmp_path)
        d._handle_setup("password")
        result = d._handle_setup("password2")
        assert result["ok"] is False
        assert "이미 존재" in result["error"]

    def test_lock_unlock_flow(self, tmp_path: Path) -> None:
        d = self._make_daemon(tmp_path)
        d._handle_setup("password")
        assert d.status == "unlocked"

        d._handle_lock()
        assert d.status == "locked"

        result = d._handle_unlock("password")
        assert result["ok"] is True
        assert d.status == "unlocked"

    def test_unlock_wrong_password(self, tmp_path: Path) -> None:
        d = self._make_daemon(tmp_path)
        d._handle_setup("correct")
        d._handle_lock()

        result = d._handle_unlock("wrong")
        assert result["ok"] is False
        assert "틀립니다" in result["error"]

    def test_encrypt_decrypt_flow(self, tmp_path: Path) -> None:
        d = self._make_daemon(tmp_path)
        d._handle_setup("password")

        enc_result = d._handle_encrypt("비밀 데이터")
        assert enc_result["ok"] is True
        marker = enc_result["data"]
        assert marker.startswith("[[SECDATA:")

        dec_result = d._handle_decrypt(marker)
        assert dec_result["ok"] is True
        assert dec_result["data"] == "비밀 데이터"

    def test_encrypt_while_locked(self, tmp_path: Path) -> None:
        d = self._make_daemon(tmp_path)
        d._handle_setup("password")
        d._handle_lock()

        result = d._handle_encrypt("data")
        assert result["ok"] is False
        assert "잠겨" in result["error"]

    def test_status_response(self, tmp_path: Path) -> None:
        d = self._make_daemon(tmp_path)
        result = d._handle_status()
        assert result["ok"] is True
        assert result["data"]["status"] == "needs_setup"

    def test_dispatch_unknown_op(self, tmp_path: Path) -> None:
        d = self._make_daemon(tmp_path)
        result = d._dispatch({"op": "invalid", "request_id": "test-1"})
        assert result["ok"] is False
        assert "알 수 없는" in result["error"]
        assert result["request_id"] == "test-1"

    def test_lockout_after_max_attempts(self, tmp_path: Path) -> None:
        d = self._make_daemon(tmp_path)
        d._handle_setup("correct")
        d._handle_lock()

        for _ in range(SecVaultDaemon.MAX_ATTEMPTS):
            d._handle_unlock("wrong")

        result = d._handle_unlock("correct")
        assert result["ok"] is False
        assert "잠금" in result["error"]


# === SecVaultClient + 데몬 통합 테스트 (실제 UDS) ===


class TestSecVaultClientDaemon:  # [JS-T015.6]
    """클라이언트-데몬 UDS 통신 테스트."""

    @pytest.fixture
    async def vault_pair(self, tmp_path: Path):
        """데몬을 asyncio로 실행하고 클라이언트를 반환합니다."""
        from jedisos.security.secvault_client import SecVaultClient

        secvault_dir = tmp_path / ".secvault"
        daemon = SecVaultDaemon(secvault_dir)

        # 데몬을 백그라운드 태스크로 실행
        server_task = asyncio.create_task(daemon._serve())

        # 소켓 파일이 생길 때까지 대기
        for _ in range(50):
            if daemon.socket_path.exists():
                break
            await asyncio.sleep(0.05)

        client = SecVaultClient(secvault_dir)
        yield client, daemon

        # 정리
        server_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await server_task

    async def test_status_needs_setup(self, vault_pair) -> None:
        client, _ = vault_pair
        status = await client.status()
        assert status["status"] == "needs_setup"

    async def test_setup_and_unlock(self, vault_pair) -> None:
        client, _ = vault_pair
        ok = await client.setup("my-password")
        assert ok is True

        status = await client.status()
        assert status["status"] == "unlocked"

        ok = await client.lock()
        assert ok is True

        locked = await client.is_locked()
        assert locked is True

        ok = await client.unlock("my-password")
        assert ok is True

    async def test_encrypt_decrypt_roundtrip(self, vault_pair) -> None:
        client, _ = vault_pair
        await client.setup("password")

        marker = await client.encrypt("비밀번호: 1234")
        assert "SECDATA" in marker

        plaintext = await client.decrypt(marker)
        assert plaintext == "비밀번호: 1234"

    async def test_decrypt_all(self, vault_pair) -> None:
        client, _ = vault_pair
        await client.setup("password")

        m1 = await client.encrypt("secret1")
        m2 = await client.encrypt("secret2")
        text = f"A: {m1} B: {m2}"

        result = await client.decrypt_all(text)
        assert "secret1" in result
        assert "secret2" in result
        assert "SECDATA" not in result

    async def test_connection_error(self, tmp_path: Path) -> None:
        """데몬 없이 연결 시 ConnectionError."""
        from jedisos.security.secvault_client import SecVaultClient

        client = SecVaultClient(tmp_path / "nonexistent")
        with pytest.raises(ConnectionError, match="연결할 수 없습니다"):
            await client.status()
