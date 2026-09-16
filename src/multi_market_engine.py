from __future__ import annotations

import json, math, threading, time
from collections import deque
from datetime import datetime
import numpy as np
import websocket


class GenericMarketEngine:
    """Generic quote/trade anomaly detector used by BTC, NQ and MNQ feeds."""
    def __init__(self, name: str, symbol: str, feed):
        self.name, self.symbol, self.feed = name, symbol.upper(), feed
        self._lock = threading.RLock(); self._started=False; self._thread=None; self._ws=None
        self.price=0.0; self.fair_value=0.0; self.best_bid=0.0; self.best_ask=0.0; self.bid_qty=0.0; self.ask_qty=0.0
        self.deviations=deque(maxlen=1200); self.history=deque(maxlen=600); self.volume_series=deque(maxlen=90)
        self.buy_window=deque(maxlen=5000); self.sell_window=deque(maxlen=5000); self.volume_window=deque(maxlen=120)
        self.logs=deque(maxlen=30); self.trade_count=0; self.status='CONNECTING'; self.reconnects=0
        self.last_event_ns=time.perf_counter_ns(); self.last_book_update=0; self.signal='WAITING'; self.anomaly_score=0.0; self.zscore=0.0; self.imbalance=0.0
        self._last_log_second=0

    def start(self):
        with self._lock:
            if self._started: return
            self._started=True
            self._thread=threading.Thread(target=self._run_forever,daemon=True,name=f'{self.name}-feed'); self._thread.start()

    def _run_forever(self):
        while self._started:
            try:
                self.status='CONNECTING'
                self._ws=websocket.WebSocketApp(self.feed.ws_url(), on_open=self._on_open, on_message=self._on_message, on_error=self._on_error, on_close=self._on_close)
                self._ws.run_forever(ping_interval=30,ping_timeout=15)
            except Exception as e: self._log('SYSTEM',f'feed exception: {e}')
            self.reconnects += 1; self.status='RECONNECTING'; time.sleep(min(10,1+self.reconnects*.5))

    def _on_open(self, ws):
        self.feed.on_open(ws); self.status='LIVE'; self.reconnects=0; self._log('SYSTEM',f'{self.name} market stream connected')

    def _on_close(self, ws, code, msg): self.status='DISCONNECTED'; self._log('SYSTEM',f'WebSocket closed: {code or "-"}')
    def _on_error(self, ws, error): self.status='ERROR'; self._log('SYSTEM',f'WebSocket error: {error}')

    def _on_message(self, ws, raw):
        try:
            events=self.feed.parse_message(raw)
            for event in events: self._apply_event(event)
        except Exception as e: self._log('SYSTEM',f'message parse error: {e}')

    def _apply_event(self,e):
        now=time.time(); received=time.perf_counter_ns(); self.last_event_ns=received
        with self._lock:
            bid,ask,bq,aq=e.get('bid',0),e.get('ask',0),e.get('bid_qty',0),e.get('ask_qty',0)
            trade=e.get('trade',0); tq=e.get('trade_qty',0)
            if bid>0: self.best_bid=bid; self.bid_qty=bq
            if ask>0: self.best_ask=ask; self.ask_qty=aq
            if trade>0: self.price=trade
            elif self.best_bid and self.best_ask: self.price=(self.best_bid+self.best_ask)/2
            if tq>0:
                # If trade is at/near offer, classify as aggressive buy; near bid as sell.
                if self.best_ask and trade >= self.best_ask - 1e-9: self.buy_window.append((now,tq))
                elif self.best_bid and trade <= self.best_bid + 1e-9: self.sell_window.append((now,tq))
            self.trade_count += 1 if tq>0 else 0
            self._trim(now); self._fair(); self._detect(now)

    def _trim(self,now):
        for q in (self.buy_window,self.sell_window):
            while q and now-q[0][0]>10: q.popleft()

    def _fair(self):
        if self.best_bid>0 and self.best_ask>self.best_bid:
            den=self.bid_qty+self.ask_qty
            micro=(self.best_ask*self.bid_qty+self.best_bid*self.ask_qty)/den if den>0 else (self.best_bid+self.best_ask)/2
        elif self.price>0: micro=self.price
        else: return
        self.fair_value=micro if self.fair_value<=0 else .12*micro+.88*self.fair_value

    def _detect(self,now):
        if self.price<=0 or self.fair_value<=0: return
        dev=self.price-self.fair_value; self.deviations.append(dev)
        z=0.0
        if len(self.deviations)>=50:
            a=np.asarray(self.deviations,dtype=float); std=float(np.std(a)); z=(dev-float(np.mean(a)))/std if std>1e-9 else 0.0
        self.zscore=z
        buy=sum(q for t,q in self.buy_window if now-t<=10); sell=sum(q for t,q in self.sell_window if now-t<=10); total=buy+sell
        self.imbalance=(buy-sell)/total*100 if total else 0.0
        recent=sum(q for t,q in self.buy_window if now-t<=2)+sum(q for t,q in self.sell_window if now-t<=2)
        self.volume_window.append(recent)
        baseline=float(np.mean(list(self.volume_window)[-30:])) if self.volume_window else recent
        burst=recent/baseline if baseline>0 else 1
        score=min(abs(z)/4,1)*55+min(abs(self.imbalance)/60,1)*25+min(max(burst-1,0)/3,1)*20
        self.anomaly_score=max(0,min(100,score))
        if z<=-1.5 and self.imbalance>0: sig='BUY DISLOCATION'
        elif z>=1.5 and self.imbalance<0: sig='SELL DISLOCATION'
        else: sig='NO ANOMALY'
        self.signal=sig
        self.history.append({'time':datetime.now().strftime('%H:%M:%S'),'price':self.price,'fair':self.fair_value})
        self.volume_series.append({'time':datetime.now().strftime('%H:%M:%S'),'buy':buy,'sell':sell})
        sec=int(now)
        if sec!=self._last_log_second and score>=70:
            self._last_log_second=sec; self._log('ANOMALY',f'{sig} | score {score:.0f} | z {z:+.2f} | flow {self.imbalance:+.1f}%')

    def _log(self,level,msg): self.logs.appendleft({'time':datetime.now().strftime('%H:%M:%S'),'level':level,'message':msg})

    def snapshot(self):
        with self._lock:
            return {'name':self.name,'symbol':self.symbol,'price':self.price,'fair_value':self.fair_value,'best_bid':self.best_bid,'best_ask':self.best_ask,'bid_qty':self.bid_qty,'ask_qty':self.ask_qty,'zscore':self.zscore,'imbalance':self.imbalance,'anomaly_score':self.anomaly_score,'signal':self.signal,'status':self.status,'trade_count':self.trade_count,'history':list(self.history),'volume_series':list(self.volume_series),'logs':list(self.logs),'last_event_ms':(time.perf_counter_ns()-self.last_event_ns)/1e6}
