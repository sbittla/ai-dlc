"""Messages for delivery (B5): write these tests FIRST, from the spec, before delivery.py exists.

Spec: ESC-SPEC-1
Spec version: 1.1.0

Lab 8.1, step 3. Replace each stub with a real test that runs the engine
(save_rule, set_priority, run_pass) and reads the outbox. Your oracles must be
independent of the code under test: recompute the signature with the standard
library's hmac, take the title's parts from the criterion's own words, and copy
expected strings from the spec. The grader runs your file against four seeded
bugs (data/variants/D1 to D4); every one must make at least one test fail.
"""

import hashlib  # noqa: F401
import hmac  # noqa: F401
import json  # noqa: F401
import re  # noqa: F401

from escalation_fixtures import ADMIN, GUEST_INVITED, OWNER, ROTTERDAM, USERS, minutes, p1_rule  # noqa: F401

from relay.escalation import EngineConfig, EscalationStore, Webhook, run_pass, save_rule, set_priority  # noqa: F401
from relay.models import Task  # noqa: F401

SECRET = b"whsec-test-only-0001"
LINK = "https://relay.example/ws-demo/projects/10/tasks/7"
TITLED = Task(7, ROTTERDAM.id, "Customer 4471 card data exposed")


def test_ESC_AC15_two_targets_get_two_emails_and_one_signed_event():
    raise NotImplementedError("Lab 8.1 step 3: write this test from ESC-AC15 and SEC-06 before the code exists")


def test_ESC_AC17_email_shows_rule_name_step_and_both_times_in_utc():
    raise NotImplementedError("Lab 8.1 step 3: write this test from ESC-AC17 before the code exists")


def test_ESC_AC27_no_part_of_the_title_in_emails_or_the_webhook_and_both_carry_the_link():
    raise NotImplementedError("Lab 8.1 step 3: write this test from ESC-AC27 before the code exists")
