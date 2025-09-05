# app/app_streamlit.py
import os
from io import BytesIO
import streamlit as st
import pandas as pd

from trip_splitter.schemas import TRIP_NAME, EXPENSE_CATEGORIES, SUPPORTED_CURRENCIES
from trip_splitter.logic import (
    load_all_data,
    convert_expenses_to_base,
    compute_allocations,
    compute_balances,
    compute_settlement,
)
from trip_splitter.build_or_update import build_workbook_bytes

st.set_page_config(page_title="Trip Expense Settlement", layout="wide")


# -----------------------------
# Helpers
# -----------------------------
def save_df_csv(df: pd.DataFrame, path: str):
    # Drop completely empty rows (all NaN)
    df = df.dropna(how="all")
    # Replace NaN with empty string for CSV friendliness
    df = df.fillna("")
    df.to_csv(path, index=False)

def editable_table(label: str, df: pd.DataFrame, key: str):
    st.caption(label)
    edited = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        key=key,
        num_rows="dynamic",
    )
    return edited


# -----------------------------
# Sidebar controls
# -----------------------------
st.sidebar.title("Trip Expense GUI")
st.sidebar.write(f"**Trip:** {TRIP_NAME}")

data_dir = st.sidebar.text_input("Data folder", value="sample_data")
col1, col2 = st.sidebar.columns(2)
reload_clicked = col1.button("Reload")
save_clicked = col2.button("Save CSVs")

gen_excel = st.sidebar.button("Generate Excel")
st.sidebar.caption("Excel includes: Settlement, Balances, Allocations, Expenses, Summary.")


# -----------------------------
# Load or reload data
# -----------------------------
if reload_clicked and not os.path.isdir(data_dir):
    st.sidebar.error(f"Folder not found: {data_dir}")

data = load_all_data(data_dir if os.path.isdir(data_dir) else "sample_data")
participants = data["participants"].copy()
rates        = data["rates"].copy()
expenses     = data["expenses"].copy()
splits       = data["splits"].copy()

# -----------------------------
# Tabs
# -----------------------------
tab_p, tab_r, tab_e, tab_s, tab_prev, tab_sum = st.tabs(
    ["Participants", "Rates", "Expenses", "Splits", "Preview", "Summary"]
)

with tab_p:
    st.subheader("Participants")
    participants = editable_table("participants.csv", participants, key="participants")
    st.info("Weights default to 1.0; you can adjust here or per-expense via WeightOverride in Splits.")

with tab_r:
    st.subheader("Rates (to VND)")
    st.caption("Enter manual daily FX rates. VND must be 1.")
    rates = editable_table("rates.csv", rates, key="rates")

with tab_e:
    st.subheader("Expenses")
    st.caption("DriveURL becomes a 🧾 hyperlink in Excel. Categories and currency must be valid.")
    # Show some guidance
    st.markdown(
        f"- Allowed categories: `{', '.join(EXPENSE_CATEGORIES)}`  \n"
        f"- Supported currencies: `{', '.join(SUPPORTED_CURRENCIES)}`"
    )
    expenses = st.data_editor(
        expenses,
        use_container_width=True,
        hide_index=True,
        key="expenses",
        num_rows="dynamic",
        column_config={
            "Category": st.column_config.SelectboxColumn("Category", options=EXPENSE_CATEGORIES),
            "Currency": st.column_config.SelectboxColumn("Currency", options=SUPPORTED_CURRENCIES),
            "Date": st.column_config.DateColumn("Date"),
        },
    )

with tab_s:
    st.subheader("Splits (long format)")
    st.caption("Included = TRUE/FALSE. WeightOverride blank → use DefaultWeight from Participants.")
    splits = st.data_editor(
        splits,
        use_container_width=True,
        hide_index=True,
        key="splits",
        num_rows="dynamic",
        column_config={
            "Included": st.column_config.CheckboxColumn(default=False),
            "WeightOverride": st.column_config.NumberColumn(required=False),
        },
    )

# -----------------------------
# Pipeline (Preview)
# -----------------------------
try:
    expenses_vnd = convert_expenses_to_base(expenses, rates)
    allocations  = compute_allocations(expenses_vnd, splits, participants)
    balances     = compute_balances(expenses_vnd, allocations, participants)
    settlement   = compute_settlement(balances)
except Exception as e:
    with tab_prev:
        st.error(f"Pipeline error: {e}")
    settlement = balances = allocations = expenses_vnd = None

with tab_prev:
    st.subheader("Preview Results")
    if expenses_vnd is not None:
        st.markdown("**Expenses (with Amount_Base in VND)**")
        st.dataframe(expenses_vnd, use_container_width=True)
        st.markdown("**Allocations** (per expense & participant)")
        st.dataframe(allocations, use_container_width=True)
        st.markdown("**Balances** (per participant)")
        st.dataframe(balances, use_container_width=True)
        st.markdown("**Settlement** (fewest transactions)")
        st.dataframe(settlement, use_container_width=True)
    else:
        st.info("Fix the error above to see previews.")

# -----------------------------
# Summary tab (lightweight)
# -----------------------------
with tab_sum:
    st.subheader("Summary")
    if expenses_vnd is not None:
        totals_by_cat = expenses_vnd.groupby("Category")["Amount_Base"].sum().reset_index()
        st.markdown("**Totals by Category (VND)**")
        st.dataframe(totals_by_cat, use_container_width=True)

        totals_by_person = balances[["Participant", "Paid_Base", "Owed_Base", "Net_Base"]]
        st.markdown("**Per Participant (VND)**")
        st.dataframe(totals_by_person, use_container_width=True)

        st.markdown("**Charts**")
        st.bar_chart(totals_by_person.set_index("Participant")[["Paid_Base", "Owed_Base", "Net_Base"]])
    else:
        st.info("Run pipeline successfully to see summaries.")

# -----------------------------
# Save CSVs (optional)
# -----------------------------
if save_clicked:
    try:
        save_df_csv(participants, os.path.join(data_dir, "participants.csv"))
        save_df_csv(rates,        os.path.join(data_dir, "rates.csv"))
        save_df_csv(expenses,     os.path.join(data_dir, "expenses.csv"))
        save_df_csv(splits,       os.path.join(data_dir, "splits.csv"))
        st.sidebar.success("CSV files saved.")
    except Exception as e:
        st.sidebar.error(f"Failed to save CSVs: {e}")

# -----------------------------
# Generate Excel for download
# -----------------------------
if gen_excel:
    try:
        xlsx_bytes = build_workbook_bytes(data_dir=data_dir)
        st.sidebar.download_button(
            "Download Trip_Splitter.xlsx",
            data=xlsx_bytes,
            file_name="Trip_Splitter.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        st.sidebar.success("Excel ready.")
    except Exception as e:
        st.sidebar.error(f"Build failed: {e}")
