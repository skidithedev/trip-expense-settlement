# test_loaders.py
"""
Quick test to verify CSV loading and schema validation.
Run this file in VSCode or terminal: python test_loaders.py
"""

from trip_splitter.logic import load_all_data
from trip_splitter.logic import convert_expenses_to_base, compute_allocations
from trip_splitter.logic import compute_balances
from trip_splitter.logic import compute_settlement

def main():
    # Load data from sample_data/
    data = load_all_data("sample_data")

    print("\n=== Participants ===")
    print(data["participants"])

    print("\n=== Rates ===")
    print(data["rates"])

    print("\n=== Expenses ===")
    print(data["expenses"])

    print("\n=== Splits ===")
    print(data["splits"])
    
def test_pipeline():
    data = load_all_data("sample_data")

    # FX conversion
    expenses_vnd = convert_expenses_to_base(data["expenses"], data["rates"])
    print("\n=== Expenses with Amount_Base (VND) ===")
    print(expenses_vnd[["ExpID", "Amount", "Currency", "Amount_Base"]])

    # Allocations
    allocs = compute_allocations(expenses_vnd, data["splits"], data["participants"])
    print("\n=== Allocations (per participant per expense) ===")
    print(allocs)

    # Balances
    balances = compute_balances(expenses_vnd, allocs, data["participants"])
    print("\n=== Balances (per participant) ===")
    print(balances)

    # Settlement
    settlement = compute_settlement(balances)
    print("\n=== Settlement (who pays whom) ===")
    print(settlement)

if __name__ == "__main__":
    main()
    test_pipeline()