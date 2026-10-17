import io
from urllib.error import URLError
import pytest
from scripts import check_availability as monitor


@pytest.mark.parametrize("origin", ["http://ranch.example", "https://user:pass@ranch.example",
                                   "https://ranch.example/api", "https://ranch.example?token=secret"])
def test_monitor_requires_a_public_https_origin(origin):
    with pytest.raises(ValueError):
        monitor.check(origin)


@pytest.mark.parametrize("status,body,expected", [(200,b'{"status":"ready"}',True),
    (200,b'<html>SPA fallback</html>',False), (503,b'{"status":"ready"}',False),
    (200,b'{"status":"ok"}',False)])
def test_monitor_checks_readiness_payload(monkeypatch,status,body,expected):
    def response(url,timeout):
        assert url == 'https://ranch.example/health/ready'
        assert timeout == 10
        stream=io.BytesIO(body)
        stream.status=status
        return stream
    monkeypatch.setattr(monitor,'urlopen',response)
    assert monitor.check('https://ranch.example') is expected


def test_monitor_handles_network_failure(monkeypatch):
    def unavailable(*args,**kwargs):
        raise URLError('private diagnostic')
    monkeypatch.setattr(monitor,'urlopen',unavailable)
    assert monitor.check('https://ranch.example') is False
