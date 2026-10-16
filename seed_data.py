"""Creates demo users, consumers and ~1 year of hourly readings.  Run:  python seed_data.py"""
import numpy as np
import pandas as pd
from werkzeug.security import generate_password_hash
from app import create_app
import repo

CONSUMERS = [  # name, address, meter, category, base kWh/hour
    ("Sharma Residence", "12 MG Road, Bengaluru", "MTR-1001", "Residential", 0.9),
    ("Iyer Apartment", "44 Indiranagar, Bengaluru", "MTR-1002", "Residential", 0.6),
    ("Green Leaf Cafe", "7 Church Street, Bengaluru", "MTR-2001", "Commercial", 2.2),
    ("City Public School", "School Lane, Jayanagar", "MTR-3001", "Educational", 3.0),
    ("Precision Tools Pvt Ltd", "Peenya Industrial Area", "MTR-4001", "Industrial", 9.0),
]
HOUR_PROFILE = {
    "Residential": [.5,.4,.4,.4,.4,.6,1,1.2,.9,.7,.7,.8,.9,.8,.8,.9,1.1,1.5,1.9,2,1.8,1.4,.9,.6],
    "Commercial":  [.3,.3,.3,.3,.3,.3,.4,.6,1,1.4,1.6,1.7,1.8,1.7,1.6,1.6,1.7,1.8,1.9,1.6,1.2,.8,.5,.4],
    "Educational": [.1,.1,.1,.1,.1,.2,.6,1.4,1.8,1.9,1.9,1.8,1.7,1.7,1.5,1.1,.5,.3,.2,.2,.1,.1,.1,.1],
    "Industrial":  [.8,.8,.8,.8,.8,.9,1.1,1.3,1.4,1.4,1.4,1.4,1.3,1.4,1.4,1.4,1.3,1.2,1.0,.9,.9,.8,.8,.8],
}


def main(days=365):
    app = create_app()
    rng = np.random.default_rng(7)
    with app.app_context():
        if not repo.get_user_by_name("admin"):
            repo.create_user("admin", generate_password_hash("admin12345"), "admin")
        for name, addr, meter, cat, _ in CONSUMERS:
            try:
                repo.create_consumer(name, addr, meter, cat)
            except Exception:
                pass
        idx = pd.date_range(end=pd.Timestamp.today().normalize() - pd.Timedelta(hours=1), periods=days * 24, freq="h")
        meters = {c["meter_no"]: c["consumer_id"] for c in repo.list_consumers()}
        for name, addr, meter, cat, base in CONSUMERS:
            prof = np.array(HOUR_PROFILE[cat])[idx.hour]
            doy = idx.dayofyear.values
            season = 1 + 0.35 * np.exp(-((doy - 130) / 40) ** 2) + 0.12 * np.exp(-((doy - 270) / 30) ** 2)  # summer cooling
            weekend = idx.dayofweek.values >= 5
            wk = np.where(weekend, {"Residential": 1.2, "Commercial": 1.3, "Educational": .15, "Industrial": .55}[cat], 1.0)
            units = np.clip(base * prof * season * wk * rng.normal(1, .08, len(idx)), 0, None).round(3)
            meter_reading = 1000 + units.cumsum().round(2)
            rows = [(meters[meter], t.strftime("%Y-%m-%d %H:%M:%S"), float(u), float(m))
                    for t, u, m in zip(idx, units, meter_reading)]
            repo.insert_readings(rows)
        # sample upload file (daily rows) for demoing the upload screen
        d = pd.date_range(pd.Timestamp.today().normalize() + pd.Timedelta(days=1), periods=10, freq="D")  # after seeded data
        pd.DataFrame({"meter_no": "MTR-1001", "reading_date": d.strftime("%Y-%m-%d"),
                      "units_consumed": rng.uniform(18, 26, 10).round(2)}).to_csv("sample_upload.csv", index=False)
    print("Seeded. Login: admin / admin12345")


if __name__ == "__main__":
    main()
