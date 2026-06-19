import json

import httpx
import respx

from arm_common import KeydbState
from arm_ripper.backend_client import BackendClient


@respx.mock
async def test_report_keydb_status_posts_body():
    route = respx.post("https://bk/api/ripper/keydb-status").mock(return_value=httpx.Response(204))
    client = BackendClient("https://bk", "tok", "host1")
    await client.report_keydb_status(state=KeydbState.OK, vuk_count=4200, age_days=0)
    await client.close()
    assert route.called
    sent = route.calls.last.request
    assert json.loads(sent.content) == {"state": "ok", "vuk_count": 4200, "age_days": 0}
