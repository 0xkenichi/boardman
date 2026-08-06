"""
Fiat top-up flow (Naira / USD bank → USDC play credit).

User:
  Get money → Top up with Naira / USD
  → enter amount → see quote after fee + bank details + ref
  → confirm → send payment → paste txn id or photo proof
  → ops credits USDC manually

Admin:
  /topups — pending list
  /credit_topup RM-XXXX [optional note]
  /reject_topup RM-XXXX [reason]
"""
from __future__ import annotations

import logging
from decimal import Decimal
from html import escape

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from gaming.src.backend.services.fiat_topup import (
    bank_configured,
    commercial_rate,
    create_topup,
    fee_floor,
    format_bank_block,
    format_quote_html,
    get_topup,
    list_topups,
    parse_ngn_amount,
    parse_usd_amount,
    quote_from_ngn,
    quote_from_usd,
    update_topup,
)
from gaming.src.backend.services.safety import admin_telegram_ids, is_admin
from gaming.src.bot.keyboards import (
    fiat_amount_presets_menu,
    fiat_confirm_menu,
    fiat_proof_menu,
    get_money_menu,
    paystack_pay_menu,
    wallet_menu,
)
from gaming.src.bot.utils.db import get_or_create_profile
from gaming.src.bot.utils.notify import notify_user
from gaming.src.bot.utils.text import h

logger = logging.getLogger(__name__)
router = Router(name="fiat_topup")


class FiatTopupWizard(StatesGroup):
    waiting_amount = State()
    waiting_proof = State()
    waiting_paystack_amount = State()


# ── Entry / chooser ──────────────────────────────────────────────────────────


@router.callback_query(F.data == "ui:get_money")
@router.callback_query(F.data == "ui:topup:menu")
async def ui_get_money_menu(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    rate = commercial_rate()
    from gaming.src.backend.services.kobox_partner import get_money_intro_html

    await callback.message.answer(
        get_money_intro_html(float(rate)),
        parse_mode=ParseMode.HTML,
        reply_markup=get_money_menu(),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "ui:topup:kobox")
async def ui_topup_kobox_info(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Explain Kobox path when no referral URL is configured yet."""
    await state.clear()
    await callback.answer()
    from gaming.src.backend.services.kobox_partner import (
        kobox_name,
        kobox_referral_url,
        onramp_copy_html,
    )

    name = kobox_name()
    url = kobox_referral_url()
    play = ""
    user = callback.from_user
    if user:
        try:
            profile = await get_or_create_profile(user)
            from gaming.src.backend.services.clawstation_circle import ensure_user_wallet

            w = await ensure_user_wallet(profile["id"], chain_id="arc")
            play = w.get("address") or ""
        except Exception:
            pass

    lines = [
        f"⭐ <b>{name} — self-serve funding</b>\n",
        onramp_copy_html(),
        "",
        "<b>Steps</b>",
        f"1. Install / open {name}" + (f" → {url}" if url else ""),
        "2. Fund with Naira (or use balance you already have)",
        "3. Swap to USDC inside the app",
        "4. Send USDC to your <b>Boardman play address</b>:",
    ]
    if play:
        lines.append(f"<code>{h(play)}</code>")
    else:
        lines.append("(open Wallet after /start to copy your address)")
    lines.extend(
        [
            "",
            "5. Back here → Wallet → Refresh",
            "",
            f"Don't want {name}? Use <b>We'll do it — pay Naira</b> and we credit you.",
        ]
    )
    kb = get_money_menu()
    await callback.message.answer(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "ui:topup:ngn")
async def ui_topup_ngn_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not bank_configured("ngn"):
        await callback.message.answer(
            "⚠️ Naira top-up is not configured yet. Try crypto deposit or contact support.",
            reply_markup=get_money_menu(),
        )
        return
    await state.set_state(FiatTopupWizard.waiting_amount)
    await state.update_data(fiat_currency="ngn")
    rate = commercial_rate()
    floor = fee_floor()
    await callback.message.answer(
        "🇳🇬 <b>Top up with Naira</b>\n\n"
        f"Today’s commercial rate: <b>₦{rate:,.0f}</b> per $1\n"
        f"Fee: max(<b>${floor}</b>, 5% of amount)\n\n"
        "How much <b>Naira</b> will you send?\n"
        "Type an amount (e.g. <code>10000</code> or <code>10k</code>) "
        "or pick a preset.",
        parse_mode=ParseMode.HTML,
        reply_markup=fiat_amount_presets_menu("ngn"),
    )


@router.callback_query(F.data == "ui:topup:usd")
async def ui_topup_usd_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not bank_configured("usd"):
        await callback.message.answer(
            "⚠️ USD bank top-up is not configured yet. Try Naira or crypto.",
            reply_markup=get_money_menu(),
        )
        return
    await state.set_state(FiatTopupWizard.waiting_amount)
    await state.update_data(fiat_currency="usd")
    floor = fee_floor()
    await callback.message.answer(
        "🇺🇸 <b>Top up with USD (bank)</b>\n\n"
        f"Fee: max(<b>${floor}</b>, 5% of amount)\n\n"
        "How much <b>USD</b> will you send?\n"
        "Type an amount (e.g. <code>20</code>) or pick a preset.",
        parse_mode=ParseMode.HTML,
        reply_markup=fiat_amount_presets_menu("usd"),
    )


@router.callback_query(F.data.startswith("ui:topup:amt:"))
async def ui_topup_amt_preset(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Preset: ui:topup:amt:ngn:10000 or ui:topup:amt:usd:20"""
    await callback.answer()
    parts = (callback.data or "").split(":")
    # ui topup amt ngn 10000
    if len(parts) < 5:
        await callback.message.answer("Invalid preset.", reply_markup=get_money_menu())
        return
    currency = parts[3].lower()
    raw = parts[4]
    cur_state = await state.get_state()
    if cur_state == FiatTopupWizard.waiting_paystack_amount.state:
        await _start_paystack_for_amount(
            callback.message, state, raw, user=callback.from_user
        )
        return
    await state.update_data(fiat_currency=currency)
    await state.set_state(FiatTopupWizard.waiting_amount)
    await _handle_amount(callback.message, state, raw, currency, user=callback.from_user)


@router.message(FiatTopupWizard.waiting_amount, F.text)
async def ui_topup_amount_text(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    currency = (data.get("fiat_currency") or "ngn").lower()
    await _handle_amount(message, state, message.text or "", currency, user=message.from_user)


async def _handle_amount(
    message: types.Message,
    state: FSMContext,
    raw: str,
    currency: str,
    user: types.User | None,
) -> None:
    if not user:
        return
    try:
        if currency == "usd":
            amount = parse_usd_amount(raw)
            quote = quote_from_usd(amount)
        else:
            amount = parse_ngn_amount(raw)
            quote = quote_from_ngn(amount)
    except ValueError as exc:
        await message.answer(
            f"❌ {escape(str(exc))}\n\nTry again or pick a preset.",
            parse_mode=ParseMode.HTML,
            reply_markup=fiat_amount_presets_menu(currency),
        )
        return

    await state.update_data(
        fiat_currency=currency,
        quote=quote.as_public_dict(),
        amount_raw=str(amount),
    )
    body = format_quote_html(quote, currency=currency)
    await message.answer(
        f"💵 <b>Quote</b>\n\n{body}\n\n"
        "If this looks right, tap <b>Continue</b> to get the account "
        "and your payment reference.",
        parse_mode=ParseMode.HTML,
        reply_markup=fiat_confirm_menu(),
    )


@router.callback_query(F.data == "ui:topup:confirm", FiatTopupWizard.waiting_amount)
@router.callback_query(F.data == "ui:topup:confirm")
async def ui_topup_confirm(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    user = callback.from_user
    if not user:
        return
    data = await state.get_data()
    currency = (data.get("fiat_currency") or "ngn").lower()
    q = data.get("quote") or {}
    if not q:
        await callback.message.answer(
            "Start over — pick Naira or USD.",
            reply_markup=get_money_menu(),
        )
        await state.clear()
        return

    profile = await get_or_create_profile(user)
    play_addr = ""
    try:
        from gaming.src.backend.services.clawstation_circle import ensure_user_wallet

        wallet = await ensure_user_wallet(profile["id"], chain_id="arc")
        play_addr = wallet.get("address") or ""
    except Exception:
        logger.exception("[FiatTopup] wallet lookup failed")

    try:
        if currency == "usd":
            amount = parse_usd_amount(str(data.get("amount_raw") or q.get("gross_usd")))
            quote = quote_from_usd(amount)
            top = create_topup(
                profile_id=profile["id"],
                telegram_id=user.id,
                display_name=user.full_name or user.username or "",
                quote=quote,
                play_address=play_addr,
                currency="usd",
                amount_fiat=amount,
            )
        else:
            amount = parse_ngn_amount(str(data.get("amount_raw") or q.get("amount_ngn")))
            quote = quote_from_ngn(amount)
            top = create_topup(
                profile_id=profile["id"],
                telegram_id=user.id,
                display_name=user.full_name or user.username or "",
                quote=quote,
                play_address=play_addr,
                currency="ngn",
                amount_fiat=amount,
            )
    except Exception as exc:
        logger.exception("[FiatTopup] create failed")
        await callback.message.answer(
            f"❌ Could not create top-up: {h(exc)}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_money_menu(),
        )
        await state.clear()
        return

    await state.set_state(FiatTopupWizard.waiting_proof)
    await state.update_data(topup_ref=top.ref, fiat_currency=currency)

    quote_html = format_quote_html(quote, ref=top.ref, currency=currency)
    bank = format_bank_block(currency)
    await callback.message.answer(
        f"✅ <b>Top-up created</b>\n\n"
        f"{quote_html}\n\n"
        f"<b>Send payment to:</b>\n{bank}\n\n"
        f"1. Transfer the exact amount\n"
        f"2. Use narration/ref <code>{h(top.ref)}</code> if possible\n"
        f"3. Reply here with your <b>transaction ID</b> or a <b>receipt photo</b>\n\n"
        f"We credit <b>${quote.credit_usdc:,.2f} USDC</b> after confirmation "
        f"(usually within ops hours).",
        parse_mode=ParseMode.HTML,
        reply_markup=fiat_proof_menu(top.ref),
    )

    await _notify_admins_new_topup(top.ref)


@router.message(FiatTopupWizard.waiting_proof, F.photo)
@router.message(FiatTopupWizard.waiting_proof, F.document)
@router.message(FiatTopupWizard.waiting_proof, F.text)
async def ui_topup_proof(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    ref = (data.get("topup_ref") or "").strip().upper()
    if not ref:
        # allow user to paste "RM-XXXX proof..."
        text = (message.text or "").strip()
        if text.upper().startswith("RM-"):
            ref = text.split()[0].upper()
        else:
            await message.answer(
                "No open top-up. Start again from <b>Get money</b>.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_money_menu(),
            )
            await state.clear()
            return

    row = get_topup(ref)
    if not row:
        await message.answer(
            f"Unknown ref <code>{h(ref)}</code>. Start a new top-up.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_money_menu(),
        )
        await state.clear()
        return

    if row.get("status") in ("credited", "rejected", "cancelled"):
        await message.answer(
            f"This top-up is already <b>{h(row.get('status'))}</b>.",
            parse_mode=ParseMode.HTML,
            reply_markup=wallet_menu(),
        )
        await state.clear()
        return

    proof_text = (message.text or message.caption or "").strip()
    proof_file_id = ""
    if message.photo:
        proof_file_id = message.photo[-1].file_id
        if not proof_text:
            proof_text = "(receipt photo)"
    elif message.document:
        proof_file_id = message.document.file_id
        if not proof_text:
            proof_text = f"(file: {message.document.file_name or 'document'})"

    if not proof_text and not proof_file_id:
        await message.answer(
            "Send a transaction ID (text) or a receipt screenshot.",
            reply_markup=fiat_proof_menu(ref),
        )
        return

    updated = update_topup(
        ref,
        status="proof_submitted",
        proof_text=proof_text[:2000],
        proof_file_id=proof_file_id,
    )
    await state.clear()

    credit = float((updated or row).get("credit_usdc") or 0)
    await message.answer(
        f"📨 <b>Proof received</b> for <code>{h(ref)}</code>\n\n"
        f"We’ll credit <b>${credit:,.2f} USDC</b> after we confirm the payment.\n"
        f"You’ll get a message when it’s done.",
        parse_mode=ParseMode.HTML,
        reply_markup=wallet_menu(),
    )
    await _notify_admins_proof(ref, proof_text, message)


@router.callback_query(F.data.startswith("ui:topup:cancel:"))
async def ui_topup_cancel(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    ref = (callback.data or "").split(":")[-1].upper()
    row = get_topup(ref)
    if row and row.get("status") in ("awaiting_payment", "proof_submitted"):
        update_topup(ref, status="cancelled")
    await state.clear()
    await callback.message.answer("Top-up cancelled.", reply_markup=get_money_menu())


@router.callback_query(F.data == "ui:topup:cancel_wizard")
async def ui_topup_cancel_wizard(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.answer("Cancelled.", reply_markup=get_money_menu())


# ── Paystack path ────────────────────────────────────────────────────────────


@router.callback_query(F.data == "ui:topup:paystack")
async def ui_topup_paystack_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    from gaming.src.backend.services.paystack import paystack_configured, sla_minutes

    if not paystack_configured():
        await callback.message.answer(
            "Paystack is not configured yet. Use bank transfer or Kobox.",
            reply_markup=get_money_menu(),
        )
        return
    await state.set_state(FiatTopupWizard.waiting_paystack_amount)
    await state.update_data(fiat_currency="ngn", provider="paystack")
    rate = commercial_rate()
    floor = fee_floor()
    sla = sla_minutes()
    await callback.message.answer(
        "⚡ <b>Pay with Paystack</b>\n\n"
        f"Rate: <b>₦{rate:,.0f}</b> per $1 · fee max(<b>${floor}</b>, 5%)\n"
        f"After Paystack confirms ₦, we credit USDC "
        f"(usually within <b>~{sla} min</b> while ops are online).\n\n"
        "<b>How USDC credit works</b>\n"
        "1. You pay ₦ → Paystack settles Naira to our bank\n"
        "2. We send USDC from a <b>pre-funded float</b> (Kobox/treasury)\n"
        "3. Later we convert settled ₦ → refill the float\n\n"
        "So you are <b>not</b> waiting for FX in real time — "
        "as long as we keep USDC ready.\n\n"
        "How much <b>Naira</b> will you pay?\n"
        "Type an amount (e.g. <code>10000</code>) or pick a preset.",
        parse_mode=ParseMode.HTML,
        reply_markup=fiat_amount_presets_menu("ngn"),
    )


@router.message(FiatTopupWizard.waiting_paystack_amount, F.text)
async def ui_paystack_amount_text(message: types.Message, state: FSMContext) -> None:
    await _start_paystack_for_amount(message, state, message.text or "", user=message.from_user)


async def _start_paystack_for_amount(
    message: types.Message,
    state: FSMContext,
    raw: str,
    user: types.User | None,
) -> None:
    if not user:
        return
    from gaming.src.backend.services.paystack import (
        initialize_transaction,
        paystack_configured,
        sla_minutes,
    )

    if not paystack_configured():
        await message.answer("Paystack not configured.", reply_markup=get_money_menu())
        await state.clear()
        return
    try:
        amount = parse_ngn_amount(raw)
        quote = quote_from_ngn(amount)
    except ValueError as exc:
        await message.answer(
            f"❌ {escape(str(exc))}\n\nTry again or pick a preset.",
            parse_mode=ParseMode.HTML,
            reply_markup=fiat_amount_presets_menu("ngn"),
        )
        return

    profile = await get_or_create_profile(user)
    play_addr = ""
    try:
        from gaming.src.backend.services.clawstation_circle import ensure_user_wallet

        wallet = await ensure_user_wallet(profile["id"], chain_id="arc")
        play_addr = wallet.get("address") or ""
    except Exception:
        logger.exception("[Paystack] wallet lookup failed")

    # Allocate top-up first to get RM- ref, then init Paystack with that reference
    try:
        top = create_topup(
            profile_id=profile["id"],
            telegram_id=user.id,
            display_name=user.full_name or user.username or "",
            quote=quote,
            play_address=play_addr,
            currency="ngn",
            amount_fiat=amount,
            provider="paystack",
        )
        import os

        email = (
            (os.getenv("PAYSTACK_DEFAULT_EMAIL") or "").strip()
            or f"tg{user.id}@boardman.playingsidequest.fun"
        )
        # Use a Paystack-safe reference (alphanumeric)
        ps_ref = top.ref.replace("-", "")
        init = initialize_transaction(
            email=email,
            amount_ngn=amount,
            reference=ps_ref,
            metadata={
                "boardman_ref": top.ref,
                "profile_id": profile["id"],
                "telegram_id": str(user.id),
                "credit_usdc": str(quote.credit_usdc),
                "play_address": play_addr,
            },
        )
        update_topup(
            top.ref,
            paystack_reference=ps_ref,
            paystack_access_code=init.get("access_code") or "",
            authorization_url=init.get("authorization_url") or "",
            provider="paystack",
        )
        auth_url = init.get("authorization_url") or ""
    except Exception as exc:
        logger.exception("[Paystack] init failed")
        await message.answer(
            f"❌ Could not start Paystack: {h(exc)}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_money_menu(),
        )
        await state.clear()
        return

    await state.clear()
    quote_html = format_quote_html(quote, ref=top.ref, currency="ngn")
    sla = sla_minutes()
    await message.answer(
        f"⚡ <b>Paystack top-up ready</b>\n\n"
        f"{quote_html}\n\n"
        f"1. Tap <b>Open Paystack &amp; pay</b>\n"
        f"2. Complete payment\n"
        f"3. Tap <b>I've paid — check status</b>\n\n"
        f"After ₦ is confirmed, we credit <b>${quote.credit_usdc:,.2f} USDC</b> "
        f"from our float (target ~{sla} min during ops hours).",
        parse_mode=ParseMode.HTML,
        reply_markup=paystack_pay_menu(top.ref, auth_url),
        disable_web_page_preview=True,
    )
    await _notify_admins_new_topup(top.ref)


@router.callback_query(F.data.startswith("ui:topup:paystack:check:"))
async def ui_paystack_check(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Checking Paystack…")
    ref = (callback.data or "").split(":")[-1].upper()
    row = get_topup(ref)
    if not row:
        await callback.message.answer("Unknown top-up.", reply_markup=get_money_menu())
        return
    if row.get("status") == "credited":
        await callback.message.answer(
            f"✅ Already credited ${float(row.get('credit_usdc') or 0):,.2f}.",
            reply_markup=wallet_menu(),
        )
        return
    if row.get("status") == "paystack_paid":
        await callback.message.answer(
            f"✅ Payment confirmed. USDC credit in progress "
            f"(${float(row.get('credit_usdc') or 0):,.2f}).\n"
            f"Admin will finish send if not automatic yet.",
            reply_markup=wallet_menu(),
        )
        return

    from gaming.src.backend.services.paystack import verify_transaction, sla_minutes

    ps_ref = row.get("paystack_reference") or ref.replace("-", "")
    try:
        result = verify_transaction(ps_ref)
    except Exception as exc:
        await callback.message.answer(
            f"❌ Could not verify: {h(exc)}\nTry again in a minute.",
            parse_mode=ParseMode.HTML,
            reply_markup=paystack_pay_menu(ref, row.get("authorization_url") or ""),
        )
        return

    if not result.get("paid"):
        await callback.message.answer(
            f"⏳ Not paid yet (status: <code>{h(result.get('status') or 'unknown')}</code>).\n"
            f"Finish Paystack checkout, then tap check again.",
            parse_mode=ParseMode.HTML,
            reply_markup=paystack_pay_menu(ref, row.get("authorization_url") or ""),
        )
        return

    # Confirm amount roughly matches
    paid_ngn = float(result.get("amount_ngn") or 0)
    expected = float(row.get("amount_ngn") or row.get("amount_fiat") or 0)
    if expected and abs(paid_ngn - expected) > 1.0:
        update_topup(
            ref,
            status="proof_submitted",
            proof_text=f"paystack_paid_amount_mismatch paid={paid_ngn} expected={expected}",
            admin_note="amount_mismatch",
        )
        await callback.message.answer(
            f"⚠️ Paid ₦{paid_ngn:,.2f} but quote was ₦{expected:,.0f}.\n"
            f"Support will adjust credit. Ref <code>{h(ref)}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=wallet_menu(),
        )
        await _notify_admins_proof(ref, f"Paystack amount mismatch {paid_ngn} vs {expected}", callback.message)
        return

    update_topup(
        ref,
        status="paystack_paid",
        proof_text=f"paystack success channel={result.get('channel')} paid_at={result.get('paid_at')}",
    )
    credit = float(row.get("credit_usdc") or 0)
    sla = sla_minutes()
    await callback.message.answer(
        f"✅ <b>Payment confirmed</b>\n\n"
        f"Ref <code>{h(ref)}</code>\n"
        f"Paid: <b>₦{paid_ngn:,.2f}</b>\n"
        f"You get: <b>${credit:,.2f} USDC</b>\n\n"
        f"We’re sending USDC to your play wallet "
        f"(target ~{sla} min while ops are online).\n"
        f"You’ll get a message when it’s done — Wallet → Refresh.",
        parse_mode=ParseMode.HTML,
        reply_markup=wallet_menu(),
    )
    # Re-notify admins to send USDC
    from gaming.src.backend.services.safety import admin_telegram_ids
    from gaming.src.bot.utils.notify import _ensure_bot

    bot = _ensure_bot()
    text = (
        f"⚡ <b>Paystack PAID</b> <code>{escape(ref)}</code>\n"
        f"₦{paid_ngn:,.2f} → credit <b>${credit:,.2f}</b> USDC\n"
        f"Play: <code>{escape(str(row.get('play_address') or '—'))}</code>\n"
        f"User tg: {row.get('telegram_id')}\n"
        f"1) Send USDC from float/Kobox\n"
        f"2) /credit_topup {escape(ref)}"
    )
    if bot:
        for aid in admin_telegram_ids():
            try:
                await bot.send_message(aid, text, parse_mode=ParseMode.HTML)
            except Exception:
                pass


# ── Crypto path (existing faucet / address) ──────────────────────────────────


@router.callback_query(F.data == "ui:topup:crypto")
async def ui_topup_crypto(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Delegate to existing Get USDC / deposit address flow."""
    await state.clear()
    # Re-use simple_ui handler logic via same callback shape
    from gaming.src.bot.handlers.simple_ui import ui_get_usdc_crypto

    await ui_get_usdc_crypto(callback)


# ── Admin ────────────────────────────────────────────────────────────────────


@router.message(Command("topups"))
async def cmd_topups(message: types.Message) -> None:
    user = message.from_user
    if not user or not is_admin(user.id):
        await message.answer("Admin only.")
        return
    pending = list_topups(status="proof_submitted", limit=15)
    paystack_paid = list_topups(status="paystack_paid", limit=15)
    waiting = list_topups(status="awaiting_payment", limit=10)
    lines = ["📋 <b>Fiat top-ups</b>\n"]
    if not pending and not waiting and not paystack_paid:
        lines.append("No open top-ups.")
    if paystack_paid:
        lines.append("<b>Paystack paid — send USDC now:</b>")
        for r in paystack_paid:
            lines.append(_admin_line(r))
    if pending:
        lines.append("<b>Proof submitted (credit these):</b>")
        for r in pending:
            lines.append(_admin_line(r))
    if waiting:
        lines.append("\n<b>Awaiting payment:</b>")
        for r in waiting:
            lines.append(_admin_line(r))
    lines.append(
        "\n<code>/credit_topup RM-XXXX</code> after you send USDC\n"
        "<code>/reject_topup RM-XXXX reason</code>"
    )
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


@router.message(Command("credit_topup"))
async def cmd_credit_topup(message: types.Message) -> None:
    user = message.from_user
    if not user or not is_admin(user.id):
        await message.answer("Admin only.")
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Usage: /credit_topup RM-XXXX [note]")
        return
    ref = parts[1].strip().upper()
    note = parts[2].strip() if len(parts) > 2 else f"credited_by:{user.id}"
    row = get_topup(ref)
    if not row:
        await message.answer(f"Unknown ref {ref}")
        return
    if row.get("status") == "credited":
        await message.answer(f"{ref} already credited.")
        return

    updated = update_topup(ref, status="credited", admin_note=note[:500])
    credit = float((updated or row).get("credit_usdc") or 0)
    tid = int(row.get("telegram_id") or 0)
    pid = row.get("profile_id") or ""

    await message.answer(
        f"✅ Marked <code>{h(ref)}</code> credited for ${credit:,.2f}.\n"
        f"Send ${credit:,.2f} USDC to play wallet if you haven’t yet.\n"
        f"Address: <code>{h(row.get('play_address') or '—')}</code>",
        parse_mode=ParseMode.HTML,
    )

    if tid:
        try:
            await notify_user(
                pid or str(tid),
                f"✅ <b>Top-up credited</b>\n\n"
                f"Ref <code>{h(ref)}</code>\n"
                f"<b>${credit:,.2f} USDC</b> should be in your play wallet.\n"
                f"Open <b>Wallet → Refresh</b> if you don’t see it yet.",
            )
        except Exception:
            # fallback: bot message by telegram id
            try:
                await message.bot.send_message(
                    tid,
                    f"✅ <b>Top-up credited</b>\n\n"
                    f"Ref <code>{escape(ref)}</code>\n"
                    f"<b>${credit:,.2f} USDC</b> — check Wallet → Refresh.",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                logger.exception("[FiatTopup] notify user failed ref=%s", ref)


@router.message(Command("reject_topup"))
async def cmd_reject_topup(message: types.Message) -> None:
    user = message.from_user
    if not user or not is_admin(user.id):
        await message.answer("Admin only.")
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Usage: /reject_topup RM-XXXX [reason]")
        return
    ref = parts[1].strip().upper()
    reason = parts[2].strip() if len(parts) > 2 else "rejected"
    row = get_topup(ref)
    if not row:
        await message.answer(f"Unknown ref {ref}")
        return
    update_topup(ref, status="rejected", admin_note=reason[:500])
    await message.answer(f"Rejected {ref}: {escape(reason)}", parse_mode=ParseMode.HTML)
    tid = int(row.get("telegram_id") or 0)
    if tid:
        try:
            await message.bot.send_message(
                tid,
                f"❌ Top-up <code>{escape(ref)}</code> was not credited.\n"
                f"Reason: {escape(reason)}\n"
                f"Contact support if this is a mistake.",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass


def _admin_line(r: dict) -> str:
    cur = (r.get("currency") or "ngn").upper()
    if cur == "USD":
        sent = f"${float(r.get('amount_fiat') or r.get('gross_usd') or 0):,.2f}"
    else:
        sent = f"₦{float(r.get('amount_ngn') or r.get('amount_fiat') or 0):,.0f}"
    prov = r.get("provider") or "bank"
    return (
        f"• <code>{h(r.get('ref'))}</code> "
        f"[{h(prov)}] {h(r.get('display_name') or '')} · {sent} → "
        f"<b>${float(r.get('credit_usdc') or 0):,.2f}</b> · "
        f"{h(r.get('status'))}"
    )


async def _notify_admins_new_topup(ref: str) -> None:
    row = get_topup(ref)
    if not row:
        return
    text = (
        f"🆕 Fiat top-up <code>{escape(ref)}</code>\n"
        f"{escape(str(row.get('display_name') or ''))} "
        f"(tg {row.get('telegram_id')})\n"
        f"Credit due: <b>${float(row.get('credit_usdc') or 0):,.2f}</b>\n"
        f"Status: awaiting payment"
    )
    await _blast_admins(text)


async def _notify_admins_proof(ref: str, proof_text: str, message: types.Message) -> None:
    row = get_topup(ref) or {}
    text = (
        f"📨 Proof for <code>{escape(ref)}</code>\n"
        f"{escape(str(row.get('display_name') or ''))}\n"
        f"Pay → credit <b>${float(row.get('credit_usdc') or 0):,.2f}</b> USDC\n"
        f"Play: <code>{escape(str(row.get('play_address') or '—'))}</code>\n"
        f"Proof: {escape((proof_text or '')[:300])}\n"
        f"/credit_topup {escape(ref)}"
    )
    await _blast_admins(text)
    # Forward photo to admins if present
    if message.photo:
        for aid in admin_telegram_ids():
            try:
                await message.bot.send_photo(
                    aid,
                    message.photo[-1].file_id,
                    caption=f"Receipt {ref}",
                )
            except Exception:
                pass


async def _blast_admins(text: str) -> None:
    from gaming.src.bot.utils.notify import _ensure_bot

    bot = _ensure_bot()
    if not bot:
        return
    for aid in admin_telegram_ids():
        try:
            await bot.send_message(aid, text, parse_mode=ParseMode.HTML)
        except Exception:
            logger.warning("[FiatTopup] admin notify failed id=%s", aid)
