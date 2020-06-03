# When running locally, execute the statements found in the file linked below to load the EIP20_ABI variable.
# See: https://github.com/carver/ethtoken.py/blob/v0.0.1-alpha.4/ethtoken/abi.py

from web3 import Web3
import json

def authenticate(addr, cred):
    
    with open('paymentABI.json') as f:
        paymentabi = json.load(f)

    w3 = Web3(Web3.WebsocketProvider("https://ropsten.infura.io/v3/f9c889dXXXXXXXXXXX186e5"))
    unicorns = w3.eth.contract(address="0xfB6916095XXXXXXXXX74c37c5d359", abi=paymentabi)

    nonce = w3.eth.getTransactionCount(addr) 
    # user account  

    # Build a transaction that invokes this contract's function, called transfer
    unicorn_txn = unicorns.functions.pay().buildTransaction({
        'chainId': 3,
        'gas': 70000,
        'gasPrice': w3.toWei('1', 'gwei'),
        'nonce': nonce,
        'value': w3.toWei('0.1', 'ether')
        })
    
    # user private key
    private_key = cred
    
    signed_txn = w3.eth.account.sign_transaction(unicorn_txn, private_key=private_key)

    try:
        w3.eth.sendRawTransaction(signed_txn.rawTransaction)
        # w3.toHex(w3.keccak(signed_txn.rawTransaction))
    except Exception as e:
        return False
        print('Transaction failed', e)
    return True
    # When you run sendRawTransaction, you get the same result as the hash of the transaction:
