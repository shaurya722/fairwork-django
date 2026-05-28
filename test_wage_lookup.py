#!/usr/bin/env python3
"""Quick test to verify wage lookup works with classification info."""

import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fairwork.settings")
django.setup()

from services.wages import lookup_hourly_rate

# Test cases
test_cases = [
    ("HOME_CARE", 1, 1, "Home Care Level 1 Pay Point 1"),
    ("HOME_CARE", 1, 2, "Home Care Level 1 Pay Point 2"),
    ("HOME_CARE", 2, 1, "Home Care Level 2 Pay Point 1"),
    ("SOCIAL_COMMUNITY_SERVICES", 1, 1, "Social & Community Level 1 Pay Point 1"),
    ("SOCIAL_COMMUNITY_SERVICES", 2, 1, "Social & Community Level 2 Pay Point 1"),
]

print("=" * 70)
print("WAGE LOOKUP TEST")
print("=" * 70)

for stream, level, pay_point, description in test_cases:
    rate = lookup_hourly_rate(stream, level, pay_point)
    status = "✓" if rate else "✗"
    rate_str = f"${rate:.2f}/hr" if rate else "NOT FOUND"
    print(f"{status} {description:45s} → {rate_str}")

print("=" * 70)
