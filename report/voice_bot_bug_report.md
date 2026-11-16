# Pretty Good AI â€” Medical Receptionist Evaluation

**Test date:** November 16, 2026  
**Test setup:** Python LiveKit Agents AI patient, Deepgram STT, OpenAI LLM, Cartesia TTS, outbound SIP.  
**Evidence:** 10 stereo call recordings (reported saved by tester) and 10 automated two-channel transcripts. Transcripts should be checked against original MP3 before submission.  
**Scope:** Findings describe the *receptionist*, except where explicitly marked as AI-patient/test-harness behavior. Backend state and SMS delivery were not independently verified.

## BUG-01 â€” Incorrect DOB in documented correction request

**Priority:** High | **Confidence:** High from transcript; verify audio  
**Call:** `20261116_165838_office_hours.mp3`  
**Evidence timestamps:** 00:45â€“01:27, especially 01:03â€“01:07 (patient confirmation) and 01:20â€“01:25 (receptionist summary)

**Steps to reproduce:** Create demo profile as Alex Morgan; state correct DOB is January 15, 1995; explicitly request correction.  
**Expected:** Receptionist accurately repeats and records *January 15, 1995*, or states it cannot update the record.  
**Observed:** Receptionist first confirms January 15, 1995, but subsequently says it added a request to update DOB to **January 5, 1995**.  
**Impact:** Incorrect demographic information could be passed to staff; identity and record matching may be affected.  
**Limitation:** The transcript establishes the spoken mismatch, not whether backend data was actually changed.

## BUG-02 â€” Multi-intent request left unresolved

**Priority:** Medium | **Confidence:** High for conversation outcome  
**Call:** `20261116_172402_multiple_requests.mp3`  
**Evidence timestamps:** 00:00â€“00:39 and 04:00â€“05:08

**Steps to reproduce:** At call start, request an appointment **and** ask a question about insurance. Continue the appointment workflow.  
**Expected:** Receptionist handles both requests, or explicitly parks and returns to the insurance question before ending.  
**Observed:** Receptionist acknowledges it can help with both but spends the remainder of the call on scheduling/rescheduling. No insurance explanation or follow-up appears before the recording ends.  
**Impact:** One of two customer requests is dropped.  
**Limitation:** Recording ends around 308 seconds; cannot conclude the receptionist would never address insurance if allowed more time.

## BUG-03 â€” Time preference boundary mishandled

**Priority:** Lowâ€“Medium | **Confidence:** High from transcript  
**Call:** `20261116_161528_appointment.mp3`  
**Evidence timestamps:** 01:13â€“01:58

**Steps to reproduce:** Request a Friday appointment **after 3:00 PM**.  
**Expected:** Only slots later than 3:00 PM are proposed as satisfying the preference.  
**Observed:** Receptionist describes 3:00 PM as the first slot *after* 3 PM and offers it. When the patient rejects that slot, it offers 3:30 PM, which the patient accepts.  
**Impact:** Incorrect handling of strict time boundaries causes extra turns and could lead to unsuitable bookings.  
**Limitation:** The issue was corrected conversationally and the booked time was 3:30 PM.

## BUG-04 â€” Repetitive rescheduling confirmation / degraded completion

**Priority:** Medium | **Confidence:** Medium; verify original audio  
**Call:** `20261116_172402_multiple_requests.mp3`  
**Evidence timestamps:** 04:27â€“05:08

**Steps to reproduce:** Ask to reschedule an existing appointment to Wednesday November 18, 9:00 AM; provide reason and confirm.  
**Expected:** A single clear confirmation with new date, time and provider, followed by closure.  
**Observed:** After saying it is processing the reschedule, receptionist repeats 'Your appointment is now scheduled' as recording approaches cutoff. Patient remarks the message cut off.  
**Impact:** Unclear final status and degraded user experience.  
**Limitation:** A five-minute cap may have terminated the call; investigate recording and application logs before assigning responsibility solely to receptionist.

## INVESTIGATION â€” Inconsistent DOB-update capabilities

**Calls:** `20261116_165056_insurance.mp3`, `20261116_165838_office_hours.mp3`, `20261116_170458_interruption.mp3`  
In the insurance call, receptionist says it cannot directly change DOB and offers a support follow-up. In office-hours/interruption calls, it asks whether it should update DOB, but at least one later describes forwarding a request. This may be a wording inconsistency rather than a functional bug. Do not label confirmed until backend behavior or additional audio supports it.

## AI PATIENT / TEST-HARNESS ISSUES â€” NOT receptionist bugs

- **Reschedule call:** `20261116_162412_reschedule.mp3` â€” patient says it has no appointment even when receptionist retrieves an earlier appointment; no actual reschedule performed.
- **Cancellation call:** `20261116_163608_cancellation.mp3` â€” patient requests information about cancellation rather than requesting a cancellation; receptionist does not cancel.
- **Appointment call:** `20261116_161528_appointment.mp3` â€” patient incorrectly calls November 20, 2026 a past date, despite call being November 16.
- **Ambiguity and multiple-requests recordings:** durations ~308 seconds; inspect call duration accounting and final audio before treating as complete recordings.

## Positive findings / no bug demonstrated

- **Refill:** `20261116_164351_refill.mp3` â€” receptionist explains refill requests require review and does not claim an unapproved refill was approved.
- **Insurance:** `20261116_165056_insurance.mp3` â€” receptionist asks for plan/member details and offers ways to verify; it does not guarantee coverage.
- **Interruption:** `20261116_170458_interruption.mp3` â€” receptionist appears to complete an appointment move, although interruption handling and audio overlap require listening review.

## Submission evidence checklist

- [ ] Listen to MP3 segments at the timestamps above and correct any transcription errors.
- [ ] Ensure 10 complete two-sided MP3/OGG files and matching transcripts are present.
- [ ] Include bug IDs, severity, reproduction steps, expected vs actual, impact, evidence timestamps, and limitations.
- [ ] Confirm recording permissions and redact credentials or sensitive details from repository/logs.
- [ ] Private GitHub repository contains setup/run instructions, code, scenario definitions, evidence and bug reports.
- [ ] Loom #1: <=3-minute walkthrough with camera on.
- [ ] Loom #2: screen recording showing AI-assisted debugging/fixing.
- [ ] Add submission links and reviewer access as required by the assignment.

