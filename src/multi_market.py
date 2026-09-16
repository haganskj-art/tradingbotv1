from __future__ import annotations
from src.multi_market_engine import GenericMarketEngine
from src.tradovate_demo import TradovateDemo

MARKETS={
 'BTCUSDT': {'label':'BTCUSDT Perpetual','venue':'BINANCE TESTNET','multiplier':1.0,'kind':'binance'},
 'NQ': {'label':'E-mini Nasdaq-100','venue':'TRADOVATE DEMO','multiplier':20.0,'kind':'tradovate'},
 'MNQ': {'label':'Micro E-mini Nasdaq-100','venue':'TRADOVATE DEMO','multiplier':2.0,'kind':'tradovate'},
}

def build_tradovate_engine(client, market, contract):
    feed=client.market_feed(contract)
    return GenericMarketEngine(market,contract,feed)
