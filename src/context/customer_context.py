import csv

class CustomerContextStore:
    def __init__(self, csv_path: str):
        with open(csv_path,'r',encoding='utf-8') as f:
            self.rows=list(csv.DictReader(f))
    def lookup(self, key: str, value: str):
        v=(value or '').strip().lower()
        for r in self.rows:
            if (r.get(key,'') or '').strip().lower()==v:
                return {
                    'customer_name': r.get('NAME') or '',
                    'pan_no': r.get('PAN_NO') or '',
                    'mobile_no': r.get('MOBILENO') or '',
                    'email_id': r.get('EMAILID') or '',
                    'sip_date': r.get('SIP_DUE_DATE') or '',
                    'mandate_status': r.get('MANDATE_STATUS') or '',
                    'sip_amount': r.get('SIP_AMOUNT') or '',
                    'fund_name': r.get('FUND_NAME') or '',
                }
        return {}
