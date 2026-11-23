# Heiman Local Client

An asynchronous Python client for a direct Heiman Wi-Fi switch implementing the `heiman_wifi_v1` LAN HTTP protocol. The caller supplies and closes an `aiohttp.ClientSession`.

```python
from aiohttp import ClientSession
from heiman_local_client import HeimanSwitchClient


async def read_switch_power(host: str) -> bool:
    async with ClientSession() as session:
        switch = HeimanSwitchClient(session, host, 80)
        info = await switch.get_info()
        return await switch.get_power(info)
```

Build a wheel and source distribution with `uv build`. To test the Home Assistant Core integration locally, install the wheel in the Core development environment before running its integration tests.

## Releasing

Set the public source repository URL under `[project.urls]` in `pyproject.toml`. In PyPI, configure a Trusted Publisher for this repository with the workflow filename `publish.yml` and the GitHub environment `pypi`.

Publish a GitHub release with a tag matching the package version, such as `v0.1.0`. The workflow checks the tag, builds and checks the distributions, and publishes them to PyPI. Include the public workflow and release-tag links in the Home Assistant Core pull request.
