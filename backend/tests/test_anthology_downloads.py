import httpx
import pytest
from figprism.network import fetch

@pytest.mark.asyncio
async def test_official_anthology_download_and_redirect_boundary(client,monkeypatch):
    redirect=False
    requested=[]
    async def reply(request):
        requested.append(str(request.url))
        if redirect:return httpx.Response(302,headers={'location':'https://untrusted.invalid/paper.pdf'})
        return httpx.Response(200,content=b'%PDF-test')
    original=httpx.AsyncClient
    def fake(**kwargs):return original(transport=httpx.MockTransport(reply),**kwargs)
    monkeypatch.setattr(httpx,'AsyncClient',fake)
    url='https://aclanthology.org/2026.acl-long.1.pdf'
    assert await fetch(url)==b'%PDF-test'
    redirect=True
    with pytest.raises(ValueError,match='白名单'):
        await fetch(url)
    assert requested==[url,url]
    for bad in ['https://aclanthology.org.evil.invalid/a.pdf','http://aclanthology.org/a.pdf','https://user@aclanthology.org/a.pdf']:
        with pytest.raises(ValueError):await fetch(bad)
