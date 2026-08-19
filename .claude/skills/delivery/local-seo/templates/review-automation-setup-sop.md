# Review Automation — Setup SOP (Agency)

**Audience:** the WEBRIS operator (or VA) setting up a client's automated review engine.
**When to run:** after the client's *Review Generation & Management Playbook* is delivered and the strategy call is done.
**Goal:** automated review requests running **from the agency's tooling** — the client never logs into a tool. Set up once at the agency level and reuse per client.

> The client-facing playbook only *describes* this as a done-for-you service. All tool names, plans, pricing, and steps live here — never in the client deliverable.

---

## 1. Choose the path

| If the agency… | Use | Why |
|---|---|---|
| Already runs **GoHighLevel** (or a similar CRM) | **Path A** | No new spend; add the client as a sub-account and reuse across the whole book. |
| Does **not** run a CRM | **Path B — BrightLocal** | Purpose-built for local reviews; agency account with each client as a location. |

Either way it's an **agency-level** setup, reused per client. Reviews become a recurring, billable add-on — not a per-client tool stack.

---

## 2. Prerequisites (both paths)

- **Google Business Profile manager access** for each client location (client grants access, or adds the agency as a manager).
- The client's **per-office direct review links** (from the playbook / Step 1 NAP): `https://search.google.com/local/writereview?placeid={PLACE_ID}`.
- **TCPA opt-in on the client's intake** — a "yes, you can text me" consent checkbox. Confirm this is in place **before enabling SMS**. This is the one client-side item.
- **Approved message copy** — SMS + email request + reminder (Section 5).

---

## 3. Path A — GoHighLevel

Repeat the location-level pieces for **each office**.

1. **Add the client as a sub-account / location** in your agency GHL.
2. **Connect Google (and Facebook) at the location level** — Reputation → Settings → sign in with the Google account that manages that office's Business Profile and select the correct listing.
3. **Create the workflow** — Automation → Workflows → + New Workflow.
4. **Set the trigger** — Opportunity Status → "Won" / "Service Completed", or Appointment Status → "Showed Up", or a manual "Request Review" tag staff add at case close.
5. **Add the Review Request action** — choose **SMS** (best response) or Email; message text is configured in Reputation Settings. Include a thank-you + the office-specific review link.
6. **Add one reminder** — 24-hour wait → "no review yet?" condition → single follow-up → stop.
7. **Time it** — fire ~30 minutes after the case/consult is marked complete.
8. **Publish + test** — publish the workflow and run a test with your own phone/email before it goes live (Section 6).

---

## 4. Path B — BrightLocal

- **Plan:** review-generation campaigns require the **Grow plan ($59/mo)**. Track ($39) and Manage ($49) do **not** include reviews. Multi-location only scales up around 11+ locations, so a typical 1–10 office client fits the base tier. *(Verify current pricing at signup.)*
- **Alternative:** Grade.us (~$36/seat) for pure resell/agency management.

Steps:

1. **Sign up / open the agency account** at brightlocal.com and **add each office as a location**.
2. **Reputation Manager → Get Reviews** → create a review-generation campaign.
3. **Build the template** — email + SMS request copy (Section 5); **select Google** as the review site for each office.
4. **Load SMS credits** — text requests use a small per-message credit; top up in the campaign panel. SMS gets the best response.
5. **Get Request URLs** — click "Get Request URLs" for links + **QR codes** to drop into email signatures, intake forms, and printed office cards.
6. **Add contacts** — upload past clients or connect the client's intake; enable the automatic reminder.

---

## 5. Message templates (copy-paste)

Merge fields: `{FirstName}`, `{FirmName}`, `{OfficeReviewLink}`, `{CallerName}`.

**SMS — initial**
> Hi {FirstName}, it's {CallerName} at {FirmName}. It was a privilege to help with your case. Would you take 30 seconds to share your experience? It really helps others find us: {OfficeReviewLink}

**SMS — reminder (24h, if no review)**
> Hi {FirstName}, just following up — if you have a moment, here's the link to leave {FirmName} a quick review. Thank you! {OfficeReviewLink}

**Email — initial** (subject: *A quick favor?*)
> Hi {FirstName},
> Thank you again for trusting {FirmName}. Reviews make a real difference for a firm like ours — they help other people in a tough spot know they can turn to us. If you have 30 seconds, we'd be grateful if you'd share your experience: {OfficeReviewLink}
> Thank you, {CallerName}

**Email — reminder**
> Hi {FirstName}, just a gentle follow-up in case you missed my last note — here's the link to leave a quick review: {OfficeReviewLink}. No worries either way, and thank you.

Keep copy honest and non-incentivized. Never offer anything of value for a review.

---

## 6. Test before go-live (checklist)

- [ ] Create a **test contact** with your own phone + email.
- [ ] Manually fire the trigger (or move the test opportunity/appointment).
- [ ] SMS **and** email received with correct copy.
- [ ] Review link opens the **correct office's** Google review box.
- [ ] Reminder fires after ~24h when no review is left.
- [ ] Workflow/campaign **stops** once a review is detected (GHL) / after the sequence (BrightLocal).
- [ ] Workflow is **Published** (GHL) / campaign is **Active** (BrightLocal).

---

## 7. Go-live & client handoff

- Turn the automation on for all offices.
- Tell the client it's live and confirm their **one job**: keep the intake opt-in checkbox in place.
- Document, per client: which **path/account**, the **trigger** used, and **which offices** are connected.

---

## 8. Ongoing management

- **Response SLA:** respond to every new review (positive + negative) within **48h** — draft replies for the client's approval; never share case details.
- **Monthly recount:** re-count reviews per office → **velocity vs. targets** (baseline captured in the Local SEO audit). *The velocity tracker + monthly review report are built in the reporting process — this SOP sets the baseline and the system.*
- Recommend **Loganix** for done-for-you review-response management if the client wants it hands-off.

---

## 9. Compliance guardrails

- **TCPA:** SMS requests require prior opt-in — confirm intake consent before enabling SMS.
- **No review gating:** ask everyone; make Google easy; **never suppress or filter out negative reviewers** (Google prohibits it).
- **Incentives:** staff-only rewards for effort — **never** pay or reward the reviewer.
- **Authenticity:** every review must reflect a real experience; never write or fabricate reviews.
