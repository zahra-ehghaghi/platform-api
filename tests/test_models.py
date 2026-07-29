import pytest
from pydantic import ValidationError

from app.models.service import ServiceCreateRequest, Language, Environment


class TestServiceCreateRequest:
    def test_valid_request_is_accepted(self):
        req = ServiceCreateRequest(
            name="payment-service",
            language="python",
            environment="dev",
        )
        assert req.name == "payment-service"
        assert req.language == Language.python
        assert req.environment == Environment.dev
        assert req.owner == "development"  # default value

    def test_name_must_start_with_lowercase_letter(self):
        with pytest.raises(ValidationError):
            ServiceCreateRequest(name="1payment", language="python", environment="dev")

    def test_name_rejects_uppercase(self):
        with pytest.raises(ValidationError):
            ServiceCreateRequest(name="Payment-Service", language="python", environment="dev")

    def test_name_rejects_underscore(self):
        with pytest.raises(ValidationError):
            ServiceCreateRequest(name="payment_service", language="python", environment="dev")

    def test_name_too_short_is_rejected(self):
        with pytest.raises(ValidationError):
            ServiceCreateRequest(name="ab", language="python", environment="dev")

    def test_name_too_long_is_rejected(self):
        with pytest.raises(ValidationError):
            ServiceCreateRequest(name="a" * 31, language="python", environment="dev")

    def test_unsupported_language_is_rejected(self):
        with pytest.raises(ValidationError):
            ServiceCreateRequest(name="payment-service", language="rust", environment="dev")

    def test_unsupported_environment_is_rejected(self):
        with pytest.raises(ValidationError):
            ServiceCreateRequest(name="payment-service", language="python", environment="staging")

    def test_owner_can_be_overridden(self):
        req = ServiceCreateRequest(
            name="payment-service",
            language="python",
            environment="dev",
            owner="payments-team",
        )
        assert req.owner == "payments-team"
