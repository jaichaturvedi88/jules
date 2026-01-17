
from flask import Flask, render_template, jsonify
import pandas as pd
import time
import threading
import schedule
from pnl_tracker import process_daily_pnl, load_pnl_data

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/pnl-history')
def pnl_history():
    return render_template('pnl_history.html')

@app.route('/api/pnl-data')
def get_pnl_data():
    try:
        df = load_pnl_data()

        # Reset index to make 'expiry_date' and 'trade_date' columns
        df_reset = df.reset_index()

        # Replace NaN with None for valid JSON
        df_reset.fillna(value=pd.NA, inplace=True)
        df_reset = df_reset.where(pd.notna(df_reset), None)

        # Group by expiry_date
        pnl_by_expiry = {}
        for name, group in df_reset.groupby('expiry_date'):
            group_data = group.drop(columns='expiry_date').to_dict(orient='records')
            pnl_by_expiry[name] = group_data

        return jsonify(pnl_by_expiry)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def run_scheduler():
    """Runs the scheduler in a background thread."""
    # Schedule the P&L processing job
    schedule.every().monday.at("15:45").do(process_daily_pnl)
    schedule.every().tuesday.at("15:45").do(process_daily_pnl)
    schedule.every().wednesday.at("15:45").do(process_daily_pnl)
    schedule.every().thursday.at("15:45").do(process_daily_pnl)
    schedule.every().friday.at("15:45").do(process_daily_pnl)

    print("Scheduler started. Waiting for the scheduled job to run at 15:45 on weekdays.")

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    # For demonstration, you might want to run the process once on startup
    # process_daily_pnl()

    # Start the scheduler in a separate thread
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()

    # Start the Flask app
    app.run(debug=True, use_reloader=False)
