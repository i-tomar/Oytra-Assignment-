"""Score one new COD order.
  python -m oytra.decide '{"customer_name":"asdf","phone":"9876543210","address":"call me","city":"Patna","state":"Bihar","pincode":"800001","order_value":649,"num_items":1,"customer_prior_orders":0,"customer_prior_rto":0,"utm_source":"meta_ads"}'
  python -m oytra.decide --examples
"""
import sys, json
from .engine import Engine

EXAMPLES = [
    {"order_id": "NEW1", "customer_name": "Priya Iyer", "phone": "9876543210", "address": "Flat 12, Lotus Apartments, Anna Nagar", "city": "Chennai",
     "state": "Tamil Nadu", "pincode": "600040", "order_value": 899, "num_items": 2, "customer_prior_orders": 3, "customer_prior_rto": 0, "utm_source": "direct"},
    {"order_id": "NEW2", "customer_name": "Ravi Kumar", "phone": "9123456789", "address": "Hanuman Mandir ke saamne, Station Road", "city": "Gorakhpur",
     "state": "Uttar Pradesh", "pincode": "273001", "order_value": 449, "num_items": 1, "customer_prior_orders": 0, "customer_prior_rto": 0, "utm_source": "meta_ads"},
    {"order_id": "NEW3", "customer_name": "asdf", "phone": "98765", "address": "call me", "city": "Patna", "state": "Bihar", "pincode": "800001",
     "order_value": 649, "num_items": 1, "customer_prior_orders": 0, "customer_prior_rto": 0, "utm_source": "meta_ads"},
    {"order_id": "NEW4", "customer_name": "Sunil Yadav", "phone": "9988776655", "address": "Govt School ke peeche wala ghar", "city": "Darbhanga",
     "state": "Bihar", "pincode": "846004", "order_value": 1499, "num_items": 1, "customer_prior_orders": 2, "customer_prior_rto": 2, "utm_source": "meta_ads"},
]

def main():
    eng = Engine.load()
    orders = EXAMPLES if (len(sys.argv) < 2 or sys.argv[1] == "--examples") else [json.loads(sys.argv[1])]
    print(f"(text judge: {type(eng.judge).__name__})")
    for o in orders:
        r = eng.decide(o)
        print(f"\n{o.get('order_id', '')} {o['customer_name']} | {o['city']} | ₹{o['order_value']}\n  -> {r['action_label'].upper()}  (risk {r['risk']:.0%})\n  {r['reason']}\n  expected ₹ per action: {r['expected_rupees']}")

if __name__ == "__main__":
    main()
