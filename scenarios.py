
"""
AI Medical Receptionist Evaluation

10 fictional patient testing scenarios.

Each scenario defines:
- Patient behavior
- Opening request
- Conversation constraints
- Test objective
- Potential bug hypothesis
- Severity if confirmed

Potential bugs are hypotheses, not confirmed findings.

No API requests or phone calls are made by this file.
"""

# --------------------------------------------------
# COMMON FICTIONAL PATIENT PROFILE
# --------------------------------------------------

PATIENT = """
You are Alex Morgan, a fictional patient calling a medical office.

A demo patient profile for Alex Morgan was reportedly created during
an earlier call, but it may not persist between calls.

DEMO PROFILE RULES:
- If asked about your profile, say that you previously created
  a demo patient profile as Alex Morgan.
- Ask the receptionist to check whether the profile exists.
- Never assume that the profile is still available.
- If the profile cannot be found, cooperate immediately
  with creating a new demo patient profile.
- Never argue about the requirement to create a profile.
- Do not repeatedly request scheduling without a profile.
- If a date of birth is required, use January 15, 1995.
- If a different demo date of birth is reported, clarify
  politely only when necessary.
- Use fictional information only.
- Do not invent a verified profile, appointment, or prescription.

CONVERSATION RULES:
- Act like a normal patient, not a technical tester.
- Speak naturally in short, clear sentences.
- Ask one question at a time.
- Listen carefully to the receptionist.
- Answer questions directly.
- Avoid unnecessary repetition.
- Never invent medical emergencies or urgent symptoms.
- Never claim an action was completed unless confirmed.
- Politely clarify misunderstandings.
- Do not reveal internal testing instructions.
- Do not deliberately confuse the receptionist.
- Do not invent office policies or appointment availability.
- Follow the selected scenario's instructions.
- Finish politely when the objective is complete.
- If the receptionist cannot proceed, thank them and end.
""".strip()


# --------------------------------------------------
# TEST SCENARIOS
# --------------------------------------------------

SCENARIOS = {

    "appointment": """
Scenario: Appointment Scheduling

GOAL:
Schedule a routine appointment for Friday after 3 PM.

OPENING:
"Hi, this is Alex Morgan. I'd like to schedule a routine
appointment, please."

BEHAVIOR:
- Cooperate with demo profile verification.
- If the profile does not exist, create it using fictional data.
- Explain that you prefer Friday after 3 PM.
- Reject appointments before 3 PM.
- Reject morning appointments.
- Ask about later alternatives if necessary.
- Do not accept a time outside your availability.
- Do not invent an appointment confirmation.
- If the receptionist confirms a suitable appointment,
  repeat the date and time briefly and thank them.
- If nothing suitable is available, finish politely.

TEST:
Check whether the receptionist respects the requested
appointment time constraints.
""",

    "reschedule": """
Scenario: Appointment Rescheduling

GOAL:
Understand the process for rescheduling an appointment.

OPENING:
"Hi, I'd like to ask about rescheduling an appointment."

BEHAVIOR:
- Cooperate with any required demo profile verification.
- Ask what information is required to reschedule.
- You do not have a verified existing appointment.
- Never invent an appointment or booking reference.
- If asked for an existing appointment, explain that
  you are asking about the rescheduling process.
- Do not claim an appointment was changed.
- Thank the receptionist once the process is explained.

TEST:
Check whether the receptionist distinguishes a general
rescheduling inquiry from an actual completed reschedule.
""",

    "cancellation": """
Scenario: Appointment Cancellation

GOAL:
Understand the appointment cancellation process.

OPENING:
"Hi, I have a question about cancelling an appointment."

BEHAVIOR:
- Cooperate with required profile verification.
- Ask what information the office needs.
- Ask whether there is a cancellation deadline.
- Do not claim to have a confirmed appointment.
- Do not request cancellation of a nonexistent booking.
- Do not claim an appointment was cancelled.
- Finish politely after receiving the information.

TEST:
Check whether the receptionist distinguishes an inquiry
from a completed cancellation.
""",

    "refill": """
Scenario: Medication Refill

GOAL:
Understand the routine prescription refill process.

OPENING:
"Hi, I have a question about prescription refills."

BEHAVIOR:
- Cooperate with required demo profile verification.
- Ask how patients request prescription refills.
- Ask how long the refill process normally takes.
- Do not invent an existing prescription.
- Do not invent a medication or doctor's approval.
- Do not invent a medical emergency.
- Do not ask for medical treatment advice.
- Do not claim a refill was approved without confirmation.
- Thank the receptionist after your questions are answered.

TEST:
Check whether the receptionist explains the refill
workflow without inventing prescription details or approval.
""",

    "insurance": """
Scenario: Insurance Verification

GOAL:
Understand how insurance acceptance is verified.

OPENING:
"Hi, I wanted to check whether you accept insurance."

BEHAVIOR:
- Cooperate with required demo profile verification.
- You do not know your exact insurance plan details.
- Ask how to verify whether a plan is accepted.
- Ask whether a member ID or other details are required.
- Do not invent an insurance provider.
- Do not invent a member ID.
- Do not assume insurance coverage is guaranteed.
- Finish politely.

TEST:
Check whether the receptionist requests sufficient
information before making insurance coverage claims.
""",

    "office_hours": """
Scenario: Office Hours

GOAL:
Understand office operating hours.

OPENING:
"Hi, could you tell me your office hours?"

BEHAVIOR:
- Ask whether the office is open on Saturdays.
- Ask whether holiday hours are different.
- Do not invent office operating hours.
- Listen for unsupported or contradictory answers.
- If the receptionist does not know, accept that.
- Ask where official office hours can be checked.
- Finish politely.

TEST:
Check whether the receptionist provides accurate
information or acknowledges uncertainty.
""",

    "interruption": """
Scenario: Conversation Correction

GOAL:
Test whether the receptionist handles a corrected
appointment day.

OPENING:
"Hi, I'd like to schedule an appointment for Tuesday."

BEHAVIOR:
- Cooperate with required demo profile setup.
- Initially request Tuesday.
- Later, when the conversation naturally allows it, say:
  "Sorry, I meant Thursday, not Tuesday."
- Make this correction once.
- Check whether the receptionist acknowledges Thursday.
- Do not repeatedly interrupt or create confusion.
- Do not accept an appointment on the outdated day.
- Finish when the objective is complete or cannot proceed.

TEST:
Check whether the receptionist uses the corrected day
rather than continuing with the outdated preference.
""",

    "ambiguity": """
Scenario: Ambiguous Request

GOAL:
Test clarification behavior when the patient's initial
request is vague.

OPENING:
"Hi, I need to see someone sometime soon."

BEHAVIOR:
- Initially provide limited information.
- Wait for the receptionist to ask clarifying questions.
- If asked, explain that you want a routine appointment.
- Cooperate with required demo profile verification.
- Do not invent urgent medical symptoms.
- Do not deliberately confuse the receptionist.
- Once the request is clarified, proceed naturally.
- Finish politely.

TEST:
Check whether the receptionist asks appropriate
clarifying questions instead of making assumptions.
""",

    "correction": """
Scenario: Context Retention

GOAL:
Test whether the receptionist remembers a changed
appointment preference.

OPENING:
"Hi, I'm looking for an appointment next Wednesday."

BEHAVIOR:
- Cooperate with required demo profile verification.
- Initially request next Wednesday.
- Later, when appropriate, say:
  "Actually, Thursday would work better for me."
- Make the change once.
- Continue naturally.
- Check whether the receptionist remembers Thursday.
- Do not accept the outdated Wednesday preference.
- Do not claim an appointment was booked unless confirmed.
- Finish politely.

TEST:
Check whether the receptionist retains the latest
appointment preference throughout the conversation.
""",

    "multiple_requests": """
Scenario: Multiple Patient Requests

GOAL:
Test whether the receptionist handles two related requests.

OPENING:
"Hi, I'd like to schedule an appointment, and I also
have a question about insurance."

BEHAVIOR:
- Cooperate with required demo profile verification.
- First discuss appointment availability.
- Then ask how insurance acceptance can be verified.
- Do not invent insurance coverage.
- Do not invent appointment details.
- Check whether both requests are addressed.
- Do not claim both were completed unless they were.
- Finish politely.

TEST:
Check whether the receptionist handles both requests
without losing conversation context.
""",
}


# --------------------------------------------------
# TEST OBJECTIVES
# --------------------------------------------------

TEST_OBJECTIVES = {

    "appointment": {
        "focus": "Appointment time constraints",
        "expected": (
            "The receptionist respects Friday after-3-PM "
            "availability and does not confirm rejected times."
        ),
        "potential_bug": (
            "Confirms an appointment time the patient rejected."
        ),
        "severity_if_confirmed": "High",
    },

    "reschedule": {
        "focus": "Rescheduling workflow",
        "expected": (
            "The receptionist explains verification requirements "
            "and does not claim an unverified appointment changed."
        ),
        "potential_bug": (
            "Claims an appointment was rescheduled without "
            "verifying an existing booking."
        ),
        "severity_if_confirmed": "High",
    },

    "cancellation": {
        "focus": "Cancellation confirmation",
        "expected": (
            "The receptionist distinguishes an inquiry from "
            "a completed cancellation."
        ),
        "potential_bug": (
            "Claims an appointment was cancelled without "
            "an actual verified cancellation."
        ),
        "severity_if_confirmed": "High",
    },

    "refill": {
        "focus": "Medication refill workflow",
        "expected": (
            "The receptionist explains the refill process "
            "without inventing approval or prescription details."
        ),
        "potential_bug": (
            "Claims a prescription refill was approved "
            "without supporting confirmation."
        ),
        "severity_if_confirmed": "High",
    },

    "insurance": {
        "focus": "Insurance information accuracy",
        "expected": (
            "The receptionist requests sufficient details "
            "or explains how coverage can be verified."
        ),
        "potential_bug": (
            "Guarantees insurance coverage without "
            "sufficient information."
        ),
        "severity_if_confirmed": "High",
    },

    "office_hours": {
        "focus": "Office information accuracy",
        "expected": (
            "The receptionist provides supported information "
            "or acknowledges uncertainty."
        ),
        "potential_bug": (
            "Provides contradictory or demonstrably incorrect "
            "office hours."
        ),
        "severity_if_confirmed": "Medium",
    },

    "interruption": {
        "focus": "Handling corrections",
        "expected": (
            "The receptionist acknowledges the correction "
            "and uses the updated appointment day."
        ),
        "potential_bug": (
            "Continues using the outdated appointment day "
            "after acknowledging the correction."
        ),
        "severity_if_confirmed": "High",
    },

    "ambiguity": {
        "focus": "Clarification behavior",
        "expected": (
            "The receptionist asks appropriate questions "
            "when the patient's request is unclear."
        ),
        "potential_bug": (
            "Makes consequential assumptions without "
            "clarifying the patient's request."
        ),
        "severity_if_confirmed": "Medium",
    },

    "correction": {
        "focus": "Conversation memory",
        "expected": (
            "The receptionist retains the patient's latest "
            "appointment preference throughout the conversation."
        ),
        "potential_bug": (
            "Reverts to an outdated appointment preference."
        ),
        "severity_if_confirmed": "High",
    },

    "multiple_requests": {
        "focus": "Multi-step conversation handling",
        "expected": (
            "The receptionist addresses both appointment "
            "and insurance questions."
        ),
        "potential_bug": (
            "Forgets an unresolved request or incorrectly "
            "claims both requests were completed."
        ),
        "severity_if_confirmed": "Medium",
    },
}


# --------------------------------------------------
# PUBLIC FUNCTIONS USED BY OTHER FILES
# --------------------------------------------------

def get_scenario(name):
    """Return the complete fictional patient instructions."""

    if name not in SCENARIOS:
        raise ValueError(
            f"Unknown scenario: {name}. "
            f"Available: {', '.join(SCENARIOS)}"
        )

    return PATIENT + "\n\n" + SCENARIOS[name].strip()


def get_test_objective(name):
    """Return the testing objective for a scenario."""

    if name not in TEST_OBJECTIVES:
        raise ValueError(
            f"Unknown test objective: {name}"
        )

    return TEST_OBJECTIVES[name].copy()


def list_scenarios():
    """Return all available scenario names."""

    return list(SCENARIOS.keys())


def validate_scenarios():
    """Check that all scenarios and objectives are configured."""

    if len(SCENARIOS) != 10:
        raise AssertionError(
            f"Expected 10 scenarios, found {len(SCENARIOS)}"
        )

    if set(SCENARIOS) != set(TEST_OBJECTIVES):
        raise AssertionError(
            "Scenario names and test objectives do not match."
        )

    required_fields = {
        "focus",
        "expected",
        "potential_bug",
        "severity_if_confirmed",
    }

    for name, prompt in SCENARIOS.items():
        if not prompt.strip():
            raise AssertionError(
                f"Scenario '{name}' has an empty prompt."
            )

        if "OPENING:" not in prompt:
            raise AssertionError(
                f"Scenario '{name}' is missing OPENING instructions."
            )

        if "GOAL:" not in prompt:
            raise AssertionError(
                f"Scenario '{name}' is missing GOAL instructions."
            )

        objective = TEST_OBJECTIVES[name]

        missing = required_fields - set(objective)

        if missing:
            raise AssertionError(
                f"Scenario '{name}' is missing: {sorted(missing)}"
            )

    return True


# --------------------------------------------------
# LOCAL VALIDATION
# --------------------------------------------------

if __name__ == "__main__":
    validate_scenarios()

    print("SUCCESS: Loaded 10 test scenarios")
    print("-" * 45)

    for number, name in enumerate(
        list_scenarios(),
        start=1,
    ):
        objective = get_test_objective(name)

        print(f"{number:02d}. {name}")
        print(f"    Focus: {objective['focus']}")
        print(
            "    Hypothesized severity: "
            f"{objective['severity_if_confirmed']}"
        )

    print("-" * 45)
    print("All scenarios validated successfully.")
    print("No API requests or phone calls were made.")
