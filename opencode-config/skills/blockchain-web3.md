# Skill: Blockchain & Web3
# Loaded on-demand when task involves Solidity, smart contracts, DeFi, ERC standards, or Web3 development

## Auto-Detect

Trigger this skill when:
- Task mentions: Solidity, smart contract, blockchain, DeFi, ERC-20, NFT, Web3, Ethereum
- Files: `*.sol`, `hardhat.config.*`, `foundry.toml`, `contracts/`, `deploy/`
- Patterns: token, staking, swap, governance, bridge, oracle
- `package.json` contains: `ethers`, `viem`, `hardhat`, `@openzeppelin/contracts`, `wagmi`

---

## Decision Tree: Smart Contract Framework

```
What are you building?
+-- Need fast compilation + testing? -> Foundry (Forge + Cast + Anvil)
+-- Need JavaScript/TypeScript tooling? -> Hardhat
+-- Need both? -> Foundry for contracts + Hardhat for scripts/deploy
+-- Simple prototype? -> Remix IDE (browser-based)

Testing strategy:
+-- Unit tests (pure logic)? -> Foundry (Solidity tests, fastest)
+-- Integration tests (multi-contract)? -> Foundry or Hardhat
+-- Fork testing (mainnet state)? -> Foundry (forge test --fork-url)
+-- Fuzzing? -> Foundry (built-in fuzzer) or Echidna
+-- Formal verification? -> Certora or Halmos
```

---

## Solidity Patterns

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

/// @title Staking Contract
/// @notice Stake tokens to earn rewards over time
/// @dev Uses checks-effects-interactions pattern throughout
contract Staking is AccessControl, ReentrancyGuard, Pausable {
    bytes32 public constant ADMIN_ROLE = keccak256("ADMIN_ROLE");

    IERC20 public immutable stakingToken;
    IERC20 public immutable rewardToken;

    uint256 public rewardRate; // Rewards per second per token staked
    uint256 public lastUpdateTime;
    uint256 public rewardPerTokenStored;

    mapping(address => uint256) public userRewardPerTokenPaid;
    mapping(address => uint256) public rewards;
    mapping(address => uint256) public balances;
    uint256 public totalSupply;

    // Events (indexed for efficient filtering)
    event Staked(address indexed user, uint256 amount);
    event Withdrawn(address indexed user, uint256 amount);
    event RewardPaid(address indexed user, uint256 reward);

    // Custom errors (cheaper than require strings)
    error ZeroAmount();
    error InsufficientBalance(uint256 requested, uint256 available);
    error TransferFailed();

    constructor(address _stakingToken, address _rewardToken, uint256 _rewardRate) {
        stakingToken = IERC20(_stakingToken);
        rewardToken = IERC20(_rewardToken);
        rewardRate = _rewardRate;
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(ADMIN_ROLE, msg.sender);
    }

    modifier updateReward(address account) {
        rewardPerTokenStored = rewardPerToken();
        lastUpdateTime = block.timestamp;
        if (account != address(0)) {
            rewards[account] = earned(account);
            userRewardPerTokenPaid[account] = rewardPerTokenStored;
        }
        _;
    }

    /// @notice Stake tokens
    /// @param amount Amount of tokens to stake
    function stake(uint256 amount) external nonReentrant whenNotPaused updateReward(msg.sender) {
        if (amount == 0) revert ZeroAmount();

        // Effects before interactions (CEI pattern)
        totalSupply += amount;
        balances[msg.sender] += amount;

        // Interaction
        bool success = stakingToken.transferFrom(msg.sender, address(this), amount);
        if (!success) revert TransferFailed();

        emit Staked(msg.sender, amount);
    }

    /// @notice Withdraw staked tokens
    /// @param amount Amount to withdraw
    function withdraw(uint256 amount) external nonReentrant updateReward(msg.sender) {
        if (amount == 0) revert ZeroAmount();
        if (balances[msg.sender] < amount) {
            revert InsufficientBalance(amount, balances[msg.sender]);
        }

        // Effects
        totalSupply -= amount;
        balances[msg.sender] -= amount;

        // Interaction
        bool success = stakingToken.transfer(msg.sender, amount);
        if (!success) revert TransferFailed();

        emit Withdrawn(msg.sender, amount);
    }

    /// @notice Claim accumulated rewards
    function claimReward() external nonReentrant updateReward(msg.sender) {
        uint256 reward = rewards[msg.sender];
        if (reward == 0) revert ZeroAmount();

        // Effects
        rewards[msg.sender] = 0;

        // Interaction
        bool success = rewardToken.transfer(msg.sender, reward);
        if (!success) revert TransferFailed();

        emit RewardPaid(msg.sender, reward);
    }

    function rewardPerToken() public view returns (uint256) {
        if (totalSupply == 0) return rewardPerTokenStored;
        return rewardPerTokenStored +
            ((block.timestamp - lastUpdateTime) * rewardRate * 1e18) / totalSupply;
    }

    function earned(address account) public view returns (uint256) {
        return (balances[account] * (rewardPerToken() - userRewardPerTokenPaid[account])) / 1e18
            + rewards[account];
    }

    // Admin functions
    function pause() external onlyRole(ADMIN_ROLE) { _pause(); }
    function unpause() external onlyRole(ADMIN_ROLE) { _unpause(); }
}
```

---

## Gas Optimization

```solidity
// Gas optimization techniques

// 1. Pack storage variables (each slot = 32 bytes)
// BAD: 3 slots
contract Bad {
    uint256 a;  // slot 0 (32 bytes)
    uint8 b;    // slot 1 (1 byte, wastes 31 bytes)
    uint256 c;  // slot 2 (32 bytes)
}

// GOOD: 2 slots
contract Good {
    uint256 a;  // slot 0
    uint256 c;  // slot 1
    uint8 b;    // slot 1 (packed with c? No - uint8 after uint256 starts new slot)
    // Actually: put small types together
}

contract BestPacking {
    uint128 a;  // slot 0 (16 bytes)
    uint128 b;  // slot 0 (16 bytes) - packed!
    uint256 c;  // slot 1
}

// 2. Use custom errors instead of require strings
// BAD: ~100 gas more per revert
require(amount > 0, "Amount must be greater than zero");
// GOOD: cheaper
error ZeroAmount();
if (amount == 0) revert ZeroAmount();

// 3. Cache storage reads in memory
// BAD: reads storage multiple times
function bad() external {
    for (uint i = 0; i < array.length; i++) { // storage read each iteration
        total += array[i];
    }
}
// GOOD: cache in memory
function good() external {
    uint256 len = array.length; // single storage read
    uint256 _total = 0;        // memory variable
    for (uint i = 0; i < len; i++) {
        _total += array[i];
    }
    total = _total; // single storage write
}

// 4. Use unchecked for safe arithmetic
function sum(uint256[] calldata nums) external pure returns (uint256 total) {
    uint256 len = nums.length;
    for (uint256 i = 0; i < len;) {
        total += nums[i];
        unchecked { ++i; } // Safe: i < len prevents overflow
    }
}

// 5. Use calldata instead of memory for read-only arrays
function process(uint256[] calldata data) external pure returns (uint256) {
    // calldata is cheaper than memory (no copy)
    return data[0] + data[1];
}

// 6. Use immutable for constructor-set values
contract Token {
    address public immutable owner; // Stored in bytecode, not storage
    constructor() { owner = msg.sender; }
}
```

---

## Smart Contract Security

```solidity
// Common vulnerabilities and mitigations

// 1. Reentrancy - Use ReentrancyGuard + CEI pattern
// VULNERABLE:
function withdrawBad() external {
    uint256 amount = balances[msg.sender];
    (bool success,) = msg.sender.call{value: amount}(""); // External call BEFORE state update
    balances[msg.sender] = 0; // Too late!
}

// SAFE: Checks-Effects-Interactions
function withdrawSafe() external nonReentrant {
    uint256 amount = balances[msg.sender];
    if (amount == 0) revert ZeroBalance();
    balances[msg.sender] = 0;  // Effect BEFORE interaction
    (bool success,) = msg.sender.call{value: amount}("");
    if (!success) revert TransferFailed();
}

// 2. Front-running protection - Commit-reveal scheme
contract CommitReveal {
    mapping(bytes32 => uint256) public commits;

    function commit(bytes32 hash) external {
        commits[hash] = block.timestamp;
    }

    function reveal(uint256 value, bytes32 salt) external {
        bytes32 hash = keccak256(abi.encodePacked(value, salt, msg.sender));
        require(commits[hash] > 0, "No commit found");
        require(block.timestamp - commits[hash] > 1 minutes, "Too early");
        require(block.timestamp - commits[hash] < 1 hours, "Expired");
        delete commits[hash];
        // Process revealed value
    }
}

// 3. Oracle manipulation - Use TWAP, not spot price
// NEVER use: pair.getReserves() for pricing (manipulable in same tx)
// USE: Chainlink oracles or Uniswap TWAP

// 4. Integer overflow - Solidity 0.8+ has built-in checks
// But be careful with unchecked blocks!

// 5. Access control - Use OpenZeppelin AccessControl
// NEVER use tx.origin for auth (phishing vulnerability)
```

---

## Testing with Foundry

```solidity
// test/Staking.t.sol
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/Staking.sol";
import "../src/mocks/MockERC20.sol";

contract StakingTest is Test {
    Staking public staking;
    MockERC20 public stakingToken;
    MockERC20 public rewardToken;

    address public alice = makeAddr("alice");
    address public bob = makeAddr("bob");

    function setUp() public {
        stakingToken = new MockERC20("Stake", "STK");
        rewardToken = new MockERC20("Reward", "RWD");
        staking = new Staking(address(stakingToken), address(rewardToken), 1e18);

        // Fund accounts
        stakingToken.mint(alice, 1000e18);
        stakingToken.mint(bob, 1000e18);
        rewardToken.mint(address(staking), 1_000_000e18);

        // Approve
        vm.prank(alice);
        stakingToken.approve(address(staking), type(uint256).max);
        vm.prank(bob);
        stakingToken.approve(address(staking), type(uint256).max);
    }

    function test_Stake() public {
        vm.prank(alice);
        staking.stake(100e18);

        assertEq(staking.balances(alice), 100e18);
        assertEq(staking.totalSupply(), 100e18);
    }

    function test_RevertWhen_StakeZero() public {
        vm.prank(alice);
        vm.expectRevert(Staking.ZeroAmount.selector);
        staking.stake(0);
    }

    function test_EarnRewards() public {
        vm.prank(alice);
        staking.stake(100e18);

        // Advance time
        vm.warp(block.timestamp + 1 days);

        uint256 earned = staking.earned(alice);
        assertGt(earned, 0);
    }

    // Fuzz testing
    function testFuzz_Stake(uint256 amount) public {
        amount = bound(amount, 1, 1000e18); // Constrain to valid range

        vm.prank(alice);
        staking.stake(amount);

        assertEq(staking.balances(alice), amount);
    }

    // Invariant testing
    function invariant_TotalSupplyMatchesBalances() public view {
        uint256 total = staking.balances(alice) + staking.balances(bob);
        assertEq(staking.totalSupply(), total);
    }
}
```

---

## Frontend Integration (viem + wagmi)

```typescript
import { useReadContract, useWriteContract, useWaitForTransactionReceipt } from 'wagmi';
import { parseEther, formatEther } from 'viem';
import { stakingAbi } from './abis/staking';

function StakingUI() {
  const { data: balance } = useReadContract({
    address: STAKING_ADDRESS,
    abi: stakingAbi,
    functionName: 'balances',
    args: [userAddress],
  });

  const { data: earned } = useReadContract({
    address: STAKING_ADDRESS,
    abi: stakingAbi,
    functionName: 'earned',
    args: [userAddress],
    query: { refetchInterval: 10000 }, // Poll every 10s
  });

  const { writeContract, data: hash } = useWriteContract();
  const { isLoading, isSuccess } = useWaitForTransactionReceipt({ hash });

  const handleStake = (amount: string) => {
    writeContract({
      address: STAKING_ADDRESS,
      abi: stakingAbi,
      functionName: 'stake',
      args: [parseEther(amount)],
    });
  };

  return (
    <div>
      <p>Staked: {formatEther(balance ?? 0n)} tokens</p>
      <p>Earned: {formatEther(earned ?? 0n)} rewards</p>
      <button onClick={() => handleStake('100')} disabled={isLoading}>
        {isLoading ? 'Confirming...' : 'Stake 100 Tokens'}
      </button>
    </div>
  );
}
```

---

## Anti-Patterns

| Anti-Pattern | Problem | Solution |
|---|---|---|
| No reentrancy guard | Funds drained via recursive calls | ReentrancyGuard + CEI pattern |
| Using tx.origin for auth | Phishing attacks via proxy contracts | Always use msg.sender |
| Unbounded loops | Transaction runs out of gas | Pagination or pull-over-push pattern |
| Hardcoded addresses | Cannot upgrade or migrate | Use immutable + constructor params |
| No event emission | Off-chain systems cannot track state | Emit events for all state changes |
| Using transfer/send | Breaks with contracts that need > 2300 gas | Use call with reentrancy guard |
| No upgrade path | Cannot fix bugs in production | Proxy pattern (UUPS or Transparent) |
| Spot price for DeFi | Flash loan manipulation | TWAP oracles or Chainlink |
