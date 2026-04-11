import numpy as np
import pandas as pd
import pandas_ta as ta
import py_vollib_vectorized

from config import settings

class Indicators:
    @staticmethod
    def calculate_greeks_and_iv(spot: float, strike_array: np.ndarray, premium_array: np.ndarray, time_to_expiry_years: float, flag_array: np.ndarray):
        """
        Calculates IIV and Greeks using py_vollib_vectorized.
        :param spot: Current price of the underlying
        :param strike_array: np.array of strike prices
        :param premium_array: np.array of option prices (LTP)
        :param time_to_expiry_years: Time to expiry in years
        :param flag_array: np.array of 'c' (call) or 'p' (put)
        """
        r = settings.RISK_FREE_RATE
        # Determine implied volatility based on premium
        iv = py_vollib_vectorized.implied_volatility_vectorized(
            premium_array, spot, strike_array, time_to_expiry_years, r, flag_array, return_as='numpy'
        )
        
        # Determine greeks
        delta = py_vollib_vectorized.delta_vectorized(
            flag_array, spot, strike_array, time_to_expiry_years, r, iv, return_as='numpy'
        )
        gamma = py_vollib_vectorized.gamma_vectorized(
            flag_array, spot, strike_array, time_to_expiry_years, r, iv, return_as='numpy'
        )
        theta = py_vollib_vectorized.theta_vectorized(
            flag_array, spot, strike_array, time_to_expiry_years, r, iv, return_as='numpy'
        )

        return {
            'IV': iv,
            'Delta': delta,
            'Gamma': gamma,
            'Theta': theta
        }

    @staticmethod
    def calculate_adx(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
        """Calculates Average Directional Index using pandas-ta."""
        # df must have high, low, close columns
        adx = ta.adx(df['high'], df['low'], df['close'], length=window)
        if adx is not None:
            # pandas-ta returns a df with ADX_14, DMP_14, DMN_14
            df['ADX'] = adx[f'ADX_{window}']
            df['DMP'] = adx[f'DMP_{window}']
            df['DMN'] = adx[f'DMN_{window}']
        return df

    @staticmethod
    def calculate_atr(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
        """Calculates Average True Range."""
        atr = ta.atr(df['high'], df['low'], df['close'], length=window)
        if atr is not None:
            df['ATR'] = atr
        return df

    @staticmethod
    def calculate_pcr(chain_df: pd.DataFrame) -> float:
        """Calculate Put-Call Ratio based on Open Interest."""
        total_ce_oi = chain_df[chain_df['type'] == 'c']['oi'].sum()
        total_pe_oi = chain_df[chain_df['type'] == 'p']['oi'].sum()
        
        if total_ce_oi == 0:
            return 1.0 # fallback
            
        return float(total_pe_oi / total_ce_oi)

    @staticmethod
    def calculate_pcr_zscore(pcr_history: pd.Series) -> float:
        """Calculates Z-score of PCR given a historical series."""
        if len(pcr_history) < 2:
            return 0.0
        mean = pcr_history.mean()
        std = pcr_history.std()
        if std == 0:
            return 0.0
        current_pcr = pcr_history.iloc[-1]
        return float((current_pcr - mean) / std)

    @staticmethod
    def iv_percentile(iv_history: pd.Series) -> float:
        """Calculate IV percentile rank."""
        if len(iv_history) < 2:
            return 50.0  # default middle
        current_iv = iv_history.iloc[-1]
        rank = (iv_history < current_iv).mean()
        return float(rank * 100)
