import pytest
from fastapi.testclient import TestClient

from src.server.main import app

client = TestClient(app)


@pytest.mark.skip(reason="It would change bucket data")
def test_predic():
    url = "/predict/"

    with open("data/testing/images/image_0.jpg", "rb") as img:
        # Form data with the image
        files = {"data": ("image_0.jpg", img, "image/jpeg")}

        # Send POST request with the image file
        response = client.post(url, files=files)

    assert response.status_code == 200
    assert "inference" in response.json()
    assert "message" in response.json()
