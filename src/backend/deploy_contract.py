import argparse
import os
import sys
import json
from web3 import Web3
from dotenv import load_dotenv

# Add path to backend
sys.path.append(os.path.dirname(__file__))

load_dotenv()

def validate_token_address(w3, token_address):
    if not token_address:
        print("❌ Error: USDT_ADDRESS missing in .env")
        return False

    try:
        token_address = Web3.to_checksum_address(token_address)
    except Exception:
        print("❌ Error: USDT_ADDRESS is not a valid address")
        return False

    erc20_abi = [
        {
            'constant': True,
            'inputs': [],
            'name': 'name',
            'outputs': [{'name': '', 'type': 'string'}],
            'payable': False,
            'stateMutability': 'view',
            'type': 'function',
        },
        {
            'constant': True,
            'inputs': [],
            'name': 'symbol',
            'outputs': [{'name': '', 'type': 'string'}],
            'payable': False,
            'stateMutability': 'view',
            'type': 'function',
        },
        {
            'constant': True,
            'inputs': [],
            'name': 'decimals',
            'outputs': [{'name': '', 'type': 'uint8'}],
            'payable': False,
            'stateMutability': 'view',
            'type': 'function',
        },
    ]

    contract = w3.eth.contract(address=token_address, abi=erc20_abi)
    try:
        name = contract.functions.name().call()
        symbol = contract.functions.symbol().call()
        decimals = contract.functions.decimals().call()
    except Exception as e:
        print(f"❌ Token lookup failed: {e}")
        return False

    print(f"✅ Token looks valid on chain")
    print(f"   Address: {token_address}")
    print(f"   Name:    {name}")
    print(f"   Symbol:  {symbol}")
    print(f"   Decimals:{decimals}")
    return True


def deploy():
    print("🚀 sideQuest Contract Deployment (Base Sepolia)")
    print("---------------------------------------------")

    rpc_url = os.getenv("RPC_URL")
    private_key = os.getenv("ADMIN_PRIVATE_KEY")
    
    if not rpc_url or not private_key:
        print("❌ Error: RPC_URL or ADMIN_PRIVATE_KEY missing in .env")
        return

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print("❌ Error: Could not connect to RPC.")
        return

    account = w3.eth.account.from_key(private_key)
    print(f"👤 Deployer Address: {account.address}")
    print(f"💰 Balance: {w3.from_wei(w3.eth.get_balance(account.address), 'ether')} ETH")

    # Path to contract
    contract_path = os.path.join(os.path.dirname(__file__), "../contracts/contracts/core/ClawEscrow.sol")
    
    print("\n🔨 Compiling contract (Requires solc)...")
    try:
        from solcx import compile_standard, install_solc
        install_solc('0.8.20')
        
        with open(contract_path, "r") as f:
            source = f.read()

        compiled_sol = compile_standard(
            {
                "language": "Solidity",
                "sources": {"ClawEscrow.sol": {"content": source}},
                "settings": {
                    "outputSelection": {
                        "*": {"*": ["abi", "evm.bytecode.object"]}
                    }
                },
            },
            solc_version="0.8.20",
        )

        # Get Bytecode/ABI
        bytecode = compiled_sol["contracts"]["ClawEscrow.sol"]["ClawEscrow"]["evm"]["bytecode"]["object"]
        abi = compiled_sol["contracts"]["ClawEscrow.sol"]["ClawEscrow"]["abi"]
        
    except ImportError:
        print("❌ Error: 'py-solc-x' not found. Please install it with 'pip install py-solc-x'.")
        return
    except Exception as e:
        print(f"❌ Compilation Error: {e}")
        return

    usdt_address = os.getenv("USDT_ADDRESS")
    if not usdt_address:
        print("❌ Error: USDT_ADDRESS missing in .env")
        return
    if not Web3.is_checksum_address(usdt_address):
        try:
            usdt_address = Web3.to_checksum_address(usdt_address)
        except Exception:
            print("❌ Error: USDT_ADDRESS is not a valid address")
            return

    if not validate_token_address(w3, usdt_address):
        print("❌ Please fix USDT_ADDRESS in .env before deployment.")
        return

    print("📤 Sending Deployment Transaction...")
    ClawEscrow = w3.eth.contract(abi=abi, bytecode=bytecode)
    nonce = w3.eth.get_transaction_count(account.address)
    
    transaction = ClawEscrow.constructor(usdt_address).build_transaction({
        "chainId": w3.eth.chain_id,
        "gas": 4000000,
        "gasPrice": w3.eth.gas_price,
        "nonce": nonce,
    })

    signed_txn = w3.eth.account.sign_transaction(transaction, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
    print(f"⏳ tx_hash: {w3.to_hex(tx_hash)}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    contract_address = receipt.contractAddress
    print(f"\n✅ SUCCESSFULLY DEPLOYED!")
    print(f"🔗 Contract Address: {contract_address}")

    # Update .env
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    with open(env_path, "r") as f:
        lines = f.readlines()
    
    updated = False
    new_lines = []
    for line in lines:
        if line.startswith("CSC_ADDRESS="):
            new_lines.append(f"CSC_ADDRESS={contract_address}\n")
            updated = True
        else:
            new_lines.append(line)
    
    if not updated:
        new_lines.append(f"CSC_ADDRESS={contract_address}\n")

    with open(env_path, "w") as f:
        f.writelines(new_lines)
    
    print("📁 Updated .env with new contract address.")

def main():
    parser = argparse.ArgumentParser(description='Deploy ClawEscrow or validate stablecoin address')
    parser.add_argument('--validate-token', action='store_true', help='Validate USDT_ADDRESS from .env before deployment')
    args = parser.parse_args()

    rpc_url = os.getenv("RPC_URL")
    if not rpc_url:
        print("❌ Error: RPC_URL missing in .env")
        return

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print("❌ Error: Could not connect to RPC.")
        return

    if args.validate_token:
        validate_token_address(w3, os.getenv("USDT_ADDRESS"))
        return

    deploy()

if __name__ == "__main__":
    main()
