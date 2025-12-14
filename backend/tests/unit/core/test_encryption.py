"""
Unit tests for the encryption service.

Tests field-level encryption with per-tenant key derivation.
"""

import pytest
from uuid import uuid4, UUID
from cryptography.fernet import Fernet

from app.core.encryption import (
    EncryptionService,
    EncryptionError,
    EncryptionKeyError,
    DecryptionError,
    get_encryption_service,
    reset_encryption_service,
)


# Test fixtures
@pytest.fixture
def valid_master_key() -> str:
    """Generate a valid Fernet key for testing."""
    return Fernet.generate_key().decode("utf-8")


@pytest.fixture
def encryption_service(valid_master_key: str) -> EncryptionService:
    """Create an encryption service with a valid key."""
    return EncryptionService(master_key=valid_master_key, enabled=True)


@pytest.fixture
def tenant_id() -> UUID:
    """Generate a test tenant ID."""
    return uuid4()


@pytest.fixture
def another_tenant_id() -> UUID:
    """Generate another test tenant ID for isolation tests."""
    return uuid4()


# Initialization Tests
class TestEncryptionServiceInit:
    """Tests for EncryptionService initialization."""

    def test_init_with_valid_key(self, valid_master_key: str):
        """Test initialization with a valid Fernet key."""
        service = EncryptionService(master_key=valid_master_key, enabled=True)
        assert service._enabled is True
        assert service._master_key is not None

    def test_init_disabled_no_key_required(self):
        """Test initialization with encryption disabled doesn't require key."""
        service = EncryptionService(master_key=None, enabled=False)
        assert service._enabled is False
        assert service._master_key is None

    def test_init_enabled_no_key_raises(self):
        """Test that enabling encryption without a key raises an error."""
        with pytest.raises(EncryptionKeyError, match="required when encryption is enabled"):
            EncryptionService(master_key=None, enabled=True)

    def test_init_with_placeholder_key_raises(self):
        """Test that placeholder keys are rejected."""
        # Note: empty string "" is handled by the "no key" check, not placeholder check
        placeholders = [
            "change-me-in-production",
            "your-encryption-key-here",
            "CHANGE_ME",
        ]
        for placeholder in placeholders:
            with pytest.raises(EncryptionKeyError, match="placeholder value"):
                EncryptionService(master_key=placeholder, enabled=True)

    def test_init_with_invalid_key_format_raises(self):
        """Test that invalid key formats are rejected."""
        with pytest.raises(EncryptionKeyError, match="Invalid master encryption key format"):
            EncryptionService(master_key="not-a-valid-fernet-key", enabled=True)


# Key Generation Tests
class TestKeyGeneration:
    """Tests for key generation utilities."""

    def test_generate_key_produces_valid_fernet_key(self):
        """Test that generate_key produces a valid Fernet key."""
        key = EncryptionService.generate_key()
        # Should not raise - key should be valid
        service = EncryptionService(master_key=key, enabled=True)
        assert service._master_key is not None

    def test_generate_key_produces_unique_keys(self):
        """Test that generate_key produces unique keys."""
        keys = {EncryptionService.generate_key() for _ in range(100)}
        assert len(keys) == 100  # All unique


# Encryption/Decryption Tests
class TestEncryptDecrypt:
    """Tests for encrypt/decrypt operations."""

    def test_encrypt_returns_prefixed_string(
        self, encryption_service: EncryptionService, tenant_id: UUID
    ):
        """Test that encrypted values have the version prefix."""
        plaintext = "my-secret-api-key"
        encrypted = encryption_service.encrypt(plaintext, tenant_id)
        assert encrypted.startswith(EncryptionService.ENCRYPTED_PREFIX)

    def test_encrypt_decrypt_roundtrip(
        self, encryption_service: EncryptionService, tenant_id: UUID
    ):
        """Test that encryption and decryption are inverse operations."""
        plaintext = "my-secret-api-key-12345"
        encrypted = encryption_service.encrypt(plaintext, tenant_id)
        decrypted = encryption_service.decrypt(encrypted, tenant_id)
        assert decrypted == plaintext

    def test_encrypt_empty_string_returns_empty(
        self, encryption_service: EncryptionService, tenant_id: UUID
    ):
        """Test that empty strings are returned as-is."""
        assert encryption_service.encrypt("", tenant_id) == ""
        assert encryption_service.encrypt(None, tenant_id) is None

    def test_decrypt_empty_string_returns_empty(
        self, encryption_service: EncryptionService, tenant_id: UUID
    ):
        """Test that empty strings are returned as-is."""
        assert encryption_service.decrypt("", tenant_id) == ""
        assert encryption_service.decrypt(None, tenant_id) is None

    def test_decrypt_unencrypted_value_returns_as_is(
        self, encryption_service: EncryptionService, tenant_id: UUID
    ):
        """Test that non-encrypted values pass through (migration support)."""
        plaintext = "not-encrypted-value"
        result = encryption_service.decrypt(plaintext, tenant_id)
        assert result == plaintext

    def test_encrypt_with_field_name_for_logging(
        self, encryption_service: EncryptionService, tenant_id: UUID
    ):
        """Test that field_name parameter doesn't affect encryption."""
        plaintext = "secret"
        encrypted1 = encryption_service.encrypt(plaintext, tenant_id, field_name="api_key")
        encrypted2 = encryption_service.encrypt(plaintext, tenant_id, field_name="password")
        # Both should decrypt to same value
        assert encryption_service.decrypt(encrypted1, tenant_id) == plaintext
        assert encryption_service.decrypt(encrypted2, tenant_id) == plaintext

    def test_encrypt_different_values_produce_different_ciphertext(
        self, encryption_service: EncryptionService, tenant_id: UUID
    ):
        """Test that different plaintexts produce different ciphertexts."""
        encrypted1 = encryption_service.encrypt("value1", tenant_id)
        encrypted2 = encryption_service.encrypt("value2", tenant_id)
        assert encrypted1 != encrypted2

    def test_encrypt_same_value_twice_produces_different_ciphertext(
        self, encryption_service: EncryptionService, tenant_id: UUID
    ):
        """Test that Fernet's random IV produces different ciphertexts."""
        plaintext = "same-value"
        encrypted1 = encryption_service.encrypt(plaintext, tenant_id)
        encrypted2 = encryption_service.encrypt(plaintext, tenant_id)
        # Different ciphertexts due to random IV
        assert encrypted1 != encrypted2
        # But both decrypt to the same value
        assert encryption_service.decrypt(encrypted1, tenant_id) == plaintext
        assert encryption_service.decrypt(encrypted2, tenant_id) == plaintext


# Tenant Isolation Tests
class TestTenantIsolation:
    """Tests for per-tenant key derivation and isolation."""

    def test_different_tenants_produce_different_ciphertext(
        self,
        encryption_service: EncryptionService,
        tenant_id: UUID,
        another_tenant_id: UUID,
    ):
        """Test that the same plaintext encrypts differently per tenant."""
        plaintext = "shared-secret"
        encrypted1 = encryption_service.encrypt(plaintext, tenant_id)
        encrypted2 = encryption_service.encrypt(plaintext, another_tenant_id)
        # Different ciphertexts due to different derived keys
        assert encrypted1 != encrypted2

    def test_cannot_decrypt_other_tenant_data(
        self,
        encryption_service: EncryptionService,
        tenant_id: UUID,
        another_tenant_id: UUID,
    ):
        """Test that one tenant cannot decrypt another tenant's data."""
        plaintext = "tenant-secret"
        encrypted = encryption_service.encrypt(plaintext, tenant_id)

        # Attempting to decrypt with another tenant's key should fail
        with pytest.raises(DecryptionError, match="corrupted or encrypted with a different key"):
            encryption_service.decrypt(encrypted, another_tenant_id)

    def test_tenant_cipher_caching(
        self, encryption_service: EncryptionService, tenant_id: UUID
    ):
        """Test that tenant ciphers are cached for performance."""
        # First call creates the cipher
        encryption_service.encrypt("value1", tenant_id)
        assert tenant_id in encryption_service._tenant_ciphers

        # Second call should use cached cipher
        initial_cipher = encryption_service._tenant_ciphers[tenant_id]
        encryption_service.encrypt("value2", tenant_id)
        assert encryption_service._tenant_ciphers[tenant_id] is initial_cipher

    def test_clear_tenant_cache_specific(
        self, encryption_service: EncryptionService, tenant_id: UUID
    ):
        """Test clearing cache for a specific tenant."""
        encryption_service.encrypt("value", tenant_id)
        assert tenant_id in encryption_service._tenant_ciphers

        encryption_service.clear_tenant_cache(tenant_id)
        assert tenant_id not in encryption_service._tenant_ciphers

    def test_clear_tenant_cache_all(
        self,
        encryption_service: EncryptionService,
        tenant_id: UUID,
        another_tenant_id: UUID,
    ):
        """Test clearing cache for all tenants."""
        encryption_service.encrypt("value", tenant_id)
        encryption_service.encrypt("value", another_tenant_id)
        assert len(encryption_service._tenant_ciphers) == 2

        encryption_service.clear_tenant_cache()
        assert len(encryption_service._tenant_ciphers) == 0


# Disabled Mode Tests
class TestDisabledMode:
    """Tests for passthrough mode when encryption is disabled."""

    @pytest.fixture
    def disabled_service(self) -> EncryptionService:
        """Create an encryption service with encryption disabled."""
        return EncryptionService(master_key=None, enabled=False)

    def test_encrypt_passthrough_when_disabled(
        self, disabled_service: EncryptionService, tenant_id: UUID
    ):
        """Test that encryption returns plaintext when disabled."""
        plaintext = "my-api-key"
        result = disabled_service.encrypt(plaintext, tenant_id)
        assert result == plaintext

    def test_decrypt_passthrough_when_disabled(
        self, disabled_service: EncryptionService, tenant_id: UUID
    ):
        """Test that decryption returns input when disabled."""
        ciphertext = "enc:v1:some-encrypted-data"
        result = disabled_service.decrypt(ciphertext, tenant_id)
        assert result == ciphertext


# Dictionary Field Encryption Tests
class TestDictFieldEncryption:
    """Tests for dictionary field encryption utilities."""

    def test_encrypt_dict_field_simple(
        self, encryption_service: EncryptionService, tenant_id: UUID
    ):
        """Test encrypting a simple field in a dictionary."""
        data = {"api_key": "secret-key", "name": "test"}
        result = encryption_service.encrypt_dict_field(data, "api_key", tenant_id)

        # Original unchanged
        assert data["api_key"] == "secret-key"
        # Result has encrypted field
        assert result["api_key"].startswith(EncryptionService.ENCRYPTED_PREFIX)
        assert result["name"] == "test"

    def test_encrypt_dict_field_nested(
        self, encryption_service: EncryptionService, tenant_id: UUID
    ):
        """Test encrypting a nested field in a dictionary."""
        data = {
            "provider": "ollama",
            "auth": {"token": "secret-token", "user": "admin"},
        }
        result = encryption_service.encrypt_dict_field(data, "auth.token", tenant_id)

        assert result["auth"]["token"].startswith(EncryptionService.ENCRYPTED_PREFIX)
        assert result["auth"]["user"] == "admin"
        assert result["provider"] == "ollama"

    def test_encrypt_dict_field_missing_path(
        self, encryption_service: EncryptionService, tenant_id: UUID
    ):
        """Test that missing field path returns unchanged dict."""
        data = {"name": "test"}
        result = encryption_service.encrypt_dict_field(data, "nonexistent", tenant_id)
        assert result == data

    def test_decrypt_dict_field_roundtrip(
        self, encryption_service: EncryptionService, tenant_id: UUID
    ):
        """Test encrypt/decrypt roundtrip for dict fields."""
        original = {"api_key": "my-secret", "name": "test"}
        encrypted = encryption_service.encrypt_dict_field(original, "api_key", tenant_id)
        decrypted = encryption_service.decrypt_dict_field(encrypted, "api_key", tenant_id)

        assert decrypted["api_key"] == "my-secret"
        assert decrypted["name"] == "test"


# Utility Method Tests
class TestUtilityMethods:
    """Tests for utility methods."""

    def test_is_encrypted_true(self, encryption_service: EncryptionService, tenant_id: UUID):
        """Test is_encrypted returns True for encrypted values."""
        encrypted = encryption_service.encrypt("secret", tenant_id)
        assert encryption_service.is_encrypted(encrypted) is True

    def test_is_encrypted_false_plain(self, encryption_service: EncryptionService):
        """Test is_encrypted returns False for plain values."""
        assert encryption_service.is_encrypted("plain-text") is False

    def test_is_encrypted_false_empty(self, encryption_service: EncryptionService):
        """Test is_encrypted returns False for empty values."""
        assert encryption_service.is_encrypted("") is False
        assert encryption_service.is_encrypted(None) is False

    def test_mask_value_default(self):
        """Test masking with default visible characters."""
        assert EncryptionService.mask_value("my-secret-api-key") == "****-key"

    def test_mask_value_custom_visible(self):
        """Test masking with custom visible characters."""
        assert EncryptionService.mask_value("my-secret-api-key", visible_chars=8) == "****-api-key"

    def test_mask_value_short_string(self):
        """Test masking a short string."""
        assert EncryptionService.mask_value("abc", visible_chars=4) == "****"

    def test_mask_value_empty(self):
        """Test masking an empty string."""
        assert EncryptionService.mask_value("") == "****"


# Error Handling Tests
class TestErrorHandling:
    """Tests for error handling scenarios."""

    def test_decrypt_corrupted_data_raises(
        self, encryption_service: EncryptionService, tenant_id: UUID
    ):
        """Test that corrupted encrypted data raises DecryptionError."""
        corrupted = f"{EncryptionService.ENCRYPTED_PREFIX}corrupted-data"
        with pytest.raises(DecryptionError):
            encryption_service.decrypt(corrupted, tenant_id)

    def test_decrypt_tampered_data_raises(
        self, encryption_service: EncryptionService, tenant_id: UUID
    ):
        """Test that tampered encrypted data raises DecryptionError."""
        encrypted = encryption_service.encrypt("secret", tenant_id)
        # Tamper with the ciphertext
        tampered = encrypted[:-10] + "XXXXXXXXXX"
        with pytest.raises(DecryptionError):
            encryption_service.decrypt(tampered, tenant_id)


# Global Service Tests
class TestGlobalService:
    """Tests for global service management."""

    def test_reset_encryption_service(self):
        """Test that reset clears the global service."""
        reset_encryption_service()
        # After reset, getting service should create a new one
        # (This would fail if ENCRYPTION_MASTER_KEY isn't set in test env)
        # Just test that reset doesn't raise
        reset_encryption_service()


# Unicode and Special Characters Tests
class TestSpecialCharacters:
    """Tests for handling special characters."""

    def test_encrypt_decrypt_unicode(
        self, encryption_service: EncryptionService, tenant_id: UUID
    ):
        """Test encryption/decryption of unicode strings."""
        unicode_text = "日本語テスト 🔐 émojis"
        encrypted = encryption_service.encrypt(unicode_text, tenant_id)
        decrypted = encryption_service.decrypt(encrypted, tenant_id)
        assert decrypted == unicode_text

    def test_encrypt_decrypt_special_chars(
        self, encryption_service: EncryptionService, tenant_id: UUID
    ):
        """Test encryption/decryption of strings with special characters."""
        special = "key=value&foo=bar\n\t\"quotes\"'apostrophe'"
        encrypted = encryption_service.encrypt(special, tenant_id)
        decrypted = encryption_service.decrypt(encrypted, tenant_id)
        assert decrypted == special

    def test_encrypt_decrypt_long_string(
        self, encryption_service: EncryptionService, tenant_id: UUID
    ):
        """Test encryption/decryption of long strings."""
        long_text = "a" * 10000
        encrypted = encryption_service.encrypt(long_text, tenant_id)
        decrypted = encryption_service.decrypt(encrypted, tenant_id)
        assert decrypted == long_text
