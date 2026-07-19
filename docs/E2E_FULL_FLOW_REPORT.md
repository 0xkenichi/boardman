# ClawStation E2E Full Flow Report

Generated: 2026-07-19T02:48:38.468382+00:00

## Stack

- Circle Programmable Wallets (developer-controlled)
- Base Sepolia
- ClawEscrow
- Telegram bot + gaming schema

## Step log

### 2026-07-19T02:47:04.904154+00:00 — start_e2e


### 2026-07-19T02:47:09.021978+00:00 — wallets

- **creator**: `{"wallet_id": "aafd7ca8-395d-526e-8264-d7652add88fc", "address": "0xa51fbdcc5fe502d6a74044322ef605e7abfbec5d", "blockchain": "BASE-SEPOLIA"}`
- **opponent**: `{"wallet_id": "6b0e5af3-ee45-5b6b-85ac-406862201d54", "address": "0x95cff0fd86f0f62502178dc0fc0f79472659a16d", "blockchain": "BASE-SEPOLIA"}`

### 2026-07-19T02:47:14.507119+00:00 — eth_balance

- **addr**: `"0xa51fbdcc5fe502d6a74044322ef605e7abfbec5d"`
- **eth**: `0.0003`

### 2026-07-19T02:47:14.819166+00:00 — eth_balance

- **addr**: `"0x95cff0fd86f0f62502178dc0fc0f79472659a16d"`
- **eth**: `0.0003`

### 2026-07-19T02:47:30.858205+00:00 — usdc_before

- **creator**: `57.0`
- **opponent**: `0.0`

### 2026-07-19T02:47:30.858255+00:00 — fund_opponent_usdc

- **amount**: `3`

### 2026-07-19T02:47:33.626687+00:00 — transfer_result

- **result**: `{"success": true, "transaction_id": "68f446b2-1b47-5595-be5a-28e4637758af", "status": "PENDING", "tx_hash": null, "to_address": "0x95cff0fd86f0f62502178dc0fc0f79472659a16d", "amount_usdc": 3.0, "blockchain": null}`

### 2026-07-19T02:47:49.993525+00:00 — transfer_wait

- **result**: `{"success": true, "status": "CONFIRMED", "tx_hash": "0x24b742f1e7ebf6881ee847726770b14161ea1c7be48620e243fdf2261b4afb16", "time_waited": 16}`

### 2026-07-19T02:48:03.322247+00:00 — usdc_after_fund

- **creator**: `54.0`
- **opponent**: `3.0`

### 2026-07-19T02:48:06.525818+00:00 — challenge_created

- **challenge**: `{"id": "c6b3b03a-6dc9-42d6-addd-b8b7c0030224", "issuer_id": "62440a47-f4fc-4249-a627-46aaa2d039ef", "target_id": "cfa4a1b9-a785-4045-ac68-c2bd3fdefc07", "game_type": "EA FC", "stake_amount": 1.0, "message": "ClawStation private challenge", "theme": "private", "status": "open", "expires_at": "2026-07-20T02:48:03.322381+00:00", "bet_id": null, "session_id": null, "created_at": "2026-07-19T02:48:06.42303+00:00", "updated_at": "2026-07-19T02:48:06.42303+00:00", "creator_lock_tx_id": null, "creator_lock_tx_hash": null, "opponent_lock_tx_id": null, "opponent_lock_tx_hash": null, "resolved_tx_hash": null, "winner_id": null, "screenshot_creator_url": null, "screenshot_opponent_url": null, "creator_score": null, "opponent_score": null, "ai_verified_at": null, "ai_winner_id": null, "dispute_reason": null, "dispute_raised_at": null, "admin_resolved_by": null, "admin_resolution_note": null, "creator_id": "62440a47-f4fc-4249-a627-46aaa2d039ef", "opponent_id": "cfa4a1b9-a785-4045-ac68-c2bd3fdefc07", "amount_usdc": 1.0, "game": "EA FC", "visibility": "private"}`

### 2026-07-19T02:48:20.434884+00:00 — challenge_accepted


### 2026-07-19T02:48:20.434914+00:00 — lock_creator_start


### 2026-07-19T02:48:38.460817+00:00 — lock_creator_FAIL

- **error**: `"USDC approve failed: {'code': -1, 'message': 'Resource not found'}"`
- **tb**: `"Traceback (most recent call last):\n  File \"<stdin>\", line 110, in main\n  File \"/Users/mac/sideQuest/sideQuest/.worktrees/clawstation-foundation/gaming/src/backend/services/clawstation_escrow.py\", line 199, in approve_and_create_match\n    raise EscrowError(f\"USDC approve failed: {approve_result.get('error')}\")\ngaming.src.backend.services.clawstation_escrow.EscrowError: USDC approve failed: {'code': -1, 'message': 'Resource not found'}\n"`

