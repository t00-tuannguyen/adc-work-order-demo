import pytest

ORDER = {
    "product_group": "spice",
    "quantity": 120,
    "pkg_length_cm": 40,
    "pkg_width_cm": 30,
    "pkg_height_cm": 25,
    "pkg_weight_kg": 8,
    "required_dose_kgy": 10,
}


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.fixture
def signed_in(sign_in):
    return sign_in()


@pytest.mark.asyncio
async def test_estimate_requires_login(client):
    assert (await client.post("/api/estimate", json=ORDER)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.usefixtures("signed_in")
async def test_estimate(client):
    response = await client.post("/api/estimate", json=ORDER)
    assert response.status_code == 200
    data = response.json()
    assert data["duration_min"] == 180
    assert set(data["breakdown"]) == {"setup", "weight_load", "volume_load", "dose_load", "buffer"}


@pytest.mark.asyncio
@pytest.mark.usefixtures("signed_in")
@pytest.mark.parametrize("change", [{"quantity": 0}, {"product_group": "unknown"}, {"required_dose_kgy": 7}])
async def test_estimate_invalid_input_is_422(client, change):
    response = await client.post("/api/estimate", json={**ORDER, **change})
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.usefixtures("signed_in")
async def test_throughput_config_exposed(client):
    response = await client.get("/api/config/throughput")
    assert response.status_code == 200
    assert response.json()["setup_min"] == 30
