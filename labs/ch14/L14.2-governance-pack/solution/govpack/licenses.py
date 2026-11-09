"""Licence decisions for Relay's components, including code an agent generated (reference solution).

A licence scan answers one question per component: may Relay use it as it is used, under license-policy-v1?
It reads SPDX identifiers and simple expressions. It does not read licence texts, and a snippet match only
says that generated code resembles published code; a person decides what to do about it.
"""

from __future__ import annotations


def classify(component: dict, policy: dict) -> tuple[str, str]:
    """(decision, reason) with decision "allow", "review" or "deny". Rules, first match wins:

    1. license None and origin "generated code (no match)" -> ("allow", "generated, no snippet match: record provenance")
    2. license None                                         -> ("review", "no licence recorded")
    3. license "NOASSERTION"                                -> ("review", "licence not stated")
    4. an expression "A OR B [OR C]": the best decision among the options, in the order allow > review > deny,
       with reason "<chosen option> chosen from <license>"
    5. in policy["deny_for_network_service"]                -> ("deny", "<license>: obligations triggered by network use")
    6. in policy["allow"]                                   -> ("allow", "<license>")
    7. in policy["review"]                                  -> ("review", "<license>: copyleft or attribution terms")
    8. otherwise                                            -> ("review", "<license>: not in the policy")
    """
    lic, origin = component.get("license"), component.get("origin")
    if lic is None and origin == "generated code (no match)":
        return "allow", "generated, no snippet match: record provenance"
    if lic is None:
        return "review", "no licence recorded"
    if lic == "NOASSERTION":
        return "review", "licence not stated"
    if " OR " in lic:
        rank = {"allow": 0, "review": 1, "deny": 2}
        options = [(classify({**component, "license": o.strip()}, policy), o.strip()) for o in lic.split(" OR ")]
        (decision, _), chosen = min(options, key=lambda x: rank[x[0][0]])
        return decision, f"{chosen} chosen from {lic}"
    if lic in policy["deny_for_network_service"]:
        return "deny", f"{lic}: obligations triggered by network use"
    if lic in policy["allow"]:
        return "allow", lic
    if lic in policy["review"]:
        return "review", f"{lic}: copyleft or attribution terms"
    return "review", f"{lic}: not in the policy"
