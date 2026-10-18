'use client'

/**
 * One-time naira top-up page, opened from a chat link (Telegram or WhatsApp).
 * Paycrest requires the paying customer's identity on every naira on-ramp, so
 * the BVN/NIN is typed here, never in a chat. It is sent once to Paycrest and
 * Boardman does not keep it. After submit the page shows the account to pay.
 */

import { useParams } from 'next/navigation'
import { useEffect, useState } from 'react'
import { BookShell } from '@/components/rematch/BookShell'

type Institution = { code: string; name: string; type?: string }

type View = {
  ok: boolean
  amount_ngn?: string
  rate?: string
  receive_usdc?: string
  bridge_fee_max_usdc?: string
  sender_fee_usdc?: string
  id_types?: string[]
  institutions?: Institution[]
  expires_in_sec?: number
  error?: string
  message?: string
}

type Pay = {
  amount_to_transfer?: string
  account_identifier?: string
  account_name?: string
  valid_until?: string
}

type Result = { ok: boolean; status?: string; message?: string; error?: string; pay?: Pay; bank_name?: string }

const ID_LABEL: Record<string, string> = { BVN: 'BVN', nationalID: 'NIN' }

export default function NairaTopUpPage() {
  const params = useParams()
  const token = String(params?.token || '')
  const [view, setView] = useState<View | null>(null)
  const [fullName, setFullName] = useState('')
  const [birthDate, setBirthDate] = useState('')
  const [idType, setIdType] = useState('BVN')
  const [idNumber, setIdNumber] = useState('')
  const [bank, setBank] = useState('')
  const [account, setAccount] = useState('')
  const [agree, setAgree] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [done, setDone] = useState<Result | null>(null)

  useEffect(() => {
    ;(async () => {
      const res = await fetch(`/api/rematch/app/naira/${encodeURIComponent(token)}`, {
        credentials: 'same-origin',
        cache: 'no-store',
      })
      const data = (await res.json().catch(() => ({ ok: false }))) as View
      setView(res.ok ? data : { ok: false, message: data.message || 'This link is not valid.' })
    })()
  }, [token])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    if (fullName.trim().split(/\s+/).length < 2) return setErr('Enter your full name as it appears at your bank.')
    if (!/^\d{4}-\d{2}-\d{2}$/.test(birthDate)) return setErr('Enter your date of birth.')
    if (!/^\d{11}$/.test(idNumber)) return setErr(`${ID_LABEL[idType] || 'ID'} is 11 digits.`)
    if (!bank) return setErr('Pick your bank.')
    if (!/^\d{10}$/.test(account)) return setErr('Account numbers are 10 digits.')
    if (!agree) return setErr('Please confirm the details are yours.')
    setBusy(true)
    const res = await fetch(`/api/rematch/app/naira/${encodeURIComponent(token)}`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        kyc: { full_name: fullName, birth_date: birthDate, id_type: idType, id_number: idNumber },
        refund: { institution: bank, account_identifier: account },
      }),
    })
    const data = (await res.json().catch(() => ({ ok: false }))) as Result
    setBusy(false)
    setIdNumber('')
    if (res.ok && data.ok) {
      setDone(data)
      return
    }
    if (['used', 'expired', 'not_found', 'kyc_rejected', 'failed'].includes(String(data.error))) {
      setView({ ok: false, message: data.message })
      return
    }
    setErr(data.message || data.error || 'That did not work. Try again.')
  }

  return (
    <BookShell title="Top up with naira">
      {!view ? (
        <div className="rm-card">
          <div className="rm-skeleton" style={{ height: 40, width: '60%' }} />
        </div>
      ) : !view.ok ? (
        <div className="rm-card rm-card-warn">
          <p className="rm-warn-text" style={{ marginTop: 0 }}>
            {view.message || 'This link is not valid.'}
          </p>
          <p className="rm-muted" style={{ marginBottom: 0, fontSize: '0.8rem' }}>
            Links work once and expire after a few minutes. Go back to the chat and start again.
          </p>
        </div>
      ) : done ? (
        <div className="rm-card rm-stack">
          {done.pay ? (
            <>
              <span className="rm-label">Pay exactly</span>
              <div className="rm-balance">₦{Number(done.pay.amount_to_transfer || 0).toLocaleString('en-NG')}</div>
              <span className="rm-label">to</span>
              <code className="rm-code">
                {done.bank_name} · {done.pay.account_identifier}
              </code>
              <span className="rm-muted">{done.pay.account_name}</span>
              {done.pay.valid_until ? (
                <span className="rm-muted" style={{ fontSize: '0.8rem' }}>
                  Before {new Date(done.pay.valid_until).toLocaleString()}
                </span>
              ) : null}
              <p className="rm-warn-text" style={{ marginBottom: 0, fontSize: '0.85rem' }}>
                Pay from your own bank account, in your own name. Payments from anyone else are held and sent
                back. The chat has these details too.
              </p>
            </>
          ) : (
            <p className="rm-ok" style={{ marginTop: 0 }}>{done.message}</p>
          )}
        </div>
      ) : (
        <form className="rm-card rm-stack-lg" onSubmit={submit} autoComplete="off">
          <div className="rm-card-hero" style={{ padding: 0 }}>
            <span className="rm-label">You send</span>
            <div className="rm-balance">₦{Number(view.amount_ngn || 0).toLocaleString('en-NG')}</div>
            <span className="rm-label">
              You get about ${Number(view.receive_usdc || 0).toFixed(2)} USDC in your play wallet
            </span>
            <span className="rm-muted" style={{ fontSize: '0.8rem' }}>
              Rate ₦{Number(view.rate || 0).toLocaleString('en-NG')} per $1 (Paycrest&apos;s 0.5% fee included).
              Bridge fee up to ${Number(view.bridge_fee_max_usdc || 0).toFixed(2)}. Paycrest&apos;s network fee is
              added to the amount you pay. This is real money.
            </span>
          </div>

          <p className="rm-muted" style={{ margin: 0, fontSize: '0.8rem' }}>
            Paycrest, our naira partner, must identify everyone who pays in. Your details go to Paycrest for this
            payment only; Boardman does not store your BVN or NIN.
          </p>

          <div>
            <label className="rm-label" htmlFor="nm">Full name (as at your bank)</label>
            <input id="nm" className="rm-input" value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </div>
          <div>
            <label className="rm-label" htmlFor="dob">Date of birth</label>
            <input id="dob" className="rm-input" type="date" value={birthDate}
              onChange={(e) => setBirthDate(e.target.value)} />
          </div>
          <div>
            <label className="rm-label" htmlFor="idt">ID</label>
            <select id="idt" className="rm-input" value={idType} onChange={(e) => setIdType(e.target.value)}>
              {(view.id_types || ['BVN']).map((t) => (
                <option key={t} value={t}>{ID_LABEL[t] || t}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="rm-label" htmlFor="idn">{ID_LABEL[idType] || 'ID'} number (11 digits)</label>
            <input id="idn" className="rm-input" type="password" inputMode="numeric" autoComplete="off"
              value={idNumber} onChange={(e) => setIdNumber(e.target.value.replace(/\D/g, '').slice(0, 11))} />
          </div>
          <div>
            <label className="rm-label" htmlFor="bk">Your bank (refunds go here)</label>
            <select id="bk" className="rm-input" value={bank} onChange={(e) => setBank(e.target.value)}>
              <option value="">Choose…</option>
              {(view.institutions || []).map((i) => (
                <option key={i.code} value={i.code}>{i.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="rm-label" htmlFor="acct">Account number</label>
            <input id="acct" className="rm-input" inputMode="numeric" value={account}
              onChange={(e) => setAccount(e.target.value.replace(/\D/g, '').slice(0, 10))} />
          </div>
          <label className="rm-muted" style={{ fontSize: '0.8rem' }}>
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} /> These are my own
            details and my own bank account.
          </label>

          <button type="submit" className="rm-btn rm-btn-primary" disabled={busy}>
            {busy ? 'Working…' : 'Get account to pay'}
          </button>
          <p className="rm-muted" style={{ margin: 0, fontSize: '0.75rem' }}>
            Boardman never asks for your BVN or NIN in a chat. If you did not start this, close the page.
          </p>
        </form>
      )}

      {err ? <p className="rm-err">{err}</p> : null}
    </BookShell>
  )
}
