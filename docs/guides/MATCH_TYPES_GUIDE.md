
# 🎮 sideQuest Match Types: Local vs Online

Complete guide to how sideQuest handles match outcomes for both **Local** (same console/TV) and **Online** (remote) matches.

---

## 🏠 Local Match

### Definition
Two players physically present at the same console/TV playing together.

### Verification Requirements
```
✅ Screenshot Required: YES
❌ Platform Activity Check: NO (optional)
⏱️ Time Limit: 60 minutes to complete
📸 Photo Requirements: Both players + TV screen
```

### Why Different?
- **Same console** means both players use one account
- **Screenshot proves** both players were present (both in frame)
- **Faster resolution** since it's harder to fake

### Flow
```
1. Player A: /challenge_local 10 FIFA
2. Player B: /match <id>
3. Player A: /approve <id>
4. [Play match on console]
5. Take selfie: Both players + TV showing final score
6. Player A: /report <id> 2-1 [upload selfie]
7. Player B: /report <id> 1-2 [upload selfie]
8. AI verifies: Do selfies match? Who's in both?
```

### Evidence Standard
- **Primary**: Photo showing both players + final score
- **Backup**: Screenshot of just TV (if selfie unavailable)
- **Platform check**: Optional (PSN/Xbox activity not required)

---

## 🌐 Online Match

### Definition
Two players in different locations playing remotely via online matchmaking.

### Verification Requirements
```
✅ Screenshot Required: YES
✅ Platform Activity Check: YES (mandatory)
⏱️ Time Limit: 120 minutes to complete
📸 Photo Requirements: Individual screenshot of final score
```

### Why Different?
- **Remote play** requires additional verification
- **Platform activity** confirms match actually happened
- **Timestamp correlation** between screenshot and activity

### Flow
```
1. Player A: /challenge 10 FIFA (online by default)
2. Player B: /match <id>
3. Player A: /approve <id>
4. [Play online match - connect via game]
5. Player A: /report <id> 2-1 [upload screenshot]
6. System: ✅ Screenshot extracted score: 2-1
          ✅ PSN shows FIFA played 15 mins ago
          ✅ Waiting for Player B...
7. Player B: /report <id> 1-2 [upload screenshot]
8. System: ❌ Conflict detected!
          Player A: Screenshot shows 2-1
          Player B: Screenshot shows 1-2
          ➡️ AI Court mediation...
```

### Evidence Standard
- **Primary**: Screenshot of final score
- **Required**: PSN/Xbox activity within 2 hours
- **Cross-check**: Timestamp + activity correlation

---

## ⚖️ How Outcomes Are Determined

### Case 1: Both Players Agree ✅

```
Player A reports: 2-1
Player B reports: 2-1
Screenshots: Both show 2-1
Platform activity: Both played FIFA within timeframe

Result: ✅ AUTO-RESOLVE
Winner: Player A (home)
Payout: Immediate (within seconds)
```

### Case 2: Players Disagree ⚠️

```
Player A reports: 2-1 (claims win)
Player B reports: 1-2 (claims win)
Screenshots: Show different scores

Result: ⚠️ DISPUTE - AI Court
AI analyzes:
  - Screenshot 1: Extracts "2-1" (confidence: 95%)
  - Screenshot 2: Extracts "1-2" (confidence: 92%)
  - PSN Activity: Player A played 15 mins ago ✓
  - PSN Activity: Player B played 20 mins ago ✓
  
AI Decision: "Different matches shown. Request replay or void."
Options:
  - Replay match (stakes held)
  - Void match (stakes returned)
  - Manual admin review
```

### Case 3: One Player Reports 🕐

```
Player A reports: 2-1 [with screenshot]
Player B: [No report after deadline]

Result: 🏆 WIN BY FORFEIT
Winner: Player A
Payout: Automatic after deadline
Action: Log "forfeit" on Player B record
```

### Case 4: Draw 🤝

```
Player A reports: 1-1 (draw)
Player B reports: 1-1 (draw)
Screenshots: Both confirm 1-1

Result: 🤝 DRAW
Action: Stakes returned to both players
Fee: 0% (no winner)
```

---

## 🔍 Verification Matrix

| Aspect | Local Match | Online Match |
|--------|-------------|--------------|
| **Screenshot** | Required (both players visible) | Required (final score) |
| **Platform Activity** | Optional | Required |
| **Time Limit** | 60 min | 120 min |
| **Report Window** | 30 min | 30 min |
| **Auto-Resolve** | Yes (if selfie valid) | Yes (if evidence agrees) |
| **Dispute Rate** | Lower | Higher |
| **Fraud Risk** | Lower | Higher |

---

## 🤖 AI Verification Logic

### Step 1: Extract Evidence
```python
1. Parse text report: "2-1" → home: 2, away: 1
2. Analyze screenshot: Extract score using Vision AI
3. Check platform: Did player play recently?
4. Cross-reference: Do all sources agree?
```

### Step 2: Determine Consensus
```python
if screenshot_confidence >= 80 and text_matches_screenshot:
    if platform_activity_confirms:
        return "AUTO_APPROVE"
    else:
        return "PENDING_PLATFORM"
elif sources_conflict:
    return "ESCALATE_TO_AI_COURT"
else:
    return "PENDING_OPPONENT"
```

### Step 3: AI Court Mediation (if dispute)
```python
dispute_context = {
    "player1_report": {"score": "2-1", "screenshot": "url1"},
    "player2_report": {"score": "1-2", "screenshot": "url2"},
    "platform_data": {"player1": {...}, "player2": {...}},
    "timestamps": {...}
}

ai_decision = ollama.analyze(dispute_context)
# Returns: "player1_win", "player2_win", "draw", "replay", "void"
```

---

## ⏰ Timing & Deadlines

### Match Timeline
```
0 min: Match created
└─ 24 hours to find opponent (or expires)

Opponent joins:
└─ Creator has 24 hours to approve

Match approved:
├─ 60 min (local) or 120 min (online) to PLAY
├─ Match must finish before deadline
└─ 30 min after match to SUBMIT REPORTS

After deadline:
├─ Both reported: Check consensus
├─ One reported: Win by forfeit
└─ None reported: Stakes returned
```

### Grace Periods
- **Join**: 24 hours to find opponent
- **Approve**: 24 hours for creator to approve
- **Play**: 60-120 min to complete match
- **Report**: 30 min after play deadline

---

## 🛡️ Anti-Cheat Measures by Type

### Local Matches
1. **Both players in photo** - Hard to fake both faces
2. **Same timestamp** - Photo metadata
3. **TV reflection** - Check if screen is real
4. **Physical presence** - Body language analysis (future)

### Online Matches
1. **Platform activity correlation** - Did both play at same time?
2. **Screenshot metadata** - Timestamp verification
3. **Score range validation** - Is score realistic?
4. **IP analysis** - Different locations (optional)

---

## 📱 User Commands

### Create Match
```
/challenge <amount> <game> [type]

Examples:
/challenge 10 FIFA           → Online match (default)
/challenge 10 FIFA local   → Local match
/challenge 10 FIFA online  → Online match (explicit)
```

### Report Outcome
```
/report <match_id> <score> [photo]

Examples:
/report abc123 2-1           → Text only
/report abc123 2-1 [photo]   → With screenshot

For local matches:
- Include selfie with opponent + TV
- Both players should be visible
- Final score must be clear
```

### Check Status
```
/status <match_id>

Shows:
- Current status (playing, pending, etc.)
- Time remaining
- What's needed from you
- Opponent's report status
```

---

## 🧪 Test Scenarios

### Scenario 1: Perfect Local Match
```
Player A: /challenge_local 10 FIFA
Player B: /match abc123
Player A: /approve abc123
[Play match, score: 3-2]
Player A: /report abc123 3-2 [selfie showing both players + TV: 3-2]
Player B: /report abc123 3-2 [selfie showing both players + TV: 3-2]

✅ Result: Auto-resolve, Player A wins
Time: < 10 seconds
```

### Scenario 2: Cheating Attempt (Online)
```
Player A: /challenge 10 FIFA
Player B: /match def456
Player A: /approve def456
[Player A wins 4-1]
Player A: /report def456 4-1 [real screenshot]
Player B: /report def456 1-4 [fake/old screenshot]

⚠️ Result: Dispute detected
AI Analysis:
  - Screenshot 1: Real FIFA end-screen ✓
  - Screenshot 2: Old screenshot from different match
  - PSN Activity: Only Player A has recent activity

✅ AI Decision: Player 1 wins, Player 2 flagged for review
```

### Scenario 3: Timeout (Forfeit)
```
Match starts at 14:00
Deadline: 16:00 (2 hours)

Player A reports: 2-1 at 15:30
Player B: No report by 16:30 (deadline + 30 min)

🏆 Result: Player A wins by forfeit
Payout: Automatic
Penalty: Player B gets "no-show" on record
```

---

## 📊 Expected Performance

| Metric | Local | Online | Target |
|--------|-------|--------|--------|
| Auto-resolution rate | 85% | 70% | >75% |
| Dispute rate | 5% | 15% | <10% |
| Avg resolution time | 2 min | 5 min | <5 min |
| Fraud detection | 99% | 85% | >90% |

---

## 🔧 Admin Commands

### Override Match
```
/admin_resolve <match_id> <winner_id> <reason>

Force resolve a disputed match
Logs: Admin action with reason
```

### Cancel Match
```
/admin_cancel <match_id> <reason>

Cancel match and refund both players
Use for: Technical issues, agreed cancellation
```

### Review Evidence
```
/admin_evidence <match_id>

View all evidence:
- Screenshots
- Platform activity
- Timestamps
- AI analysis
```

---

## 📋 Summary

### Local Matches
- **Best for**: Friends playing together, LAN parties
- **Trust level**: High (both present)
- **Speed**: Fast resolution
- **Requirements**: Photo with both players

### Online Matches
- **Best for**: Remote players, global matching
- **Trust level**: Medium (needs verification)
- **Speed**: Standard resolution
- **Requirements**: Screenshot + platform activity

Both types provide fair, verifiable outcomes with appropriate security levels!

---

*Built with 🎮 by sideQuest*
