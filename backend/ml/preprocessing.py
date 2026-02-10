"""
MetricsPreprocessor: Feature engineering and normalisation for Prometheus-style metrics.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler


class MetricsPreprocessor:
    """
    Prepares raw metric DataFrames for consumption by AnomalyDetector.

    Typical pipeline::

        preprocessor = MetricsPreprocessor()
        clean        = preprocessor.handle_missing(raw_df)
        features     = preprocessor.extract_features(clean)
        normalised   = preprocessor.normalize(features)
    """

    def __init__(
        self,
        rolling_window: int = 5,
        ewm_span: int = 10,
    ) -> None:
        self.rolling_window = rolling_window
        self.ewm_span = ewm_span
        self._scaler: StandardScaler | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def handle_missing(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Handle missing values using forward-fill followed by linear interpolation.

        Strategy:
          1. Forward-fill propagates the last known value (good for sudden gaps).
          2. Linear interpolation fills remaining NaNs using neighbouring values.
          3. Any residual NaNs (e.g. leading) are filled with 0.

        Parameters
        ----------
        df : pd.DataFrame
            Raw metrics DataFrame with possible NaN values.

        Returns
        -------
        pd.DataFrame — cleaned copy with no NaNs
        """
        result = df.copy()

        # Forward fill — handles gaps caused by scrape failures
        result = result.ffill()

        # Backward fill for leading NaNs that forward-fill cannot address
        result = result.bfill()

        # Linear interpolation for interior gaps still remaining
        numeric_cols = result.select_dtypes(include=[np.number]).columns
        result[numeric_cols] = result[numeric_cols].interpolate(method="linear", limit_direction="both")

        # Final safety net
        result = result.fillna(0)

        return result

    def extract_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Derive additional statistical features from raw metric columns.

        Added features (per numeric column ``col``):
          - ``{col}_rolling_mean``  — rolling mean over ``rolling_window`` steps
          - ``{col}_rolling_std``   — rolling std  over ``rolling_window`` steps
          - ``{col}_rate_of_change``— first-order finite difference (delta per step)
          - ``{col}_ewm``          — exponentially weighted mean (span=ewm_span)
          - ``{col}_z_score``      — per-point z-score relative to rolling window

        Parameters
        ----------
        df : pd.DataFrame

        Returns
        -------
        pd.DataFrame — original columns + engineered feature columns
        """
        result = df.copy()
        numeric_cols = df.select_dtypes(include=[np.number]).columns

        for col in numeric_cols:
            s = df[col]
            w = self.rolling_window

            rolling_obj = s.rolling(window=w, min_periods=1)
            rolling_mean = rolling_obj.mean()
            rolling_std = rolling_obj.std().fillna(0)

            result[f"{col}_rolling_mean"] = rolling_mean
            result[f"{col}_rolling_std"] = rolling_std
            result[f"{col}_rate_of_change"] = s.diff().fillna(0)
            result[f"{col}_ewm"] = s.ewm(span=self.ewm_span, adjust=False).mean()

            # z-score relative to rolling window (avoids divide-by-zero)
            denom = rolling_std.replace(0, np.nan)
            z_score = (s - rolling_mean) / denom
            result[f"{col}_z_score"] = z_score.fillna(0)

        return result

    def normalize(self, df: pd.DataFrame, fit: bool = True) -> pd.DataFrame:
        """
        Apply StandardScaler normalisation to all numeric columns.

        Parameters
        ----------
        df  : pd.DataFrame
        fit : bool
            If True, fit the scaler on this data (training mode).
            If False, use the previously fitted scaler (inference mode).

        Returns
        -------
        pd.DataFrame — same shape with normalised numeric columns
        """
        result = df.copy()
        numeric_cols = result.select_dtypes(include=[np.number]).columns

        if not len(numeric_cols):
            return result

        if fit or self._scaler is None:
            self._scaler = StandardScaler()
            result[numeric_cols] = self._scaler.fit_transform(result[numeric_cols].values)
        else:
            result[numeric_cols] = self._scaler.transform(result[numeric_cols].values)

        return result

    def inverse_normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Reverse StandardScaler transformation (useful for converting forecasts back to raw units)."""
        if self._scaler is None:
            raise RuntimeError("Scaler has not been fitted yet. Call normalize(fit=True) first.")

        result = df.copy()
        numeric_cols = result.select_dtypes(include=[np.number]).columns

        if len(numeric_cols):
            result[numeric_cols] = self._scaler.inverse_transform(result[numeric_cols].values)

        return result

    def get_feature_names(self, base_columns: list[str]) -> list[str]:
        """Return the full list of feature column names for a given set of base metric columns."""
        names = list(base_columns)
        for col in base_columns:
            names += [
                f"{col}_rolling_mean",
                f"{col}_rolling_std",
                f"{col}_rate_of_change",
                f"{col}_ewm",
                f"{col}_z_score",
            ]
        return names
