#!/usr/bin/env python3
"""
Compute USDC on-chain transfer volume for agent addresses on Arc testnet.

Usage:
  pip install requests
  ARC_RPC_URL=https://rpc.testnet.arc.network \
  ARC_USDC_ADDRESS=0x3600000000000000000000000000000000000000 \
  python3 scripts/compute_agent_onchain_volume.py --addresses 0xDB131a4B88ACA79c29D5aDF3C3Df033954D36029,0xe430C73cF2beD38aBE83DF8309763191624373E1

Notes:
- The script uses `eth_getLogs` filtered to the USDC contract's Transfer events.
- It counts transfer events where the agent is sender or recipient and sums values (USDC has 6 decimals).
- For very long histories the RPC may reject wide queries; you can pass --from-block to restrict range.
"""
from __future__ import annotations

import argparse
import os
import math
import requests
from typing import List

TRANSFER_TOPIC = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
DEFAULT_RPC = os.environ.get('ARC_RPC_URL', 'https://rpc.testnet.arc.network')
DEFAULT_USDC = os.environ.get('ARC_USDC_ADDRESS', '0x3600000000000000000000000000000000000000')


def pad_topic_address(addr: str) -> str:
    a = addr.lower().replace('0x', '')
    return '0x' + a.rjust(64, '0')


def eth_call(rpc: str, method: str, params):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    r = requests.post(rpc, json=payload, timeout=30)
    r.raise_for_status()
    j = r.json()
    if 'error' in j:
        raise RuntimeError(j['error'])
    return j.get('result')


def get_logs(rpc: str, contract: str, topics: List[str], from_block: str = '0x0', to_block: str = 'latest'):
    params = [{"address": contract, "topics": topics, "fromBlock": from_block, "toBlock": to_block}]
    return eth_call(rpc, 'eth_getLogs', params)


def get_logs_paged(rpc: str, contract: str, topics: List[str], start_block: int, end_block: int, chunk: int = 5000):
    import time

    out = []
    b = start_block
    while b <= end_block:
        hi = min(b + chunk - 1, end_block)
        fb = hex(b)
        tb = hex(hi)
        attempts = 0
        while attempts < 6:
            try:
                res = get_logs(rpc, contract, topics, fb, tb)
                if res:
                    out.extend(res)
                break
            except Exception as e:
                attempts += 1
                wait = 0.5 * (2 ** (attempts - 1))
                time.sleep(wait)
                if attempts >= 6:
                    raise RuntimeError(f"logs failed for {fb}->{tb}: {e}")
        # polite pause between chunks
        time.sleep(0.05)
        b = hi + 1
    return out


def hex_to_int(h: str) -> int:
    return int(h, 16) if isinstance(h, str) and h.startswith('0x') else int(h)


def sum_usdc_for_address(rpc: str, usdc: str, address: str, from_block: str = '0x0', to_block: str = 'latest'):
    addr_topic = pad_topic_address(address)
    # resolve from_block/to_block to integers if hex/decimal
    def to_int(b):
        if isinstance(b, str) and b == 'latest':
            return None
        if isinstance(b, str) and b.startswith('0x'):
            return int(b, 16)
        return int(b)

    fb_i = to_int(from_block)
    tb_i = to_int(to_block)
    # if latest, query current block
    if tb_i is None:
        hb = eth_call(rpc, 'eth_blockNumber', [])
        tb_i = int(hb, 16)
    if fb_i is None:
        fb_i = 0

    # use paged logs to respect RPC limits
    logs_from = get_logs_paged(rpc, usdc, [TRANSFER_TOPIC, addr_topic, None], fb_i, tb_i)
    logs_to = get_logs_paged(rpc, usdc, [TRANSFER_TOPIC, None, addr_topic], fb_i, tb_i)

    total_in = 0
    for l in logs_to or []:
        value = hex_to_int(l.get('data', '0x0'))
        total_in += value
    total_out = 0
    for l in logs_from or []:
        value = hex_to_int(l.get('data', '0x0'))
        total_out += value

    return {
        'address': address,
        'in_wei': total_in,
        'out_wei': total_out,
        'in_usdc': total_in / 10**6,
        'out_usdc': total_out / 10**6,
        'count_in': len(logs_to or []),
        'count_out': len(logs_from or []),
    }


def sum_usdc_for_address_explorer(explorer_api: str, usdc: str, address: str):
    """Use Blockscout/Etherscan-style API to list token transfers and sum values."""
    # explorer_api e.g. https://testnet.arcscan.app/api
    page = 1
    offset = 1000
    total_in = 0
    total_out = 0
    count_in = 0
    count_out = 0
    while True:
        params = {
            'module': 'account',
            'action': 'tokentx',
            'contractaddress': usdc,
            'address': address,
            'page': page,
            'offset': offset,
            'startblock': 0,
            'endblock': 99999999,
            'sort': 'asc',
        }
        r = requests.get(explorer_api, params=params, timeout=30)
        r.raise_for_status()
        j = r.json()
        res = j.get('result') or []
        if not res:
            break
        for t in res:
            val = int(t.get('value') or 0)
            # normalized: token value already respects decimals (Etherscan returns raw integer)
            # determine if address is to or from
            frm = (t.get('from') or '').lower()
            to = (t.get('to') or '').lower()
            if frm == address.lower():
                total_out += val
                count_out += 1
            if to == address.lower():
                total_in += val
                count_in += 1
        if len(res) < offset:
            break
        page += 1
    return {
        'address': address,
        'in_wei': total_in,
        'out_wei': total_out,
        'in_usdc': total_in / 10**6,
        'out_usdc': total_out / 10**6,
        'count_in': count_in,
        'count_out': count_out,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--addresses', required=True, help='Comma-separated addresses to query')
    ap.add_argument('--use-explorer', action='store_true', help='Use explorer API (arcscan) instead of eth_getLogs')
    ap.add_argument('--from-block', default='0x0', help='Start block (hex or decimal). Default 0')
    ap.add_argument('--to-block', default='latest', help='End block. Default latest')
    args = ap.parse_args()

    rpc = os.environ.get('ARC_RPC_URL', DEFAULT_RPC)
    usdc = os.environ.get('ARC_USDC_ADDRESS', DEFAULT_USDC)

    addrs = [a.strip() for a in args.addresses.split(',') if a.strip()]
    if not addrs:
        print('No addresses provided')
        return 2

    print('RPC:', rpc)
    print('USDC contract:', usdc)
    print('Querying', len(addrs), 'addresses')
    for a in addrs:
        print('\nAddress:', a)
        try:
            if args.use_explorer:
                res = sum_usdc_for_address_explorer(os.environ.get('ARC_EXPLORER_API', 'https://testnet.arcscan.app/api'), usdc, a)
            else:
                res = sum_usdc_for_address(rpc, usdc, a, args.from_block, args.to_block)
            print('  Transfers in :', res['count_in'], 'amount USDC:', res['in_usdc'])
            print('  Transfers out:', res['count_out'], 'amount USDC:', res['out_usdc'])
            print('  Net received :', (res['in_usdc'] - res['out_usdc']))
        except Exception as e:
            print('  ERROR:', e)


if __name__ == '__main__':
    raise SystemExit(main())
