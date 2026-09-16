from __future__ import annotations
import json, threading, time, requests, websocket

class TradovateDemo:
    """Tradovate Production-Demo (simulated) REST + market-data adapter."""
    BASE='https://demo.tradovateapi.com/v1'
    MD_WS='wss://md.tradovateapi.com/v1/websocket'
    TRADE_WS='wss://demo.tradovateapi.com/v1/websocket'
    def __init__(self, username, password, app_id, cid, secret, app_version='1.0.0'):
        if not all([username,password,app_id,secret]): raise ValueError('Tradovate demo credentials are required.')
        self.username=username.strip(); self.password=password; self.app_id=app_id.strip(); self.cid=int(cid); self.secret=secret.strip(); self.app_version=app_version
        self.s=requests.Session(); self.token=None; self.md_token=None; self.expiry=0
    def auth(self):
        if self.token and time.time()<self.expiry-300: return self.token
        r=self.s.post(self.BASE+'/auth/accesstokenrequest',json={'name':self.username,'password':self.password,'appId':self.app_id,'appVersion':self.app_version,'cid':self.cid,'sec':self.secret},timeout=10); data=r.json()
        if not r.ok or not data.get('accessToken'): raise RuntimeError(f'Tradovate auth failed: {data.get("errorText", data)}')
        self.token=data['accessToken']; self.md_token=data.get('mdAccessToken') or self.token; self.expiry=time.time()+4800; return self.token
    def _get(self,path,params=None):
        t=self.auth(); r=self.s.get(self.BASE+path,params=params,headers={'Authorization':f'Bearer {t}'},timeout=10); 
        try: data=r.json()
        except: data=r.text
        if not r.ok: raise RuntimeError(f'Tradovate API {r.status_code}: {data}')
        return data
    def accounts(self): return self._get('/account/list')
    def positions(self): return self._get('/position/list')
    def place_market(self,account_id,account_spec,symbol,action,qty):
        t=self.auth(); body={'accountSpec':account_spec,'accountId':int(account_id),'action':action.title(),'symbol':symbol,'orderQty':int(qty),'orderType':'Market','isAutomated':True}
        r=self.s.post(self.BASE+'/order/placeorder',json=body,headers={'Authorization':f'Bearer {t}'},timeout=10); data=r.json()
        if not r.ok: raise RuntimeError(f'Place order failed: {data}')
        return data
    def ws_url(self): return self.MD_WS
    def market_feed(self,symbol): return TradovateFeed(self,symbol)

class TradovateFeed:
    def __init__(self,client,symbol): self.client=client; self.symbol=symbol
    def ws_url(self): return self.client.MD_WS
    def on_open(self,ws):
        token=self.client.auth(); ws.send(f'authorize\n0\n\n{token}'); time.sleep(.3); ws.send(f'md/subscribeQuote\n1\n\n{json.dumps({"symbol":self.symbol})}')
    def parse_message(self,raw):
        try:
            x=json.loads(raw)
        except Exception: return []
        d=x.get('d',{}) if isinstance(x,dict) else {}
        out=[]
        for q in d.get('quotes',[]):
            e=q.get('entries',{}); b=e.get('Bid',{}); a=e.get('Offer',{}); t=e.get('Trade',{})
            out.append({'bid':float(b.get('price',0) or 0),'ask':float(a.get('price',0) or 0),'bid_qty':float(b.get('size',0) or 0),'ask_qty':float(a.get('size',0) or 0),'trade':float(t.get('price',0) or 0),'trade_qty':float(t.get('size',0) or 0)})
        return out
