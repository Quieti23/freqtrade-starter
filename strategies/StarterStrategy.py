"""Original demonstration strategy; not a profitability claim."""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy


class StarterStrategy(IStrategy):
    INTERFACE_VERSION = 3
    can_short = False
    timeframe = "5m"
    startup_candle_count = 60
    minimal_roi = {"0": 0.03, "60": 0.01, "180": 0}
    stoploss = -0.03
    process_only_new_candles = True

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=12)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=26)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["ema_fast"] > dataframe["ema_slow"])
            & (dataframe["ema_fast"].shift(1) <= dataframe["ema_slow"].shift(1))
            & (dataframe["rsi"] < 70)
            & (dataframe["volume"] > 0),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["ema_fast"] < dataframe["ema_slow"])
            & (dataframe["ema_fast"].shift(1) >= dataframe["ema_slow"].shift(1))
            & (dataframe["volume"] > 0),
            "exit_long",
        ] = 1
        return dataframe
