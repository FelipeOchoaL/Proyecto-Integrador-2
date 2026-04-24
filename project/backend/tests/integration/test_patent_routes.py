from unittest.mock import MagicMock


def test_list_patents_happy_path(client, mock_supabase):
    fake_rows = [
        {"id": 1, "pn": "US123", "ti": "Invento 1"},
        {"id": 2, "pn": "US456", "ti": "Invento 2"},
    ]

    count_response = MagicMock(count=2)
    data_response = MagicMock(data=fake_rows)

    table = mock_supabase.table.return_value
    table.select.return_value.execute.return_value = count_response
    table.select.return_value.order.return_value.range.return_value.execute.return_value = (
        data_response
    )

    response = client.get("/patentes/")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["page"] == 1
    assert body["page_size"] == 50
    assert len(body["data"]) == 2
    assert body["data"][0]["pn"] == "US123"
