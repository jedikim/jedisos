"""
[JS-G003] jedisos.security.secvault
SecVault 코어 암호화 로직 - Argon2id 키 유도 + AES-256-GCM 암호화/복호화

version: 1.0.0
created: 2026-02-19
modified: 2026-02-19
dependencies: argon2-cffi>=23.1.0, cryptography>=46.0.5
"""

from __future__ import annotations

import base64
import json
import os
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import structlog
from argon2.low_level import Type as Argon2Type
from argon2.low_level import hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = structlog.get_logger()

# SecVault 마커 형식: [[SECDATA:AES256GCM:<nonce_b64>:<ciphertext_b64>:<tag_b64>]]
SECDATA_PATTERN = re.compile(
    r"\[\[SECDATA:AES256GCM:([A-Za-z0-9+/=]+):([A-Za-z0-9+/=]+):([A-Za-z0-9+/=]+)\]\]"
)

# Argon2id 파라미터
ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST = 65536  # 64 MiB
ARGON2_PARALLELISM = 4
ARGON2_HASH_LEN = 32  # 256-bit 키

# AES-256-GCM 상수
AES_KEY_LEN = 32  # 256-bit
AES_NONCE_LEN = 12  # 96-bit
AES_TAG_LEN = 16  # 128-bit (GCM 기본)


def derive_key(password: str, salt: bytes) -> bytes:  # [JS-G003.1]
    """Argon2id로 비밀번호에서 AES-256 키를 유도합니다.

    Args:
        password: 마스터 비밀번호
        salt: 32바이트 랜덤 salt

    Returns:
        32바이트 AES-256 키
    """
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST,
        parallelism=ARGON2_PARALLELISM,
        hash_len=ARGON2_HASH_LEN,
        type=Argon2Type.ID,
    )


def encrypt_data(plaintext: str, key: bytes) -> str:  # [JS-G003.2]
    """AES-256-GCM으로 평문을 암호화합니다.

    Args:
        plaintext: 암호화할 평문
        key: 32바이트 AES-256 키

    Returns:
        SecVault 마커 형식 문자열: [[SECDATA:AES256GCM:<nonce>:<ct>:<tag>]]
    """
    aesgcm = AESGCM(key)
    nonce = os.urandom(AES_NONCE_LEN)
    # AESGCM.encrypt는 ciphertext+tag를 하나로 반환
    ct_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    # tag는 마지막 16바이트
    ciphertext = ct_with_tag[:-AES_TAG_LEN]
    tag = ct_with_tag[-AES_TAG_LEN:]

    nonce_b64 = base64.b64encode(nonce).decode()
    ct_b64 = base64.b64encode(ciphertext).decode()
    tag_b64 = base64.b64encode(tag).decode()

    return f"[[SECDATA:AES256GCM:{nonce_b64}:{ct_b64}:{tag_b64}]]"


def decrypt_data(marker: str, key: bytes) -> str:  # [JS-G003.3]
    """SecVault 마커를 복호화합니다.

    Args:
        marker: [[SECDATA:AES256GCM:<nonce>:<ct>:<tag>]] 형식 문자열
        key: 32바이트 AES-256 키

    Returns:
        복호화된 평문

    Raises:
        ValueError: 마커 형식이 잘못된 경우
        cryptography.exceptions.InvalidTag: 키가 틀리거나 데이터가 변조된 경우
    """
    match = SECDATA_PATTERN.fullmatch(marker)
    if not match:
        raise ValueError(f"유효하지 않은 SecVault 마커: {marker[:50]}...")

    nonce = base64.b64decode(match.group(1))
    ciphertext = base64.b64decode(match.group(2))
    tag = base64.b64decode(match.group(3))

    aesgcm = AESGCM(key)
    plaintext_bytes = aesgcm.decrypt(nonce, ciphertext + tag, None)
    return plaintext_bytes.decode("utf-8")


def find_secdata_markers(text: str) -> list[str]:  # [JS-G003.4]
    """텍스트에서 모든 SecVault 마커를 찾습니다.

    Args:
        text: 검색할 텍스트

    Returns:
        발견된 마커 문자열 리스트
    """
    return SECDATA_PATTERN.findall(text)


def has_secdata(text: str) -> bool:  # [JS-G003.5]
    """텍스트에 SecVault 마커가 있는지 확인합니다."""
    return bool(SECDATA_PATTERN.search(text))


class MasterKeyFile:  # [JS-G003.6]
    """마스터 키 파일 관리.

    마스터 키는 Argon2id로 유도된 KEK(Key Encryption Key)로 암호화되어 저장됩니다.
    실제 데이터 암호화에는 마스터 키(DEK)를 사용합니다.

    파일 형식 (master.key):
    {
        "version": 1,
        "algorithm": "argon2id",
        "salt": "<base64_32bytes>",
        "encrypted_master_key": "<base64_aes256gcm>",
        "nonce": "<base64_12bytes>",
        "created_at": "2026-02-19T14:00:00Z"
    }
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def exists(self) -> bool:  # [JS-G003.6.1]
        """마스터 키 파일이 존재하는지 확인합니다."""
        return self.path.exists()

    def create(self, password: str) -> bytes:  # [JS-G003.6.2]
        """새 마스터 키를 생성하고 비밀번호로 보호하여 저장합니다.

        Args:
            password: 마스터 비밀번호

        Returns:
            생성된 마스터 키 (DEK)
        """
        from datetime import UTC, datetime

        # 랜덤 마스터 키(DEK) 생성
        master_key = os.urandom(AES_KEY_LEN)

        # 비밀번호에서 KEK 유도
        salt = os.urandom(32)
        kek = derive_key(password, salt)

        # KEK로 마스터 키 암호화
        aesgcm = AESGCM(kek)
        nonce = os.urandom(AES_NONCE_LEN)
        encrypted_mk = aesgcm.encrypt(nonce, master_key, None)

        data = {
            "version": 1,
            "algorithm": "argon2id",
            "salt": base64.b64encode(salt).decode(),
            "encrypted_master_key": base64.b64encode(encrypted_mk).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "created_at": datetime.now(UTC).isoformat(),
        }

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2))
        # 파일 권한을 소유자만 읽기/쓰기로 제한
        self.path.chmod(0o600)

        logger.info("master_key_created", path=str(self.path))
        return master_key

    def unlock(self, password: str) -> bytes:  # [JS-G003.6.3]
        """비밀번호로 마스터 키를 복호화합니다.

        Args:
            password: 마스터 비밀번호

        Returns:
            복호화된 마스터 키 (DEK)

        Raises:
            FileNotFoundError: 마스터 키 파일이 없는 경우
            cryptography.exceptions.InvalidTag: 비밀번호가 틀린 경우
        """
        if not self.exists():
            raise FileNotFoundError(f"마스터 키 파일이 없습니다: {self.path}")

        data = json.loads(self.path.read_text())

        salt = base64.b64decode(data["salt"])
        nonce = base64.b64decode(data["nonce"])
        encrypted_mk = base64.b64decode(data["encrypted_master_key"])

        # 비밀번호에서 KEK 유도
        kek = derive_key(password, salt)

        # KEK로 마스터 키 복호화
        aesgcm = AESGCM(kek)
        master_key = aesgcm.decrypt(nonce, encrypted_mk, None)

        logger.info("master_key_unlocked", path=str(self.path))
        return master_key

    def get_info(self) -> dict[str, Any]:  # [JS-G003.6.4]
        """마스터 키 파일 메타정보를 반환합니다 (민감 데이터 제외)."""
        if not self.exists():
            return {"exists": False}

        data = json.loads(self.path.read_text())
        return {
            "exists": True,
            "version": data.get("version"),
            "algorithm": data.get("algorithm"),
            "created_at": data.get("created_at"),
        }
