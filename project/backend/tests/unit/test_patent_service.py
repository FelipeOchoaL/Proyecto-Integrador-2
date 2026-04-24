import pytest
from unittest.mock import MagicMock

from app.services.patent_service import PatentService


def test_get_all_propaga_error_de_conexion():
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.execute.side_effect = (
        ConnectionError("Supabase no responde")
    )

    service = PatentService(mock_client)

    with pytest.raises(ConnectionError, match="Supabase no responde"):
        service.get_all(page=1, page_size=10)
