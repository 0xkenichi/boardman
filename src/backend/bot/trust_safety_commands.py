# ─── TRUST & SAFETY BOT COMMANDS ──────────────────────────────────────────────────

async def cmd_report(message: types.Message):
    """Report a user: /report <user_id> <reason> [description]"""
    parts = message.text.split(maxsplit=3)
    if len(parts) < 3:
        await send(message.bot, message.chat.id,
            "Usage: /report <user_id> <reason> [description]\n"
            "Reasons: spam, harassment, hate_speech, fake_account, cheating, "
            "inappropriate_content, scam, violence, underage, other")
        return
    target_id = parts[1]
    reason = parts[2]
    description = parts[3] if len(parts) > 3 else None
    p = await get_profile(message.from_user)
    if not p:
        await send(message.bot, message.chat.id, "Profile not found.")
        return
    result = await submit_report(
        reporter_id=p["id"], target_type="user",
        reason=reason, target_user_id=target_id,
        description=description,
    )
    await send(message.bot, message.chat.id,
        "{} {}".format("✅" if result.get('success') else "❌",
                       result.get('message', result.get('error', 'Unknown'))))


async def cmd_block(message: types.Message):
    """Block a user: /block <user_id> [mute]"""
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await send(message.bot, message.chat.id, "Usage: /block <user_id> [mute]")
        return
    target_id = parts[1]
    mute_only = len(parts) > 2 and parts[2].lower() == "mute"
    p = await get_profile(message.from_user)
    if not p:
        await send(message.bot, message.chat.id, "Profile not found.")
        return
    result = await block_user(blocker_id=p["id"], blocked_id=target_id, mute_only=mute_only)
    action = "muted" if mute_only else "blocked"
    await send(message.bot, message.chat.id,
        "{} User {}: {}".format("✅" if result.get('success') else "❌",
                                action, result.get('action', result.get('error', ''))))


async def cmd_unblock(message: types.Message):
    """Unblock a user: /unblock <user_id>"""
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await send(message.bot, message.chat.id, "Usage: /unblock <user_id>")
        return
    target_id = parts[1]
    p = await get_profile(message.from_user)
    if not p:
        await send(message.bot, message.chat.id, "Profile not found.")
        return
    result = await unblock_user(blocker_id=p["id"], blocked_id=target_id)
    await send(message.bot, message.chat.id,
        "{} User unblocked.".format("✅" if result.get('success') else "❌"))


async def cmd_sos(message: types.Message):
    """Trigger SOS: /sos [message]"""
    parts = message.text.split(maxsplit=1)
    desc = parts[1] if len(parts) > 1 else None
    p = await get_profile(message.from_user)
    if not p:
        await send(message.bot, message.chat.id, "Profile not found.")
        return
    result = await trigger_sos(profile_id=p["id"], message=desc)
    await send(message.bot, message.chat.id,
        "{} {}".format("✅" if result.get('success') else "❌",
                       result.get('message', result.get('error', ''))))


async def cmd_tos(message: types.Message):
    """Accept ToS: /tos [version]"""
    parts = message.text.split(maxsplit=1)
    version = parts[1] if len(parts) > 1 else "1.0"
    p = await get_profile(message.from_user)
    if not p:
        await send(message.bot, message.chat.id, "Profile not found.")
        return
    result = await accept_tos(profile_id=p["id"], version=version)
    msg = "Terms accepted (v{}).".format(version) if result.get('success') else result.get('error', 'Failed')
    icon = "✅" if result.get('success') else "❌"
    await send(message.bot, message.chat.id, "{} {}".format(icon, msg))


async def cmd_age_verify(message: types.Message):
    """Verify age: /verify_age YYYY-MM-DD"""
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await send(message.bot, message.chat.id, "Usage: /verify_age YYYY-MM-DD")
        return
    dob = parts[1]
    p = await get_profile(message.from_user)
    if not p:
        await send(message.bot, message.chat.id, "Profile not found.")
        return
    result = await verify_age(profile_id=p["id"], date_of_birth=dob)
    await send(message.bot, message.chat.id,
        "{} {}".format("✅" if result.get('success') else "❌",
                       result.get('message', result.get('error', ''))))


async def cmd_emergency_contact(message: types.Message):
    """Add emergency contact: /emergency <name> <phone> [relationship]"""
    parts = message.text.split(maxsplit=3)
    if len(parts) < 3:
        await send(message.bot, message.chat.id,
            "Usage: /emergency <name> <phone> [relationship]")
        return
    name = parts[1]
    phone = parts[2]
    relationship = parts[3] if len(parts) > 3 else None
    p = await get_profile(message.from_user)
    if not p:
        await send(message.bot, message.chat.id, "Profile not found.")
        return
    result = await add_emergency_contact(
        profile_id=p["id"], name=name, phone=phone,
        relationship=relationship,
    )
    await send(message.bot, message.chat.id,
        "{} {}".format("✅" if result.get('success') else "❌",
                       result.get('message', result.get('error', ''))))


async def cmd_report_noshow(message: types.Message):
    """Report no-show: /noshow <reported_id> <match_id> [description]"""
    parts = message.text.split(maxsplit=3)
    if len(parts) < 3:
        await send(message.bot, message.chat.id,
            "Usage: /noshow <reported_id> <match_id> [description]")
        return
    reported_id = parts[1]
    match_id = parts[2]
    description = parts[3] if len(parts) > 3 else None
    p = await get_profile(message.from_user)
    if not p:
        await send(message.bot, message.chat.id, "Profile not found.")
        return
    result = await report_no_show(
        reporter_id=p["id"], reported_id=reported_id,
        match_id=match_id, description=description,
    )
    await send(message.bot, message.chat.id,
        "{} {}".format("✅" if result.get('success') else "❌",
                       result.get('message', result.get('error', ''))))