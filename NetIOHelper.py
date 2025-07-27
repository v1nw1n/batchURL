import asyncio
import aiohttp
import aiodns
import socket
from urllib.parse import urlparse
import logging

class NetIOHelper:
    def __init__(self, proxy_url=None, custom_dns=None):
        self.proxy_url = proxy_url
        self.custom_dns = custom_dns
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)  #确保设置在前
        self.resolver = aiodns.DNSResolver(loop=self.loop)  #显式传递 loop
        self.session = self.loop.run_until_complete(self._init_session())

    async def _init_session(self):
        connector = aiohttp.TCPConnector(ssl=False)
        return aiohttp.ClientSession(connector=connector)

    def resolve_ip(self, url):
        return self.loop.run_until_complete(self._resolve_ip_async(url))

    def net_check(self, url):
        return self.loop.run_until_complete(self._net_check_async(url))

    async def _resolve_ip_async(self, url):
        domain = urlparse(url).hostname
        try:
            if self.custom_dns:
                self.resolver.nameservers = [self.custom_dns]
            result = await self.resolver.gethostbyname(domain, socket.AF_INET)
            return result.addresses[0] if result.addresses else ""
        except:
            try:
                return socket.gethostbyname(domain)
            except:
                return ""

    async def _net_check_async(self, target_url, timeout=5):
        result = {
            "target": target_url,
            "proxy_status": None,
            "direct_status": None,
            "proxy_code": None,
            "direct_code": None,
            "result": None
        }

        try:
            async with self.session.get(target_url, timeout=timeout) as resp:
                result["direct_status"] = True
                result["direct_code"] = resp.status
        except:
            result["direct_status"] = False

        if self.proxy_url:
            try:
                async with self.session.get(target_url, proxy=self.proxy_url, timeout=timeout) as resp:
                    result["proxy_status"] = True
                    result["proxy_code"] = resp.status
            except:
                result["proxy_status"] = False

        ps = result["proxy_status"]
        ds = result["direct_status"]
        pc = result["proxy_code"]
        dc = result["direct_code"]

        if ps and ds:
            if pc == dc:
                result["result"] = "任意网络"
            elif pc in [403, 405, 502] and dc < 400:
                result["result"] = "直连访问"
            else:
                result["result"] = "直连访问【需确认】"
        elif ps and not ds:
            result["result"] = "代理访问"
        elif not ps and ds:
            result["result"] = "直连访问"
        else:
            result["result"] = "不可访问"

        logging.info(f"proxy_status->{ps}:direct_status->{ds}:proxy_code->{pc}:direct_code->{dc}:{target_url}")
        return result["result"]

    def close(self):
        self.loop.run_until_complete(self.session.close())
        self.loop.close()