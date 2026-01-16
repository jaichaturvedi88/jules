
import pandas as pd
import datetime
import random

# --- Constants ---
CSV_FILE = 'pnl_data.csv'
NIFTY_LOT_SIZE = 50

def get_trading_days(start_date, end_date):
    """Returns a list of trading days (Mon-Fri) between two dates."""
    return pd.date_range(start=start_date, end=end_date, freq='B').strftime('%Y-%m-%d').tolist()

def generate_dummy_data():
    """Generates dummy P&L data for December 2023 and January 2024."""
    print("Generating dummy historical data...")

    # --- December 2023 Expiry ---
    dec_expiry_date = '2023-12-28'
    dec_start_date = '2023-12-01'
    dec_trading_days = get_trading_days(dec_start_date, dec_expiry_date)

    dec_data = []
    for i, trade_date in enumerate(dec_trading_days):
        strike = 21000 + (i * 50)
        buy_price = random.uniform(200, 300)
        row = {
            'expiry_date': dec_expiry_date,
            'trade_date': trade_date,
            'strike_price': strike,
            'buy_price': buy_price,
            'call_id': 'dummy_call_' + str(i),
            'put_id': 'dummy_put_' + str(i)
        }
        # Simulate P&L
        pnl = 0
        for pnl_date in dec_trading_days[i:]:
            pnl += random.uniform(-500, 550)
            row[pnl_date] = round(pnl, 2)
        dec_data.append(row)

    # --- January 2024 Expiry ---
    jan_expiry_date = '2024-01-25'
    jan_start_date = '2024-01-01'
    jan_trading_days = get_trading_days(jan_start_date, jan_expiry_date)

    jan_data = []
    for i, trade_date in enumerate(jan_trading_days):
        strike = 22000 + (i * 50)
        buy_price = random.uniform(250, 350)
        row = {
            'expiry_date': jan_expiry_date,
            'trade_date': trade_date,
            'strike_price': strike,
            'buy_price': buy_price,
            'call_id': 'dummy_call_jan_' + str(i),
            'put_id': 'dummy_put_jan_' + str(i)
        }
        # Simulate P&L
        pnl = 0
        for pnl_date in jan_trading_days[i:]:
            pnl += random.uniform(-600, 650)
            row[pnl_date] = round(pnl, 2)
        jan_data.append(row)

    # --- Combine and Save ---
    df = pd.DataFrame(dec_data + jan_data)
    df.set_index(['expiry_date', 'trade_date'], inplace=True)
    df.to_csv(CSV_FILE)

    print("Dummy data for December 2023 and January 2024 has been generated.")
    print(f"Data saved to '{CSV_FILE}'")

if __name__ == '__main__':
    generate_dummy_data()
