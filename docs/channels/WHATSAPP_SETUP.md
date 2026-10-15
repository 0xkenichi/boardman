# WhatsApp setup: the founder's click-path

Status: written 2026-10-15 for Phase 0 of `docs/channels/CHANNELS_DESIGN.md`. The code runs against a fake WhatsApp in tests; nothing here has been tried on a live Meta account yet.

**[?]** marks a Meta screen name, limit or rule taken from memory of Meta's documentation, not checked on a live account. Meta renames menus often: if a label differs, look for the closest match and tell engineering so this page gets fixed.

What you end up with, and where each value goes:

| You get | Env var on the API server | Secret? |
|---|---|---|
| Phone number ID | `WHATSAPP_PHONE_NUMBER_ID` | no |
| WhatsApp Business Account ID | (keep in the password manager; not read by the code yet) | no |
| App secret | `WHATSAPP_APP_SECRET` | **yes** |
| Permanent system-user token | `WHATSAPP_ACCESS_TOKEN` | **yes** |
| Verify token (you make it up) | `WHATSAPP_VERIFY_TOKEN` | **yes** |
| The +234 number, digits only | `WHATSAPP_DISPLAY_NUMBER` | no |

Then `WHATSAPP_ENABLED=1` and `CHANNELS_CORE_FLOWS_WHATSAPP=all` (see `docs/RUNBOOK.md`, "Chat channels").

Plan 1 to 4 weeks of calendar time for verification and template review, in parallel with engineering.

---

## 0. Before you start

- A Facebook account for yourself, with two-factor authentication on.
- The legal entity's documents: CAC certificate of incorporation, and a utility bill or bank statement with the registered address **[?]** (Meta accepts several document types; have both ready).
- The website `https://boardman.playingsidequest.fun` must show the business name "Boardman" and a contact email on the same domain or the legal name. Meta's reviewers check this for the display name and for verification.
- A **new +234 SIM** that has never been used on WhatsApp or WhatsApp Business. If it was, delete that WhatsApp account first (Settings → Account → Delete account) and wait a few minutes **[?]**. Keep the SIM in a phone that can receive SMS or calls: you need it once for the code, and again if Meta re-verifies.
- **Policy check first.** Before paying for anything, ask counsel to read Meta's WhatsApp Business Messaging Policy and Commerce Policy on real-money games of skill **[?]**. Our plan keeps spectator betting off WhatsApp (link to the web only). Staked skill matches still involve money; get a written view.

## 1. Business portfolio (Meta Business Suite)

1. Go to `https://business.facebook.com` and sign in.
2. Create a business portfolio **[?]** ("Create an account"). Business name: the legal name as on the CAC certificate. Your name, a work email on our domain.
3. Settings (gear) → Business info: fill in the legal address, phone, website `https://boardman.playingsidequest.fun`.
4. Settings → People: add a second admin you trust (losing the only admin locks the account).

## 2. Business verification

1. Settings → Security Centre → **Start verification** **[?]**.
2. Pick the country (Nigeria), enter the legal name exactly as on the CAC certificate, the registered address and phone.
3. Upload the CAC certificate, and a proof of address if asked.
4. Choose how Meta confirms you: email on our domain is fastest; phone or a domain DNS record also work **[?]**.
5. Wait. Usually 2 to 14 days **[?]**. Until verified you can still build and test, but you stay on the lowest messaging limit (about 250 business-started conversations per day **[?]**) and cannot get the display name approved for a verified badge.

## 3. Meta developer app with WhatsApp

1. Go to `https://developers.facebook.com` → My Apps → **Create app** **[?]**.
2. Use case: "Other", type **Business** **[?]**. App name: "Boardman WhatsApp". Contact email: ours. Business portfolio: the one from step 1.
3. In the app dashboard, add the product **WhatsApp** → Set up. Meta creates a WhatsApp Business Account (WABA) and a free **test number** **[?]**. Ignore the test number for production but you can use it to try things.
4. App settings → Basic: copy the **App secret** (Show). Store it in the password manager as `WHATSAPP_APP_SECRET`. Also set the Privacy Policy URL to `https://boardman.playingsidequest.fun/legal` **[?]** (or wherever the policy lives) and the app icon.

## 4. Add the +234 number and display name

1. WhatsApp → API Setup (or WhatsApp Manager → Phone numbers) → **Add phone number** **[?]**.
2. Display name: **Boardman**. Category: "Entertainment" or "Games" **[?]**. Description: "Skill 1v1s with stakes held in escrow, settled in USDC."
3. Enter the +234 number, receive the code by SMS or voice, confirm.
4. Set a **two-step verification PIN** for the number when asked. Store it in the password manager. (This PIN is for the number itself; it has nothing to do with players' withdrawal PINs.)
5. Copy the **Phone number ID** (a long number shown next to the number) → `WHATSAPP_PHONE_NUMBER_ID`. Copy the WhatsApp Business Account ID too.
6. The display name goes to review (1 to 3 days **[?]**). Until approved, messages show the number, not "Boardman".

## 5. Permanent token (system user)

Temporary tokens from the API Setup page expire in about 24 hours **[?]**. Production needs a system-user token.

1. business.facebook.com → Settings → Users → **System users** → Add. Name "boardman-api", role **Admin** **[?]**.
2. Select the system user → **Assign assets**: the "Boardman WhatsApp" app (full control) and the WhatsApp account (full control) **[?]**.
3. **Generate new token**: app "Boardman WhatsApp", expiry **Never** **[?]**, permissions `whatsapp_business_messaging` and `whatsapp_business_management` (nothing else).
4. Copy the token once, straight into the password manager as `WHATSAPP_ACCESS_TOKEN`. Never paste it into chat, email or a ticket. If it leaks: revoke it on the same page and generate a new one.

## 6. Webhook

The API server must already run with these set: `WHATSAPP_ENABLED=1`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`. Meta checks the URL the moment you save it.

1. Make up a verify token: 32+ random characters (e.g. from the password manager's generator). Put it in `WHATSAPP_VERIFY_TOKEN` on the server and keep it for the next step.
2. developers.facebook.com → the app → WhatsApp → **Configuration** → Webhook → Edit **[?]**:
   - Callback URL: `https://boardman-api.playingsidequest.fun/webhooks/whatsapp`
   - Verify token: the value from step 1.
   - Click **Verify and save**. Meta sends a GET with `hub.challenge`; our server echoes it only if the token matches.
3. Webhook fields → **Subscribe** to `messages` (this carries both inbound messages and delivery statuses) **[?]**.
4. If the app is still in Development mode, switch it to **Live** (App Mode toggle at the top) **[?]**; otherwise only test numbers reach the webhook.
5. Smoke test: from your own phone, send "hi" to the +234 number. You should get the Boardman welcome with buttons. In the server log you'll see `POST /webhooks/whatsapp 200`. If nothing arrives: check the app is Live, the `messages` field is subscribed, and the URL answers (`curl https://boardman-api.playingsidequest.fun/api/health`).

Notes:
- `/webhooks/` is exempt from the geo-fence on purpose: Meta calls from US data centres, and the US is on our blocked list. The HMAC signature (`X-Hub-Signature-256`, checked with the app secret) authenticates every POST instead.
- Uptime matters: if the server is down, Meta retries for a while **[?]**, but players see silence. The design recommends moving the API to the always-on VM before launch.

## 7. Message templates (utility)

Outside the 24-hour window after a player's last message, we can only send pre-approved templates. Submit each one below in WhatsApp Manager → **Message templates** → Create template **[?]**:

- Category: **Utility** (not Marketing). Language: **English**. Name: exactly as given (lower case, underscores).
- Body: copy the text exactly, including the `{{1}}` variables. Meta asks for a sample value for each variable: use the samples given.
- Buttons: add the listed **Quick reply** buttons in the same order, with the same text. No URL buttons.
- No header, no footer, no emoji, no promotion. Templates that read like marketing get re-categorised and cost more **[?]**.
- Approval usually takes minutes to a day **[?]**. If one is rejected, send engineering the rejection reason; don't reword it yourself, because the code sends these exact names and variable orders (`src/channels/whatsapp/templates.py`, kept in sync with this page by a test).

#### 1. `account_linked`

- Category: Utility. Language: English (`en`).
- Body (copy exactly):

  ```
  Security notice: {{1}} was linked to your Boardman account. If this was not you, contact Boardman support right away.
  ```

- Variables and samples: `{{1}}` identity (sample: WhatsApp +234•••2222)
- Quick-reply buttons: none

#### 2. `challenge_received`

- Category: Utility. Language: English (`en`).
- Body (copy exactly):

  ```
  {{1}} challenged you to {{2}} for {{3}} USDC. The challenge expires in {{4}}.
  ```

- Variables and samples: `{{1}}` challenger (sample: @tobi); `{{2}}` game (sample: EA FC 25); `{{3}}` stake (sample: 10.00); `{{4}}` expires_in (sample: 30 minutes)
- Quick-reply buttons: Accept, Decline

#### 3. `challenge_answered`

- Category: Utility. Language: English (`en`).
- Body (copy exactly):

  ```
  {{1}} {{2}} your {{3}} challenge.
  ```

- Variables and samples: `{{1}}` opponent (sample: @tobi); `{{2}}` answer (sample: accepted); `{{3}}` game (sample: EA FC 25)
- Quick-reply buttons: My match

#### 4. `stake_locked`

- Category: Utility. Language: English (`en`).
- Body (copy exactly):

  ```
  Match {{1}}: {{2}}. Stakes are held in escrow until the result is in.
  ```

- Variables and samples: `{{1}}` match_code (sample: M-7KQ2); `{{2}}` what (sample: both stakes are locked)
- Quick-reply buttons: Lock my stake, Report result

#### 5. `report_reminder`

- Category: Utility. Language: English (`en`).
- Body (copy exactly):

  ```
  Match {{1}} is waiting for your result. Please report it by {{2}}.
  ```

- Variables and samples: `{{1}}` match_code (sample: M-7KQ2); `{{2}}` deadline (sample: 18:30 WAT)
- Quick-reply buttons: Report result

#### 6. `match_result`

- Category: Utility. Language: English (`en`).
- Body (copy exactly):

  ```
  Match {{1}} is settled: {{2}}. Amount: {{3}} USDC. Your balance is {{4}} USDC.
  ```

- Variables and samples: `{{1}}` match_code (sample: M-7KQ2); `{{2}}` outcome (sample: you won); `{{3}}` amount (sample: 18.50); `{{4}}` balance (sample: 52.00)
- Quick-reply buttons: Wallet

#### 7. `match_disputed`

- Category: Utility. Language: English (`en`).
- Body (copy exactly):

  ```
  Match {{1}} is under review because the reported results differ. We will message you with the outcome.
  ```

- Variables and samples: `{{1}}` match_code (sample: M-7KQ2)
- Quick-reply buttons: Match status

#### 8. `match_refunded`

- Category: Utility. Language: English (`en`).
- Body (copy exactly):

  ```
  Match {{1}} was {{2}}. {{3}} USDC was returned to your balance.
  ```

- Variables and samples: `{{1}}` match_code (sample: M-7KQ2); `{{2}}` reason (sample: cancelled); `{{3}}` amount (sample: 18.50)
- Quick-reply buttons: Wallet

#### 9. `deposit_received`

- Category: Utility. Language: English (`en`).
- Body (copy exactly):

  ```
  Deposit received: {{1}} USDC. Your balance is {{2}} USDC.
  ```

- Variables and samples: `{{1}}` amount (sample: 18.50); `{{2}}` balance (sample: 52.00)
- Quick-reply buttons: Wallet

#### 10. `withdrawal_update`

- Category: Utility. Language: English (`en`).
- Body (copy exactly):

  ```
  Your withdrawal of {{1}} USDC to {{2}} is {{3}}.
  ```

- Variables and samples: `{{1}}` amount (sample: 18.50); `{{2}}` destination (sample: 0x12ab…9f3c); `{{3}}` status (sample: submitted)
- Quick-reply buttons: Wallet

#### 11. `security_outflow`

- Category: Utility. Language: English (`en`).
- Body (copy exactly):

  ```
  Security notice: {{1}} USDC left your Boardman wallet to {{2}}. If this was not you, contact Boardman support right away.
  ```

- Variables and samples: `{{1}}` amount (sample: 18.50); `{{2}}` destination (sample: 0x12ab…9f3c)
- Quick-reply buttons: Wallet, Not me

#### 12. `spend_approval`

- Category: Utility. Language: English (`en`).
- Body (copy exactly):

  ```
  Approve a {{1}} of {{2}} USDC on Boardman? This request expires in {{3}}.
  ```

- Variables and samples: `{{1}}` action (sample: spectator bet); `{{2}}` amount (sample: 18.50); `{{3}}` expires_in (sample: 30 minutes)
- Quick-reply buttons: Yes, No, Always

#### 13. `cup_match_ready`

- Category: Utility. Language: English (`en`).
- Body (copy exactly):

  ```
  Your {{1}} match against {{2}} is ready. Play it by {{3}}.
  ```

- Variables and samples: `{{1}}` cup (sample: Lagos Weekend Cup); `{{2}}` opponent (sample: @tobi); `{{3}}` deadline (sample: 18:30 WAT)
- Quick-reply buttons: My match

#### 14. `cup_result`

- Category: Utility. Language: English (`en`).
- Body (copy exactly):

  ```
  {{1}} has finished. You placed {{2}}. Prize: {{3}} USDC.
  ```

- Variables and samples: `{{1}}` cup (sample: Lagos Weekend Cup); `{{2}}` place (sample: 2nd); `{{3}}` prize (sample: 25.00)
- Quick-reply buttons: Wallet

#### 15. `match_ready` (new with the skill-match flows)

- Category: Utility. Language: English (`en`).
- Body (copy exactly):

  ```
  Match {{1}}: both stakes are locked. Play your {{2}} match, then report the result here.
  ```

- Variables and samples: `{{1}}` match_code (sample: K7M2P9QX); `{{2}}` game (sample: EA FC Mobile)
- Quick-reply buttons: Report result


Not needed: authentication templates (web login will use a code the player sends *to* us), and marketing templates (optional, later, with a monthly budget).

## 8. Payment method and limits

1. WhatsApp Manager → Settings → **Payment methods**: add a card for the WABA **[?]**. Utility templates outside the window are charged per message; free-form replies inside the window are free **[?]**. Check the current Nigeria rate card before setting a budget.
2. Messaging limit: new numbers start at about 250 business-started conversations per 24 h **[?]**. It rises after business verification and with good quality. Watch the **Quality rating** in WhatsApp Manager: blocks and reports lower it.

## 9. Hand-off checklist

Send engineering (through the password manager, never chat):

- [ ] `WHATSAPP_PHONE_NUMBER_ID`
- [ ] `WHATSAPP_APP_SECRET`
- [ ] `WHATSAPP_ACCESS_TOKEN` (system user, never expires)
- [ ] `WHATSAPP_VERIFY_TOKEN`
- [ ] `WHATSAPP_DISPLAY_NUMBER` (e.g. `2348012345678`)
- [ ] WhatsApp Business Account ID
- [ ] Which templates are approved (names)
- [ ] Business verification status, display-name status, current messaging limit
- [ ] Counsel's written view on the policy question in section 0

Then engineering sets `WHATSAPP_ENABLED=1` and `CHANNELS_CORE_FLOWS_WHATSAPP=all`, runs the smoke test in section 6 and opens a closed beta.
