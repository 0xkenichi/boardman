# Gaming Reorganization Report
## Summary
- Current focus is Social Quest + City Quest.
- `gaming/` is now the single home for paused Telegram bot gaming code and docs.
- Gaming vertical is paused, not deleted.
- Telegram bot gaming is first priority if bot work resumes; WhatsApp follows Telegram.
- Thin compatibility shims remain in `backend/` so active imports and route registration continue to resolve.

## Source Code Moved

- `backend/Dockerfile.bot` → `gaming/src/backend/Dockerfile.bot`
- `backend/Dockerfile.bot.simple` → `gaming/src/backend/Dockerfile.bot.simple`
- `backend/Dockerfile.telegram` → `gaming/src/backend/Dockerfile.telegram`
- `backend/api_proof_of_play.py` → `gaming/src/backend/api_proof_of_play.py`
- `backend/app_controller.py` → `gaming/src/backend/app_controller.py`
- `backend/betting_engine.py` → `gaming/src/backend/betting_engine.py`
- `backend/betting_engine_onchain.py` → `gaming/src/backend/betting_engine_onchain.py`
- `backend/blockchain_whatsapp_agent.py` → `gaming/src/backend/blockchain_whatsapp_agent.py`
- `backend/blockchain_whatsapp_commands.py` → `gaming/src/backend/blockchain_whatsapp_commands.py`
- `backend/bot/handlers.py` → `gaming/src/backend/bot/handlers.py`
- `backend/bot/keyboards.py` → `gaming/src/backend/bot/keyboards.py`
- `backend/bot/trust_safety_commands.py` → `gaming/src/backend/bot/trust_safety_commands.py`
- `backend/bot_monitor.py` → `gaming/src/backend/bot_monitor.py`
- `backend/bot_monitor_requirements.txt` → `gaming/src/backend/bot_monitor_requirements.txt`
- `backend/bot_service.py` → `gaming/src/backend/bot_service.py`
- `backend/bot_watchdog.py` → `gaming/src/backend/bot_watchdog.py`
- `backend/circle_test_api.py` → `gaming/src/backend/circle_test_api.py`
- `backend/load_test_bot.py` → `gaming/src/backend/load_test_bot.py`
- `backend/match_manager.py` → `gaming/src/backend/match_manager.py`
- `backend/psn_game_reader.py` → `gaming/src/backend/psn_game_reader.py`
- `backend/routes/gaming.py` → `gaming/src/backend/routes/gaming.py`
- `backend/score_verifier.py` → `gaming/src/backend/score_verifier.py`
- `backend/setup_circle_escrow.py` → `gaming/src/backend/setup_circle_escrow.py`
- `backend/setup_circle_final.py` → `gaming/src/backend/setup_circle_final.py`
- `backend/simulate_betting.py` → `gaming/src/backend/simulate_betting.py`
- `backend/start_bot.py` → `gaming/src/backend/start_bot.py`
- `backend/telegram_bot.py` → `gaming/src/backend/telegram_bot.py`
- `backend/telegram_handler.py` → `gaming/src/backend/telegram_handler.py`
- `backend/telegram_handler_v2.py` → `gaming/src/backend/telegram_handler_v2.py`
- `backend/telegram_notifier.py` → `gaming/src/backend/telegram_notifier.py`
- `backend/telegram_webhook.py` → `gaming/src/backend/telegram_webhook.py`
- `backend/test_bot_send.py` → `gaming/src/backend/test_bot_send.py`
- `backend/test_circle_wallet.py` → `gaming/src/backend/test_circle_wallet.py`
- `backend/whatsapp_blockchain_commands.py` → `gaming/src/backend/whatsapp_blockchain_commands.py`
- `backend/whatsapp_handler.py` → `gaming/src/backend/whatsapp_handler.py`
- `backend/xbox_game_reader.py` → `gaming/src/backend/xbox_game_reader.py`

## Documentation Moved

- `PROOF_OF_PLAY_SYSTEM.md` → `gaming/PROOF_OF_PLAY_SYSTEM.md`
- `docs/lite_papers/02_gaming_staking.md` → `gaming/docs/lite_papers/02_gaming_staking.md`
- `docs/api/BLOCKCHAIN_WHATSAPP_INTEGRATION.md` → `gaming/docs/api/BLOCKCHAIN_WHATSAPP_INTEGRATION.md`
- `docs/api/CIRCLE_ESCROW_SETUP.md` → `gaming/docs/api/CIRCLE_ESCROW_SETUP.md`
- `docs/api/CIRCLE_INTEGRATION_QUICK_START.md` → `gaming/docs/api/CIRCLE_INTEGRATION_QUICK_START.md`
- `docs/api/CIRCLE_READY.md` → `gaming/docs/api/CIRCLE_READY.md`
- `docs/api/GAME_COVERAGE.md` → `gaming/docs/api/GAME_COVERAGE.md`
- `docs/api/INTEGRATION_STEPS.md` → `gaming/docs/api/INTEGRATION_STEPS.md`
- `docs/architecture/BLOCKCHAIN_SECURITY_AUDIT.md` → `gaming/docs/architecture/BLOCKCHAIN_SECURITY_AUDIT.md`
- `docs/guides/BASE_SEPOLIA_TESTNET_SETUP.md` → `gaming/docs/guides/BASE_SEPOLIA_TESTNET_SETUP.md`
- `docs/guides/MATCH_TYPES_GUIDE.md` → `gaming/docs/guides/MATCH_TYPES_GUIDE.md`
- `docs/guides/TESTNET_LAUNCH.md` → `gaming/docs/guides/TESTNET_LAUNCH.md`
- `docs/guides/TESTNET_QUICK_REFERENCE.md` → `gaming/docs/guides/TESTNET_QUICK_REFERENCE.md`
- `docs/guides/TESTNET_READY.md` → `gaming/docs/guides/TESTNET_READY.md`

## Compatibility Shims Left In Backend

These files now re-export from `gaming/src/backend/...` to avoid breaking imports while the gaming vertical is paused.

- `backend/api_proof_of_play.py`
- `backend/app_controller.py`
- `backend/betting_engine.py`
- `backend/betting_engine_onchain.py`
- `backend/blockchain_whatsapp_agent.py`
- `backend/blockchain_whatsapp_commands.py`
- `backend/bot/handlers.py`
- `backend/bot/keyboards.py`
- `backend/bot/trust_safety_commands.py`
- `backend/bot_monitor.py`
- `backend/bot_service.py`
- `backend/bot_watchdog.py`
- `backend/circle_test_api.py`
- `backend/load_test_bot.py`
- `backend/match_manager.py`
- `backend/psn_game_reader.py`
- `backend/routes/gaming.py`
- `backend/score_verifier.py`
- `backend/setup_circle_escrow.py`
- `backend/setup_circle_final.py`
- `backend/simulate_betting.py`
- `backend/start_bot.py`
- `backend/telegram_bot.py`
- `backend/telegram_handler.py`
- `backend/telegram_handler_v2.py`
- `backend/telegram_notifier.py`
- `backend/telegram_webhook.py`
- `backend/test_bot_send.py`
- `backend/test_circle_wallet.py`
- `backend/whatsapp_blockchain_commands.py`
- `backend/whatsapp_handler.py`
- `backend/xbox_game_reader.py`

## Documentation Updated

- `PROJECT_MAP.md` now states Social Quest + City Quest are the focus and `gaming/` owns all paused Telegram bot gaming code/docs.
- `SIDEQUEST_COFOUNDER_DEEP_DIVE_REPORT.md` points moved gaming doc references at `gaming/` paths.
- `gaming/README.md` clarifies ownership of Telegram bot gaming, 1v1 staking, gaming quests, and console-style game sessions.

## Shared Or Risky To Move, Left In Place

These are gaming-adjacent or infrastructure-adjacent, but are shared with active Social Quest / City Quest flows, API route registration, wallet/database access, contracts, or package/runtime paths. They were not moved.

- `backend/api.py`
- `backend/api/__init__.py`
- `backend/api_blockchain_additions.py`
- `backend/blockchain_api_endpoints.py`
- `backend/blockchain_layer.py`
- `backend/circle_wallet_service.py`
- `backend/create_wallet_set.py`
- `backend/custodial_wallet.py`
- `backend/db_layer.py`
- `backend/db_layer_blockchain.py`
- `backend/services/circle_vault.py`
- `backend/wallet_service.py`
- `contracts/`
- `supabase/migrations/001_blockchain_schema.sql`
- `supabase/migrations/002_match_wallet_schema.sql`
- `supabase/migrations/006_proof_of_play_schema.sql`

## Verification Notes

- Checked moved files exist under `gaming/`.
- Patched moved internal imports to use `gaming.src.backend...` where needed.
- Kept backend shims for previously imported module paths.
- Ran `py_compile` on backend shims and moved gaming modules successfully.
- Runtime import sanity check passes for core shims including `backend.match_manager`; `backend.routes.gaming` still raises the existing Python 3.9-style `type | None` issue under the current interpreter. This was not introduced by the move.
- Did not run the full app test suite because this was a repository reorganization and the repo already has extensive unrelated dirty state.

## Existing Dirty State Not From This Reorg

The repo already had extensive unrelated dirty state before this work, including `.venv12` deletions, backend/frontend changes, Android files, and several modified docs. This reorganization avoided intentionally changing unrelated areas.
