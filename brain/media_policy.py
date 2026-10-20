"""No automatic paid-media retries. Bounded, complexity-aware response budgets."""
import math
import re

MINIMUM_SECONDS = {'image':150,'speech':200,'audio':200,'video':300}


def response_timeout(kind, configured=0, payload=None):
    payload=payload or {}
    minimum=MINIMUM_SECONDS[kind]
    budget=float(minimum)
    if kind=='image':
        match=re.fullmatch(r'(\d+)x(\d+)',str(payload.get('size','1024x1024')))
        pixels=int(match[1])*int(match[2]) if match else 1024*1024
        budget*=max(1,pixels/(1024*1024))*max(1,int(payload.get('n',1)))
        budget+=max(0,len(str(payload.get('prompt','')))-2000)/100
    elif kind in {'speech','audio'}:
        budget=max(budget,60+len(str(payload.get('input','')))/6)
    else:
        budget=max(budget,120+float(payload.get('duration',0))*10)
    return min(3600,math.ceil(max(budget,float(configured or 0),minimum)))


def request_headers(kind, timeout):
    return {'X-EditorGPT-Media-Single-Attempt':'1',
            'X-EditorGPT-Media-Timeout-Ms':str(int(timeout*1000))}


def require_gateway_safety(client,url,headers):
    """Read-only handshake. Never submit paid media to a gateway lacking the guard."""
    try:
        response=client.get(url,headers=headers)
        response.raise_for_status()
        policy=response.json()
        if policy.get('version')!=1 or policy.get('single_attempt') is not True:
            raise ValueError('unsupported policy')
    except Exception as exc:
        raise RuntimeError('Gateway media safety policy is unavailable; no media request was submitted') from exc
