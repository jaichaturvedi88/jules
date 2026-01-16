
from flask import Flask, render_template, jsonify
import configparser
from dhanhq import dhanhq
import datetime
import holidays
import time
import threading
import schedule

app = Flask(__name__)
pnl_data = {}
NIFTY_LOT_SIZE = 50

def get_monthly_expiry_date():
    """Gets the monthly expiry date for Nifty options (last Thursday of the month)."""
    today = datetime.date.today()
    year = today.year
    month = today.month

    # Find the last day of the month
    if month == 12:
        last_day = datetime.date(year, month, 31)
    else:
        last_day = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)

    # Find the last Thursday of the month
    last_thursday = last_day
    while last_thursday.weekday() != 3: # 3 is for Thursday
        last_thursday -= datetime.timedelta(days=1)

    # Check if the last Thursday is a holiday
    india_holidays = holidays.country_holidays('IN', subdiv='MH')
    while last_thursday in india_holidays:
        last_thursday -= datetime.timedelta(days=1)

    return last_thursday.strftime('%d%b%y').upper()

def get_option_details(dhan, atm_strike, expiry_date):
    """Gets the option details for the given strike and expiry."""
    try:
        option_chain = dhan.get_option_chain(symbol='NIFTY',
                                             exchange_segment='NFO_OPT',
                                             instrument_type='OPTIDX',
                                             expiry_date=expiry_date)

        if option_chain and option_chain['success'] and 'data' in option_chain:
            for option in option_chain['data']:
                if option['strikePrice'] == atm_strike:
                    if option['optionType'] == 'CALL':
                        call_option = option
                    elif option['optionType'] == 'PUT':
                        put_option = option
            return call_option, put_option
        else:
            print("Error fetching option chain:", option_chain)
            return None, None
    except Exception as e:
        print(f"An error occurred while fetching option details: {e}")
        return None, None

def place_order(dhan, option, order_type='BUY'):
    """Places a market order for the given option."""
    try:
        # --- UNCOMMENT THE FOLLOWING BLOCK TO PLACE REAL ORDERS ---
        # print(f"Placing {order_type} order for {option['symbol']}")
        # order = dhan.place_order(
        #     security_id=str(option['securityId']),
        #     exchange_segment='NFO_OPT',
        #     transaction_type=order_type,
        #     quantity=NIFTY_LOT_SIZE,
        #     order_type='MARKET',
        #     product_type='INTRADAY',
        #     price=0
        # )
        # if order and order.get('status') == 'success':
        #     # In a real scenario, you would need to fetch the trade book
        #     # to get the actual executed price. For this example, we'll
        #     # continue to use the LTP as the simulated buy price.
        #     print(f"Order placed successfully for {option['symbol']}. Order ID: {order['data']['orderId']}")
        # else:
        #     print(f"Order placement failed for {option['symbol']}: {order}")
        #     return {'success': False, 'message': 'Order placement failed.'}
        # ---------------------------------------------------------

        # For simulation, we'll fetch the current price and use it as the buy price
        print(f"Simulating {order_type} order for {option['symbol']}")
        quote = dhan.get_quote(security_id=str(option['securityId']),
                               exchange_segment='NFO_OPT',
                               instrument_type='OPTIDX')

        if quote and quote['success'] and 'ltp' in quote['data']:
            buy_price = quote['data']['ltp']
            print(f"Simulated buy price for {option['symbol']}: {buy_price}")
            return {'success': True, 'order_id': 'simulated_order_123', 'buy_price': buy_price}
        else:
            print(f"Could not fetch LTP for {option['symbol']}. Order simulation failed.")
            return {'success': False, 'message': 'Could not fetch LTP.'}

    except Exception as e:
        print(f"An error occurred while placing the order: {e}")
        return {'success': False, 'message': str(e)}

def buy_straddle(dhan, atm_strike, expiry_date):
    """Buys an ATM straddle with a single retry."""
    call_option, put_option = get_option_details(dhan, atm_strike, expiry_date)

    if not call_option or not put_option:
        print("Could not find options for the ATM strike. Straddle not bought.")
        return None, None

    positions = []

    # Buy Call Option
    call_order = place_order(dhan, call_option, 'BUY')
    if not call_order.get('success'):
        print("Failed to buy call option. Retrying once...")
        time.sleep(1)
        call_order = place_order(dhan, call_option, 'BUY')

    if call_order.get('success'):
        positions.append({'symbol': call_option['symbol'],
                           'securityId': call_option['securityId'],
                           'buy_price': call_order['buy_price']})
    else:
        print("Failed to buy call option. Straddle failed.")
        return None, None

    # Buy Put Option
    put_order = place_order(dhan, put_option, 'BUY')
    if not put_order.get('success'):
        print("Failed to buy put option. Retrying once...")
        time.sleep(1)
        put_order = place_order(dhan, put_option, 'BUY')

    if put_order.get('success'):
        positions.append({'symbol': put_option['symbol'],
                           'securityId': put_option['securityId'],
                           'buy_price': put_order['buy_price']})
    else:
        print("Failed to buy put option. Straddle failed.")
        return None, None

    print("Straddle bought successfully!")
    return positions


def track_pnl(dhan, positions):
    """Tracks and displays the P&L for the given positions."""
    global pnl_data
    if not positions:
        return

    print("\nStarting P&L Tracking...")
    while True:
        total_pnl = 0
        pnl_data['positions'] = []
        for position in positions:
            quote = dhan.get_quote(security_id=str(position['securityId']),
                                   exchange_segment='NFO_OPT',
                                   instrument_type='OPTIDX')

            if quote and quote['success'] and 'ltp' in quote['data']:
                ltp = quote['data']['ltp']
                pnl = (ltp - position['buy_price']) * NIFTY_LOT_SIZE
                total_pnl += pnl
                pnl_data['positions'].append({
                    'symbol': position['symbol'],
                    'buy_price': position['buy_price'],
                    'ltp': ltp,
                    'pnl': round(pnl, 2)
                })
            else:
                print(f"Could not fetch LTP for {position['symbol']}.")

        pnl_data['total_pnl'] = round(total_pnl, 2)
        print(f"Total Straddle P&L: {pnl_data['total_pnl']:.2f}")
        time.sleep(15 * 60) # 15 minutes


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/pnl')
def get_pnl():
    return jsonify(pnl_data)

def get_dhan_credentials():
    """Reads Dhan API credentials from the config file."""
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config['dhan']['client_id'], config['dhan']['access_token']

def get_nifty_spot_price(dhan):
    """Fetches the current spot price of Nifty 50."""
    try:
        # Security ID for Nifty 50 index is 13, and exchange segment is IDX_I
        nifty_quote = dhan.get_quote(security_id='13',
                                    exchange_segment='IDX_I',
                                    instrument_type='INDEX')
        if nifty_quote and nifty_quote['success'] and 'ltp' in nifty_quote['data']:
            return nifty_quote['data']['ltp']
        else:
            print("Error fetching Nifty spot price:", nifty_quote)
            return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

def get_atm_strike(spot_price):
    """Calculates the at-the-money (ATM) strike price."""
    if spot_price:
        return round(spot_price / 50) * 50
    return None

def run_strategy():
    """The main trading strategy function."""
    global pnl_data
    print("Running the strategy at 9:15 AM...")
    client_id, access_token = get_dhan_credentials()

    if 'YOUR_CLIENT_ID' in client_id or 'YOUR_ACCESS_TOKEN' in access_token:
        print("Please update your Dhan API credentials in config.ini")
        pnl_data['error'] = "Please update your Dhan API credentials in config.ini"
        return

    dhan = dhanhq(client_id, access_token)

    spot_price = get_nifty_spot_price(dhan)

    if spot_price:
        atm_strike = get_atm_strike(spot_price)
        print(f"Nifty Spot Price: {spot_price}")
        print(f"ATM Strike Price: {atm_strike}")

        expiry_date = get_monthly_expiry_date()
        print(f"Monthly Expiry Date: {expiry_date}")

        positions = buy_straddle(dhan, atm_strike, expiry_date)

        if positions:
            pnl_thread = threading.Thread(target=track_pnl, args=(dhan, positions))
            pnl_thread.daemon = True
            pnl_thread.start()

if __name__ == '__main__':
    # The following line is for demonstration purposes.
    # Uncomment it if you want to run the strategy immediately on startup.
    # run_strategy()

    # Schedule the strategy to run every weekday at 9:15 AM
    schedule.every().monday.at("09:15").do(run_strategy)
    schedule.every().tuesday.at("09:15").do(run_strategy)
    schedule.every().wednesday.at("09:15").do(run_strategy)
    schedule.every().thursday.at("09:15").do(run_strategy)
    schedule.every().friday.at("09:15").do(run_strategy)

    # Start the Flask app in a separate thread
    flask_thread = threading.Thread(target=lambda: app.run(debug=True, use_reloader=False))
    flask_thread.daemon = True
    flask_thread.start()

    print("Scheduler started. Waiting for the scheduled job to run.")

    while True:
        schedule.run_pending()
        time.sleep(1)
