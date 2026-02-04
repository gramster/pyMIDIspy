#!/usr/bin/env python3
"""
Simple example: List all MIDI destinations.
"""

from snoize_midi_spy import get_destinations

print("MIDI Destinations:")
print("-" * 40)

destinations = get_destinations()

if not destinations:
    print("No MIDI destinations found.")
else:
    for dest in destinations:
        print(f"  Name: {dest.name}")
        print(f"    Unique ID: {dest.unique_id}")
        print(f"    Endpoint Ref: {dest.endpoint_ref}")
        print()
