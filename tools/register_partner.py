"""One-time registration of your Tesla Developer app in a Fleet API region.

Gets a *partner* token (client_credentials) and calls POST /api/1/partner_accounts.
Tesla then downloads https://<domain>/.well-known/appspecific/com.tesla.3p.public-key.pem,
so the public key must already be published there.

Usage:
  python tools/register_partner.py --client-id XXX --domain example.com --region eu
  (the client secret is asked interactively and is not echoed or stored)
"""
import argparse
import getpass
import sys

import requests

TOKEN_URL = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token"
REGIONS = {
    "eu": "https://fleet-api.prd.eu.vn.cloud.tesla.com",
    "na": "https://fleet-api.prd.na.vn.cloud.tesla.com",
    "cn": "https://fleet-api.prd.cn.vn.cloud.tesla.cn",
}
SCOPES = "openid vehicle_device_data vehicle_cmds vehicle_charging_cmds"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-id", required=True)
    ap.add_argument("--domain", required=True, help="домен без https://, например example.com")
    ap.add_argument("--region", choices=REGIONS, default="eu")
    args = ap.parse_args()
    secret = getpass.getpass("Client Secret: ").strip()
    base = REGIONS[args.region]
    domain = args.domain.removeprefix("https://").strip("/")

    pub_url = f"https://{domain}/.well-known/appspecific/com.tesla.3p.public-key.pem"
    try:
        r = requests.get(pub_url, timeout=15)
        if r.status_code != 200 or "BEGIN PUBLIC KEY" not in r.text:
            sys.exit(f"Публичный ключ не найден по адресу {pub_url} (HTTP {r.status_code}).")
        print(f"✓ Публичный ключ доступен: {pub_url}")
    except requests.RequestException as exc:
        sys.exit(f"Не удалось открыть {pub_url}: {exc}")

    r = requests.post(TOKEN_URL, data={
        "grant_type": "client_credentials", "client_id": args.client_id, "client_secret": secret,
        "scope": SCOPES, "audience": base}, timeout=20)
    if r.status_code != 200:
        sys.exit(f"Не удалось получить partner token ({r.status_code}): {r.text[:400]}")
    token = r.json()["access_token"]
    print("✓ Partner token получен")

    r = requests.post(f"{base}/api/1/partner_accounts", json={"domain": domain},
                      headers={"Authorization": f"Bearer {token}"}, timeout=20)
    if r.status_code not in (200, 201):
        sys.exit(f"Регистрация не удалась ({r.status_code}): {r.text[:400]}")
    print(f"✓ Приложение зарегистрировано в регионе {args.region.upper()} для домена {domain}")

    r = requests.get(f"{base}/api/1/partner_accounts/public_key", params={"domain": domain},
                     headers={"Authorization": f"Bearer {token}"}, timeout=20)
    if r.ok:
        print("✓ Tesla видит ваш публичный ключ")
    print(f"\nСсылка для добавления виртуального ключа в автомобиль:\n  https://tesla.com/_ak/{domain}")


if __name__ == "__main__":
    main()
