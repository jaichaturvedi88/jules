
import configparser
import datetime
import holidays
import os
import pandas as pd
from dhanhq import dhanhq

# --- Constants ---
CSV_FILE = 'pnl_data.csv'
NIFTY_LOT_SIZE = 50

# --- Dhan API Helper ---

def get_dhan_credentials():
    """Reads Dhan API credentials from the config file."""
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config['dhan']['client_id'], config['dhan']['access_token']

def get_dhan_client():
    """Initializes and returns the Dhan API client."""
    client_id, access_token = get_dhan_credentials()
    if 'YOUR_CLIENT_ID' in client_id or 'YOUR_ACCESS_TOKEN' in access_token:
        raise ValueError("Please update your Dhan API credentials in config.ini")
    return dhanhq(client_id, access_token)

# --- Date and Expiry Helpers ---

def get_monthly_expiry_date(date=None):
    """Gets the monthly expiry date for Nifty options (last Thursday of the month)."""
    if date is None:
        date = datetime.date.today()

    year = date.year
    month = date.month

    if month == 12:
        last_day = datetime.date(year, month, 31)
    else:
        last_day = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)

    last_thursday = last_day
    while last_thursday.weekday() != 3:  # 3 is for Thursday
        last_thursday -= datetime.timedelta(days=1)

    india_holidays = holidays.country_holidays('IN', subdiv='MH')
    while last_thursday in india_holidays:
        last_thursday -= datetime.timedelta(days=1)

    return last_thursday

def get_expiry_str_for_dhan(expiry_date):
    """Formats the expiry date for the Dhan API (e.g., '25JUL24')."""
    return expiry_date.strftime('%d%b%y').upper()

# --- Market Data Helpers ---

def get_nifty_spot_close(dhan):
    """Fetches the closing price of Nifty 50."""
    try:
        quote = dhan.get_quote(security_id='13', exchange_segment='IDX_I', instrument_type='INDEX')
        if quote and quote['success'] and 'ohlc' in quote['data']:
            return quote['data']['ohlc']['close']
        else:
            print("Error fetching Nifty spot close:", quote)
            return None
    except Exception as e:
        print(f"An error occurred fetching Nifty spot close: {e}")
        return None

def get_atm_strike(spot_price):
    """Calculates the at-the-money (ATM) strike price."""
    if spot_price:
        return round(spot_price / 50) * 50
    return None

def get_option_close_price(dhan, security_id):
    """Fetches the closing price for a specific option."""
    try:
        quote = dhan.get_quote(security_id=str(security_id), exchange_segment='NFO_OPT', instrument_type='OPTIDX')
        if quote and quote['success'] and 'ohlc' in quote['data']:
            return quote['data']['ohlc']['close']
        else:
            print(f"Error fetching close for security_id {security_id}:", quote)
            return None
    except Exception as e:
        print(f"An error occurred fetching option close price: {e}")
        return None

def get_option_security_ids(dhan, atm_strike, expiry_date):
    """Gets the security IDs for the ATM call and put options."""
    try:
        expiry_str = get_expiry_str_for_dhan(expiry_date)
        option_chain = dhan.get_option_chain(symbol='NIFTY',
                                             exchange_segment='NFO_OPT',
                                             instrument_type='OPTIDX',
                                             expiry_date=expiry_str)

        if not (option_chain and option_chain['success'] and 'data' in option_chain):
            print("Error fetching option chain:", option_chain)
            return None, None

        call_id, put_id = None, None
        for option in option_chain['data']:
            if option['strikePrice'] == atm_strike:
                if option['optionType'] == 'CALL':
                    call_id = option['securityId']
                elif option['optionType'] == 'PUT':
                    put_id = option['securityId']

        if not call_id or not put_id:
            print(f"Could not find both call and put for strike {atm_strike}")

        return call_id, put_id
    except Exception as e:
        print(f"An error occurred while fetching option security IDs: {e}")
        return None, None

# --- CSV and P&L Logic ---

def init_csv():
    """Initializes the CSV file with headers if it doesn't exist."""
    if not os.path.exists(CSV_FILE):
        df = pd.DataFrame(columns=['expiry_date', 'trade_date', 'strike_price', 'buy_price'])
        df.set_index(['expiry_date', 'trade_date'], inplace=True)
        df.to_csv(CSV_FILE)
        print(f"'{CSV_FILE}' created.")

def load_pnl_data():
    """Loads the P&L data from the CSV file."""
    if not os.path.exists(CSV_FILE):
        init_csv()
    return pd.read_csv(CSV_FILE, index_col=['expiry_date', 'trade_date'])

def save_pnl_data(df):
    """Saves the DataFrame to the CSV file."""
    df.to_csv(CSV_FILE)

def process_daily_pnl():
    """The main function to create a new straddle and update P&L for existing ones."""
    print("\n--- Running Daily P&L Process ---")
    today = datetime.date.today()
    today_str = today.strftime('%Y-%m-%d')

    try:
        dhan = get_dhan_client()
        df = load_pnl_data()

        # --- Update P&L for all existing trades ---
        print("Updating P&L for existing trades...")
        # Create a set of unique security IDs to fetch
        security_ids_to_fetch = set()
        for index, row in df.iterrows():
            if 'call_id' in row and 'put_id' in row:
                security_ids_to_fetch.add(row['call_id'])
                security_ids_to_fetch.add(row['put_id'])

        # Fetch prices in a batch
        prices = {}
        for sec_id in security_ids_to_fetch:
            prices[sec_id] = get_option_close_price(dhan, sec_id)
            if prices[sec_id] is None:
                print(f"Warning: Could not fetch price for {sec_id}. P&L for this option will not be updated.")

        # Update DataFrame
        for index, row in df.iterrows():
            if 'call_id' in row and 'put_id' in row:
                call_close = prices.get(row['call_id'])
                put_close = prices.get(row['put_id'])

                if call_close is not None and put_close is not None:
                    current_straddle_price = call_close + put_close
                    pnl = (current_straddle_price - row['buy_price']) * NIFTY_LOT_SIZE
                    df.loc[index, today_str] = round(pnl, 2)

        # --- Create a new straddle for today ---
        print("Creating a new straddle for today...")
        expiry_date = get_monthly_expiry_date(today)
        expiry_date_str = expiry_date.strftime('%Y-%m-%d')

        if (expiry_date_str, today_str) in df.index:
            print(f"Straddle for {today_str} with expiry {expiry_date_str} already exists. Skipping.")
        else:
            spot_close = get_nifty_spot_close(dhan)
            if spot_close:
                atm_strike = get_atm_strike(spot_close)
                print(f"Nifty Spot Close: {spot_close}, ATM Strike: {atm_strike}")

                call_id, put_id = get_option_security_ids(dhan, atm_strike, expiry_date)

                if call_id and put_id:
                    call_close = get_option_close_price(dhan, call_id)
                    put_close = get_option_close_price(dhan, put_id)

                    if call_close is not None and put_close is not None:
                        buy_price = call_close + put_close

                        new_data = {
                            'strike_price': atm_strike,
                            'buy_price': buy_price,
                            'call_id': call_id,
                            'put_id': put_id,
                            today_str: 0 # P&L on buy date is 0
                        }

                        # Use pd.concat to add the new row
                        new_row = pd.DataFrame([new_data], index=pd.MultiIndex.from_tuples([(expiry_date_str, today_str)], names=['expiry_date', 'trade_date']))
                        df = pd.concat([df, new_row])

                        print(f"New straddle created: Strike={atm_strike}, Buy Price={buy_price}")

        save_pnl_data(df)
        print("--- Daily P&L Process Finished ---")

    except Exception as e:
        print(f"An error occurred in the daily P&L process: {e}")

if __name__ == '__main__':
    # This allows for direct execution for testing
    process_daily_pnl()
