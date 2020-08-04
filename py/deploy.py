from web3.auto import w3
from web3 import Web3
from solc import compile_standard
import os
import json

w3.eth.defaultAccount = w3.eth.accounts[0]


def geneateCompiled_sol(sol_name, contract_name):
    basedir = "/Users/gaojin/Documents/GitHub/yvault/contracts"
    fname = os.path.join(basedir, sol_name)
    with open(fname) as f:
        content = f.read()
    _compile_standard = {
        "language": "Solidity",
        "sources": {sol_name: {"content": content}},
        "settings": {
            "outputSelection": {
                "*": {"*": ["metadata", "evm.bytecode", "evm.bytecode.sourceMap"]}
            }
        },
    }
    compiled_sol = compile_standard(_compile_standard)
    bytecode = compiled_sol["contracts"][sol_name][contract_name]["evm"]["bytecode"][
        "object"
    ]
    abi = json.loads(compiled_sol["contracts"][sol_name][contract_name]["metadata"])[
        "output"
    ]["abi"]

    c = w3.eth.contract(abi=abi, bytecode=bytecode)
    return c, abi


def deploy():
    ## Controller
    Controller, abi = geneateCompiled_sol("Controller.sol", "Controller")
    tx_hash = Controller.constructor().transact()
    tx_receipt = w3.eth.waitForTransactionReceipt(tx_hash)
    controller_instance = w3.eth.contract(address=tx_receipt.contractAddress, abi=abi)

    Yfii, abi = geneateCompiled_sol("yfiicontract.sol", "YFII")
    tx_hash = Yfii.constructor("YFII", "YFII").transact()
    tx_receipt = w3.eth.waitForTransactionReceipt(tx_hash)
    yfii_instance = w3.eth.contract(address=tx_receipt.contractAddress, abi=abi)
    print(yfii_instance.functions.name().call())

    token, abi = geneateCompiled_sol("yfiicontract.sol", "NewToken")
    tx_hash = token.constructor("NewToken", "NewToken").transact()
    tx_receipt = w3.eth.waitForTransactionReceipt(tx_hash)
    token_instance = w3.eth.contract(address=tx_receipt.contractAddress, abi=abi)
    print(token_instance.functions.name().call())

    StrategyYfii, abi = geneateCompiled_sol("StrategyCurveYfii.sol", "StrategyYfii")
    tx_hash = StrategyYfii.constructor(controller_instance.address).transact()
    tx_receipt = w3.eth.waitForTransactionReceipt(tx_hash)
    strategyYfii_instance = w3.eth.contract(address=tx_receipt.contractAddress, abi=abi)
    # print(strategyYfii_instance.functions.controller().call())
    assert (
        strategyYfii_instance.functions.controller().call()
        == controller_instance.address
    )

    yVault, abi = geneateCompiled_sol("yvault.sol", "yVault")
    tx_hash = yVault.constructor(
        token_instance.address, controller_instance.address, yfii_instance.address
    ).transact()
    tx_receipt = w3.eth.waitForTransactionReceipt(tx_hash)
    yVault_instance = w3.eth.contract(address=tx_receipt.contractAddress, abi=abi)

    assert yVault_instance.functions.controller().call() == controller_instance.address
    assert yVault_instance.functions.Yfiitoken().call() == yfii_instance.address
    assert yVault_instance.functions.token().call() == token_instance.address

    return (
        yfii_instance,
        token_instance,
        controller_instance,
        yVault_instance,
        strategyYfii_instance,
    )


(
    yfii_instance,
    token_instance,
    controller_instance,
    yVault_instance,
    strategyYfii_instance,
) = deploy()
from_0 = w3.eth.accounts[0]
from_1 = w3.eth.accounts[1]
from_2 = w3.eth.accounts[2]


def run():
    setup()

    # from_1 depost
    w3.eth.defaultAccount = from_1
    deposit_balance = w3.toWei("1000", "ether")
    yVault_instance.functions.deposit(deposit_balance).transact()
    # 检查 yVault的余额情况
    assert (
        token_instance.functions.balanceOf(yVault_instance.address).call()
        == deposit_balance
    )
    total_stake, total_out, earnings_per_share = yVault_instance.functions.global_(
        0
    ).call()
    assert [total_stake, total_out, earnings_per_share] == [deposit_balance, 0, 0]

    # 检查 用户存入情况
    stake, payout, total_out = yVault_instance.functions.plyr_(from_1).call()
    assert [stake, payout, total_out] == [deposit_balance, 0, 0]

    # cal_out
    assert yVault_instance.functions.cal_out(from_1).call() == 0

    # make_profit
    w3.eth.defaultAccount = from_0
    make_profit_balance = w3.toWei("1", "ether")
    yVault_instance.functions.make_profit(make_profit_balance).transact()
    assert (
        yfii_instance.functions.balanceOf(yVault_instance.address).call()
        == make_profit_balance
    )

    ##TODO:
    _earnings_per_share = earnings_per_share + (
        make_profit_balance * 1e22 / total_stake
    )
    _earnings_per_share = int(_earnings_per_share)
    total_stake, total_out, earnings_per_share = yVault_instance.functions.global_(
        0
    ).call()
    assert [total_stake, total_out, earnings_per_share] == [
        deposit_balance,
        make_profit_balance,
        _earnings_per_share,
    ]
    ## 算出应该领取的分红
    _calout = earnings_per_share * stake / 1e22 - payout
    assert yVault_instance.functions.cal_out(from_1).call() == make_profit_balance

    # 领取分红
    w3.eth.defaultAccount = from_1
    yVault_instance.functions.claim().transact()

    stake, payout, total_out = yVault_instance.functions.plyr_(from_1).call()
    assert [stake, payout, total_out] == [deposit_balance, _calout, make_profit_balance]

    assert (
        yfii_instance.functions.balanceOf(yVault_instance.address).call()
        == make_profit_balance - _calout
    )


def setup():

    w3.eth.defaultAccount = from_0
    ## yfii mint to from_0
    yfii_instance.functions.addMinter(from_0).transact()
    mint_balance = w3.toWei(str(pow(2, 100)), "ether")
    yfii_instance.functions.mint(from_0, mint_balance).transact()

    assert yfii_instance.functions.balanceOf(from_0).call() == mint_balance

    ## token mint to from_1,from_2
    token_instance.functions.addMinter(from_0).transact()
    token_instance.functions.mint(from_1, mint_balance).transact()
    token_instance.functions.mint(from_2, mint_balance).transact()

    assert token_instance.functions.balanceOf(from_1).call() == mint_balance
    assert token_instance.functions.balanceOf(from_2).call() == mint_balance

    ## approve
    approve_balance = w3.toWei(str(pow(2, 100) - 1), "ether")

    ## yfii: from_0 approve to yVault_instance
    yfii_instance.functions.approve(
        yVault_instance.address, approve_balance
    ).transact()  ## make_profit

    ## token: from_1 approve to yVault_instance
    w3.eth.defaultAccount = from_1
    token_instance.functions.approve(
        yVault_instance.address, approve_balance
    ).transact()  ## deposit

    ## token: from_2 approve to yVault_instance
    w3.eth.defaultAccount = from_2
    token_instance.functions.approve(
        yVault_instance.address, approve_balance
    ).transact()  ## deposit


if __name__ == "__main__":
    run()
