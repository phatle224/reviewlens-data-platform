from __future__ import annotations

import hashlib
import json
import os
from uuid import uuid4

import httpx
import pytest

from reviewlens.config import DataMode, load_settings
from reviewlens.providers.r2 import R2Client

pytestmark = pytest.mark.live


@pytest.mark.skipif(
    os.environ.get("REVIEWLENS_RUN_LIVE_R2") != "1",
    reason="set REVIEWLENS_RUN_LIVE_R2=1 to run the synthetic R2 smoke test",
)
def test_private_r2_synthetic_round_trip_and_cleanup() -> None:
    settings = load_settings()
    assert settings.data_mode is DataMode.SYNTHETIC
    client = R2Client.from_config(settings.r2)
    key = f"manifests/_smoke/{uuid4()}.json"
    body = json.dumps(
        {"data_class": "synthetic", "source": "reviewlens-r2-live-smoke"},
        sort_keys=True,
    ).encode()
    checksum = hashlib.sha256(body).hexdigest()

    try:
        uploaded = client.put_bytes(
            key,
            body,
            content_type="application/json",
            metadata={"data-class": "synthetic", "sha256": checksum},
        )
        assert uploaded.size == len(body)
        assert uploaded.metadata["data-class"] == "synthetic"
        assert uploaded.metadata["sha256"] == checksum
        assert hashlib.sha256(client.get_bytes(key)).hexdigest() == checksum
        assert key in client.list_keys("manifests/_smoke/")
        assert client.account_level_bucket_listing_is_denied()

        response = httpx.get(client.anonymous_object_url(key), timeout=10, follow_redirects=False)
        assert response.status_code in {400, 401, 403, 404}
        assert response.content != body
    finally:
        client.delete(key)

    assert not client.exists(key)
