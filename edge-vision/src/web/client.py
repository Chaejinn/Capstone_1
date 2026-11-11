"""Small bounded HTTP client with explicit errors and no credential logging."""
import json
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class WebError(RuntimeError):
    pass


class PoseClient:
    def __init__(self, origin, token='', timeout=3, opener=None):
        parsed = urlsplit(origin)
        local = parsed.hostname in ('localhost','127.0.0.1','::1')
        if (parsed.scheme not in ('https','http') or (parsed.scheme=='http' and not local)
                or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in ('','/') or parsed.query or parsed.fragment):
            raise ValueError('WEB_BACKEND_URL must be an HTTPS origin (HTTP allowed only on localhost)')
        if not 0 < timeout <= 10:
            raise ValueError('timeout must be in (0,10] seconds')
        self.origin, self.token, self.timeout = origin.rstrip('/'), token, timeout
        self.opener = opener or build_opener(NoRedirect())

    def request(self, path, body=None):
        data = json.dumps(body,allow_nan=False).encode() if body is not None else None
        headers = {'Content-Type':'application/json'}
        if body is not None:
            if len(self.token)<32:
                raise WebError('WEB_BACKEND_TOKEN must contain the dedicated service key (at least 32 characters)')
            headers['Authorization']='Bearer '+self.token
        req = Request(self.origin+path, data=data, headers=headers,
                      method='POST' if body is not None else 'GET')
        try:
            with self.opener.open(req,timeout=self.timeout) as response:
                raw=response.read(65537)
                if len(raw)>65536:
                    raise WebError('Response exceeds 64 KiB')
                return json.loads(raw)
        except HTTPError as exc:
            status=exc.code
            raw=exc.read(4097);exc.close()
            reason={401:'check WEB_BACKEND_TOKEN',403:'check site/camera scope',
                    404:'web endpoint is not deployed',409:'old frame or active producer',
                    422:'check timestamp, measured offset and metre coordinates',
                    503:'web receiver configuration is missing'}.get(status,'HTTP request rejected')
            try:
                detail=json.loads(raw).get('detail')
                if isinstance(detail,dict) and detail.get('code')=='INVALID_TIMESTAMP':
                    age=detail.get('observed_age_seconds')
                    if type(age) in (int,float):reason+=f'; observed_age_seconds={age:g}; synchronize PC clock'
            except (ValueError,AttributeError):
                pass
            raise WebError(f'HTTP {status}: {reason}') from None
        except (OSError,ValueError):
            raise WebError('Network connection or JSON response failed') from None

    def check_clock(self):
        from datetime import datetime
        before=time.time()
        data=self.request('/api/edge/time')
        after=time.time()
        server=datetime.fromisoformat(data['server_time'].replace('Z','+00:00')).timestamp()
        offset=server-(before+after)/2
        return {'server_minus_pc_seconds':round(offset,3),
                'roundtrip_seconds':round(after-before,3),
                'uncertainty_seconds':round((after-before)/2,3),
                'note':'estimate only; no timestamps are rewritten'}

    def send(self, body):
        return self.request('/api/edge/pose',body)
