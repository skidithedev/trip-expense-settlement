# Trip Expense Settlement System

A simple Python-powered tool to manage **shared travel expenses** and generate a clean, professional **Excel workbook** for settlement.

## ✨ Features

* **Settlement sheet** → optimized *who pays whom* with fewest transactions.
* **Balances sheet** → what each participant paid, owes, and net balance.
* **Allocations sheet** → detailed per-expense shares.
* **Expenses sheet** → original amounts (multi-currency), converted to VND, with **receipt links** (🧾).
* **Summary sheet** → totals by category, per person, with charts.

## ⚙️ Setup

### Prerequisites

* macOS/Linux
* Python 3.10+
* Excel (or LibreOffice)

### Installation

```bash
# Clone repo
git clone https://github.com/skidithedev/trip-expense-settlement
cd trip-expense-settlement

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install pandas openpyxl
```

## 📝 Input Data

CSV files are stored in `sample_data/`.

* **participants.csv**

```csv
Name,DefaultWeight,Contact
Alice,1.0,
Bob,1.0,
Carol,1.0,
```

* **rates.csv** (manual exchange rates to VND)

```csv
Date,Currency,Rate_to_Base
2025-08-10,VND,1
2025-08-10,CNY,3600
2025-08-11,CNY,3610
```

* **expenses.csv**

```csv
ExpID,Date,Description,Category,Amount,Currency,Payer,DriveURL
E0001,2025-08-10,SIM cards,SIM cards,150,CNY,Alice,https://drive.google.com/receipt1
```

* **splits.csv**

```csv
ExpID,Participant,Included,WeightOverride
E0001,Alice,TRUE,
E0001,Bob,TRUE,
E0001,Carol,TRUE,
```

👉 End-users update these CSVs daily during the trip.

## ▶️ Usage

Generate the Excel workbook:

```bash
python -m trip_splitter.build_or_update
```

Output:

```
Workbook saved to Trip_Splitter.xlsx
```

Open in Excel → explore **Settlement, Balances, Expenses, Summary**.

## 📊 Example Output

* Settlement: Alice pays Carol 1,533,000 ₫, Bob pays Carol 453,000 ₫.
* Summary: Charts of spending by category & participant.

## 🔒 Best Practices

* Keep receipts → upload to Google Drive → paste share link in `expenses.csv`.
* Update `rates.csv` daily with exchange rates.
* Use `splits.csv` for fairness (e.g., skip or weight participants).

## 🚀 Future Ideas

* One-click **PDF export** of Settlement & Summary.
* Mobile-friendly input (Google Sheets → CSV sync).
* Support for multiple trips.

---

💡 Built for hassle-free holiday group expense tracking!
