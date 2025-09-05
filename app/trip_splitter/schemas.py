"""
schemas.py
----------
Central definitions for trip expense settlement workbook.

- Stores constants: currencies, categories, trip name.
- Defines expected CSV/Excel table schemas.
- Provides simple validation helpers for pandas DataFrames.
"""

from dataclasses import dataclass
from typing import List
import pandas as pd


# -----------------------------
# Project Constants
# -----------------------------

TRIP_NAME: str = "China, Aug 2025"
BASE_CURRENCY: str = "VND"

SUPPORTED_CURRENCIES: List[str] = ["VND", "CNY", "USD", "EUR"]

# Modify this based on your personal preferences
EXPENSE_CATEGORIES: List[str] = [
    "Services",
    "Food&Drinks",
    "Tickets",
    "Travelling",
    "Gifts&Merch",
]

ROUNDING_RULE: str = "VND"  # options: "VND", "nearest100", "nearest1000"


# -----------------------------
# Table Schemas
# -----------------------------

@dataclass(frozen=True)
class TableSchema:
    name: str
    required_columns: List[str]


# Schema definitions
PARTICIPANTS_SCHEMA = TableSchema(
    name="participants",
    required_columns=["Name", "DefaultWeight", "Contact"],
)

RATES_SCHEMA = TableSchema(
    name="rates",
    required_columns=["Date", "Currency", "Rate_to_Base"],
)

EXPENSES_SCHEMA = TableSchema(
    name="expenses",
    required_columns=[
        "ExpID",
        "Date",
        "Description",
        "Category",
        "Amount",
        "Currency",
        "Payer",
        "DriveURL",
    ],
)

SPLITS_SCHEMA = TableSchema(
    name="splits",
    required_columns=["ExpID", "Participant", "Included", "WeightOverride"],
)


# -----------------------------
# Validation Helpers
# -----------------------------

def validate_columns(df: pd.DataFrame, schema: TableSchema) -> None:
    """
    Validate that a DataFrame contains all required columns.

    Parameters
    ----------
    df : pd.DataFrame
        The dataframe to validate.
    schema : TableSchema
        Schema with required columns.

    Raises
    ------
    ValueError
        If required columns are missing.
    """
    missing = set(schema.required_columns) - set(df.columns)
    if missing:
        raise ValueError(
            f"Table '{schema.name}' is missing required columns: {missing}"
        )


def validate_category(value: str) -> None:
    """
    Ensure category is in the allowed EXPENSE_CATEGORIES.
    """
    if value not in EXPENSE_CATEGORIES:
        raise ValueError(
            f"Invalid category '{value}'. Must be one of: {EXPENSE_CATEGORIES}"
        )


def validate_currency(value: str) -> None:
    """
    Ensure currency is supported.
    """
    if value not in SUPPORTED_CURRENCIES:
        raise ValueError(
            f"Invalid currency '{value}'. Must be one of: {SUPPORTED_CURRENCIES}"
        )
