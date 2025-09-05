"""
logic.py
--------
Functions for loading and validating trip expense data from CSVs.

- Loads participants, rates, expenses, and splits tables.
- Validates each DataFrame against schemas defined in schemas.py.
- Provides helper to load all data at once.
"""

import os
import pandas as pd

from trip_splitter.schemas import (
    PARTICIPANTS_SCHEMA,
    RATES_SCHEMA,
    EXPENSES_SCHEMA,
    SPLITS_SCHEMA,
    validate_columns,
    validate_category,
    validate_currency,
)


# -----------------------------
# Loader functions
# -----------------------------

def load_participants(path: str) -> pd.DataFrame:
    """Load participants.csv"""
    df = pd.read_csv(path)
    validate_columns(df, PARTICIPANTS_SCHEMA)
    return df


def load_rates(path: str) -> pd.DataFrame:
    """Load rates.csv (parse Date)"""
    df = pd.read_csv(path, parse_dates=["Date"])
    validate_columns(df, RATES_SCHEMA)
    # Ensure VND always = 1
    vnd_rows = df[df["Currency"] == "VND"]
    if not all(vnd_rows["Rate_to_Base"] == 1):
        raise ValueError("Base currency VND must have Rate_to_Base = 1")
    return df


def load_expenses(path: str) -> pd.DataFrame:
    """Load expenses.csv (parse Date, validate categories/currencies)"""
    df = pd.read_csv(path, parse_dates=["Date"])
    validate_columns(df, EXPENSES_SCHEMA)

    # Validate categories and currencies
    for cat in df["Category"]:
        validate_category(cat)
    for cur in df["Currency"]:
        validate_currency(cur)

    return df


def load_splits(path: str) -> pd.DataFrame:
    """Load splits.csv"""
    df = pd.read_csv(path)
    validate_columns(df, SPLITS_SCHEMA)

    # Normalize Included column to boolean
    df["Included"] = df["Included"].astype(str).str.upper().map({"TRUE": True, "FALSE": False})
    df["WeightOverride"] = df["WeightOverride"].fillna("")
    return df


# -----------------------------
# High-level loader
# -----------------------------

def load_all_data(data_dir: str = "sample_data"):
    """
    Load all CSVs into a dictionary of DataFrames.

    Parameters
    ----------
    data_dir : str
        Directory containing the CSV files.

    Returns
    -------
    dict
        {
            "participants": DataFrame,
            "rates": DataFrame,
            "expenses": DataFrame,
            "splits": DataFrame,
        }
    """
    participants = load_participants(os.path.join(data_dir, "participants.csv"))
    rates = load_rates(os.path.join(data_dir, "rates.csv"))
    expenses = load_expenses(os.path.join(data_dir, "expenses.csv"))
    splits = load_splits(os.path.join(data_dir, "splits.csv"))

    return {
        "participants": participants,
        "rates": rates,
        "expenses": expenses,
        "splits": splits,
    }
    
# -----------------------------
# FX Conversion
# -----------------------------

def get_rate_on_or_before(rates: pd.DataFrame, date, currency: str, base="VND") -> float:
    """
    Get the latest FX rate for a currency on or before the given date.
    """
    if currency == base:
        return 1.0
    subset = rates[(rates["Currency"] == currency) & (rates["Date"] <= date)]
    if subset.empty:
        raise ValueError(f"No FX rate found for {currency} on or before {date}")
    return float(subset.sort_values("Date").iloc[-1]["Rate_to_Base"])


def convert_expenses_to_base(expenses: pd.DataFrame, rates: pd.DataFrame, base="VND") -> pd.DataFrame:
    """
    Add Amount_Base (in VND) column to expenses DataFrame.
    """
    expenses = expenses.copy()
    expenses["Amount_Base"] = expenses.apply(
        lambda row: row["Amount"] * get_rate_on_or_before(rates, row["Date"], row["Currency"], base),
        axis=1,
    )
    # Round to whole VND
    expenses["Amount_Base"] = expenses["Amount_Base"].round(0).astype(int)
    return expenses


# -----------------------------
# Allocations
# -----------------------------

def compute_allocations(expenses: pd.DataFrame, splits: pd.DataFrame, participants: pd.DataFrame) -> pd.DataFrame:
    """
    Compute per-participant share of each expense in VND.
    """
    # Merge splits with participant default weights
    p_weights = participants.set_index("Name")["DefaultWeight"].to_dict()
    s = splits.copy()

    # Resolve UseWeight
    def resolve_weight(row):
        if not row["Included"]:
            return 0.0
        if row["WeightOverride"] and str(row["WeightOverride"]).strip() != "":
            return float(row["WeightOverride"])
        return float(p_weights.get(row["Participant"], 1.0))

    s["UseWeight"] = s.apply(resolve_weight, axis=1)

    # Merge in Amount_Base for each ExpID
    exp_base = expenses.set_index("ExpID")["Amount_Base"]
    s = s.join(exp_base, on="ExpID")

    # Compute weight sums per expense
    weight_sums = s.groupby("ExpID")["UseWeight"].transform("sum")
    s["Share_Base"] = (s["Amount_Base"] * s["UseWeight"] / weight_sums).round(0).astype(int)

    # Keep only participants who were included
    allocs = s[s["UseWeight"] > 0].copy()
    return allocs[["ExpID", "Participant", "Share_Base"]]

# -----------------------------
# Balances
# -----------------------------

def compute_balances(expenses: pd.DataFrame, allocations: pd.DataFrame, participants: pd.DataFrame) -> pd.DataFrame:
    """
    Compute balances per participant:
    - Paid_Base: total they paid (in VND)
    - Owed_Base: total they owe (share of expenses)
    - Net_Base: Paid - Owed
    """
    # Paid per payer
    paid = expenses.groupby("Payer")["Amount_Base"].sum().rename("Paid_Base")

    # Owed per participant
    owed = allocations.groupby("Participant")["Share_Base"].sum().rename("Owed_Base")

    # Build full balances table with all participants
    df = participants[["Name"]].copy()
    df = df.rename(columns={"Name": "Participant"})
    df = df.join(paid, on="Participant").join(owed, on="Participant")

    # Fill missing values with 0
    df = df.fillna(0)

    # Compute net
    df["Net_Base"] = df["Paid_Base"] - df["Owed_Base"]

    # Round to whole VND (already integers but for safety)
    df[["Paid_Base", "Owed_Base", "Net_Base"]] = df[["Paid_Base", "Owed_Base", "Net_Base"]].round(0).astype(int)

    return df

# -----------------------------
# Settlement
# -----------------------------

def compute_settlement(balances: pd.DataFrame, eps: int = 1) -> pd.DataFrame:
    """
    Compute settlement transactions (who pays whom) to balance debts.

    Parameters
    ----------
    balances : pd.DataFrame
        Must contain columns ["Participant", "Net_Base"]
    eps : int
        Rounding tolerance (default = 1 VND)

    Returns
    -------
    pd.DataFrame
        Columns: ["From (Payer)", "To (Receiver)", "Amount_VND"]
    """
    creditors = balances[balances["Net_Base"] > 0].copy()
    debtors = balances[balances["Net_Base"] < 0].copy()

    creditors = creditors.sort_values("Net_Base", ascending=False).reset_index(drop=True)
    debtors = debtors.sort_values("Net_Base", ascending=True).reset_index(drop=True)

    txns = []
    i, j = 0, 0

    while i < len(debtors) and j < len(creditors):
        debtor = debtors.loc[i]
        creditor = creditors.loc[j]

        pay_amount = min(-debtor["Net_Base"], creditor["Net_Base"])
        if pay_amount > eps:
            txns.append({
                "From (Payer)": debtor["Participant"],
                "To (Receiver)": creditor["Participant"],
                "Amount_VND": int(round(pay_amount, 0))
            })

            # Update balances
            debtors.at[i, "Net_Base"] += pay_amount
            creditors.at[j, "Net_Base"] -= pay_amount

        # Move pointers if someone is settled
        if abs(debtors.at[i, "Net_Base"]) <= eps:
            i += 1
        if abs(creditors.at[j, "Net_Base"]) <= eps:
            j += 1

    return pd.DataFrame(txns)