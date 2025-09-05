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
    # Drop any temporary helper columns (e.g., delete markers)
    df = df[[c for c in df.columns if not str(c).startswith("__")]]
    # Replace NaN with empty string for CSV friendliness
    df = df.fillna("")
    df.to_csv(path, index=False)

def editable_table(label: str, df: pd.DataFrame, key: str):
    st.caption(label)
    st.caption("Tip: Click 'Add row' to add; use the row menu to delete.")
    edited = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        key=key,
        num_rows="dynamic",
    )
    return edited

def apply_sort_controls(df: pd.DataFrame, key_prefix: str, default_col: str | None = None, exclude_prefix: str = "__") -> pd.DataFrame:
    # Exclude helper columns (like __delete__)
    sort_columns = [c for c in df.columns if not str(c).startswith(exclude_prefix)]
    if not sort_columns:
        return df
    # Persisted prefs container
    if "sort_prefs" not in st.session_state:
        st.session_state.sort_prefs = {}
    prefs = st.session_state.sort_prefs.get(key_prefix, {})

    with st.expander("Sorting", expanded=False):
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            try:
                default_idx = sort_columns.index(default_col) if default_col in sort_columns else 0
            except ValueError:
                default_idx = 0
            selected_col = st.selectbox(
                "Sort by",
                sort_columns,
                index=sort_columns.index(prefs.get("col", sort_columns[default_idx])) if prefs.get("col") in sort_columns else default_idx,
                key=f"{key_prefix}_sort_col_tmp",
            )
        with c2:
            selected_asc = st.toggle(
                "Ascending",
                value=prefs.get("asc", True),
                key=f"{key_prefix}_sort_asc_tmp",
            )
        with c3:
            apply_clicked = st.button("Apply sort", key=f"{key_prefix}_apply_sort")
            clear_clicked = st.button("Clear sort", key=f"{key_prefix}_clear_sort")

    # Update persisted sort preferences only when buttons clicked
    if clear_clicked:
        st.session_state.sort_prefs[key_prefix] = {}
        return df
    if apply_clicked:
        st.session_state.sort_prefs[key_prefix] = {"col": selected_col, "asc": selected_asc}

    # Apply persisted sort if present
    prefs = st.session_state.sort_prefs.get(key_prefix, {})
    if "col" in prefs:
        try:
            return df.sort_values(by=prefs["col"], ascending=prefs.get("asc", True), kind="mergesort", ignore_index=True)
        except Exception:
            return df
    return df


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
auto_preview = st.sidebar.toggle("Auto-preview", value=True, help="If off, preview updates only when you click 'Run preview'.")
run_preview_clicked = st.sidebar.button("Run preview")


# -----------------------------
# Load or reload data into session_state
# -----------------------------
if reload_clicked and not os.path.isdir(data_dir):
    st.sidebar.error(f"Folder not found: {data_dir}")

if "dfs" not in st.session_state or reload_clicked:
    load_dir = data_dir if os.path.isdir(data_dir) else "sample_data"
    data = load_all_data(load_dir)
    st.session_state.dfs = {
        "participants": data["participants"].copy(),
        "rates": data["rates"].copy(),
        "expenses": data["expenses"].copy(),
        "splits": data["splits"].copy(),
    }
    st.session_state.loaded_data_dir = load_dir

# Bind locals to current state for easier use below
participants = st.session_state.dfs["participants"]
rates        = st.session_state.dfs["rates"]
expenses     = st.session_state.dfs["expenses"]
splits       = st.session_state.dfs["splits"]

# -----------------------------
# Tabs
# -----------------------------
tab_p, tab_r, tab_e, tab_s, tab_prev, tab_sum = st.tabs(
    ["Participants", "Rates", "Expenses", "Splits", "Preview", "Summary"]
)

with tab_p:
    st.subheader("Participants")
    participants = apply_sort_controls(participants, key_prefix="participants", default_col=participants.columns[0] if not participants.empty else None)
    participants = editable_table("participants.csv", participants, key="participants")
    st.session_state.dfs["participants"] = participants
    st.info("Weights default to 1.0; you can adjust here or per-expense via WeightOverride in Splits.")

with tab_r:
    st.subheader("Rates (to VND)")
    st.caption("Enter manual daily FX rates. VND must be 1.")
    rates = apply_sort_controls(rates, key_prefix="rates", default_col=rates.columns[0] if not rates.empty else None)
    rates = editable_table("rates.csv", rates, key="rates")
    st.session_state.dfs["rates"] = rates

with tab_e:
    st.subheader("Expenses")
    st.caption("DriveURL becomes a 🧾 hyperlink in Excel. Categories and currency must be valid.")
    st.caption("Tip: Click 'Add row' to add; use the row menu to delete.")
    # Show some guidance
    st.markdown(
        f"- Allowed categories: `{', '.join(EXPENSE_CATEGORIES)}`  \n"
        f"- Supported currencies: `{', '.join(SUPPORTED_CURRENCIES)}`"
    )
    # Add a helper checkbox column for deletions (not saved to CSV)
    if "__delete__" not in expenses.columns:
        expenses["__delete__"] = False
    expenses = apply_sort_controls(expenses, key_prefix="expenses", default_col="Date" if "Date" in expenses.columns else None)
    col_del_e1, col_del_e2 = st.columns([1, 3])
    with col_del_e1:
        del_expenses_clicked = st.button("Delete selected rows", key="del_expenses")
    expenses = st.data_editor(
        expenses,
        use_container_width=True,
        hide_index=True,
        key="expenses",
        num_rows="dynamic",
        column_config={
            "__delete__": st.column_config.CheckboxColumn(label="Delete?", default=False),
            "Category": st.column_config.SelectboxColumn(
                "Category", options=EXPENSE_CATEGORIES
            ),
            "Currency": st.column_config.SelectboxColumn(
                "Currency", options=SUPPORTED_CURRENCIES
            ),
            "Date": st.column_config.DateColumn("Date"),
        },
    )
    if del_expenses_clicked and "__delete__" in expenses.columns:
        expenses = expenses[~expenses["__delete__"].fillna(False)].drop(columns=["__delete__"], errors="ignore").reset_index(drop=True)
    else:
        # Keep helper column for further edits until save
        pass
    st.session_state.dfs["expenses"] = expenses

with tab_s:
    st.subheader("Splits (long format)")
    st.caption("Included = TRUE/FALSE. WeightOverride blank → use DefaultWeight from Participants.")
    st.caption("Tip: Click 'Add row' to add; use the row menu to delete.")
    # Add a helper checkbox column for deletions (not saved to CSV)
    if "__delete__" not in splits.columns:
        splits["__delete__"] = False
    splits = apply_sort_controls(splits, key_prefix="splits", default_col="ExpenseID" if "ExpenseID" in splits.columns else None)
    col_del_s1, col_del_s2 = st.columns([1, 3])
    with col_del_s1:
        del_splits_clicked = st.button("Delete selected rows", key="del_splits")
    splits = st.data_editor(
        splits,
        use_container_width=True,
        hide_index=True,
        key="splits",
        num_rows="dynamic",
        column_config={
            "__delete__": st.column_config.CheckboxColumn(label="Delete?", default=False),
            "Included": st.column_config.CheckboxColumn(default=False),
            "WeightOverride": st.column_config.NumberColumn(required=False),
        },
    )
    if del_splits_clicked and "__delete__" in splits.columns:
        splits = splits[~splits["__delete__"].fillna(False)].drop(columns=["__delete__"], errors="ignore").reset_index(drop=True)
    else:
        # Keep helper column for further edits until save
        pass
    st.session_state.dfs["splits"] = splits

# -----------------------------
# Pipeline (Preview)
# -----------------------------
should_run_preview = auto_preview or run_preview_clicked
try:
    if should_run_preview:
        expenses_vnd = convert_expenses_to_base(st.session_state.dfs["expenses"], st.session_state.dfs["rates"])
        allocations  = compute_allocations(expenses_vnd, st.session_state.dfs["splits"], st.session_state.dfs["participants"])
        balances     = compute_balances(expenses_vnd, allocations, st.session_state.dfs["participants"])
        settlement   = compute_settlement(balances)
    else:
        expenses_vnd = allocations = balances = settlement = None
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
        if auto_preview:
            st.info("Fix the error above to see previews.")
        else:
            st.info("Auto-preview is off. Click 'Run preview' in the sidebar to update.")

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
        save_df_csv(st.session_state.dfs["participants"], os.path.join(data_dir, "participants.csv"))
        save_df_csv(st.session_state.dfs["rates"],        os.path.join(data_dir, "rates.csv"))
        save_df_csv(st.session_state.dfs["expenses"],     os.path.join(data_dir, "expenses.csv"))
        save_df_csv(st.session_state.dfs["splits"],       os.path.join(data_dir, "splits.csv"))
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
