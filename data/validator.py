import numpy as np
import pandas as pd

def validate_dataframe(df: pd.DataFrame, required_columns: list[str]) -> bool:
    """Validates that a dataframe has needed columns and is not empty."""
    if df is None or df.empty:
        return False
    if not all(col in df.columns for col in required_columns):
        return False
    return True

def validate_quote(quote_data: dict, instruments: list[str]) -> bool:
    """Validates that quote data contains data for requested instruments."""
    if not quote_data:
        return False
    return all(inst in quote_data for inst in instruments)

def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Remove any infinite or NaN values from critical columns before processing."""
    # Replace inf with nan
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    # Forward fill nan values
    df.ffill(inplace=True)
    return df
